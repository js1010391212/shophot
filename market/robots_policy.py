"""Shared, bounded REP gate for the existing HTTPS collectors.

RFC 9309 group/rule semantics; crawl-delay is a conservative local extension.
Redirects and non-200 responses stop collection, rather than grant access.
This is a request gate, not a commercial-use licence or a general crawler.
"""
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from .collectors import CollectionError, MAX_BYTES

AGENT = 'ShopHot'
_UNRESERVED = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~')


def _octets(value, pattern=False):
    """Compare UTF-8/percent octets; encoded reserved chars stay encoded."""
    result, index = [], 0
    while index < len(value):
        char = value[index]
        if char == '%' and re.fullmatch('[0-9a-fA-F]{2}', value[index + 1:index + 3]):
            number = int(value[index + 1:index + 3], 16)
            result.append(chr(number) if chr(number) in _UNRESERVED else f'%{number:02X}')
            index += 3
            continue
        if ord(char) > 127 or char in ' \t' or char == '$' or (not pattern and char == '*'):
            result.extend(f'%{byte:02X}' for byte in char.encode('utf-8'))
        else:
            result.append(char)
        index += 1
    return ''.join(result)


def _matches(pattern, path):
    """Prefix match with REP * and terminal $; no regex backtracking."""
    anchored = pattern.endswith('$')
    parts = (pattern[:-1] if anchored else pattern).split('*')
    if not path.startswith(parts[0]):
        return False
    position = len(parts[0])
    if len(parts) == 1:
        return not anchored or position == len(path)
    for index, part in enumerate(parts[1:], 1):
        if anchored and index == len(parts) - 1:
            return path.endswith(part) and len(path) - len(part) >= position
        found = path.find(part, position)
        if found < 0:
            return False
        position = found + len(part)
    return True


def _origin(url):
    try:
        parts = urlsplit(url)
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443):
            raise ValueError
        return parts.hostname.lower()
    except ValueError as exc:
        raise CollectionError('robots.txt 仅允许同域 HTTPS 默认端口。') from exc


class RobotsPolicy:
    def __init__(self, text, root, agent=AGENT):
        self.host = _origin(root)
        groups, agents, rules, delays = [], [], [], []
        unknown_record = False
        for raw in text.splitlines():
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            if ':' not in line:
                raise CollectionError('robots.txt 格式无法安全解析，已停止。')
            key, value = (part.strip() for part in line.split(':', 1))
            key = key.lower()
            if any(ord(char) < 32 and char != '\t' for char in line):
                raise CollectionError('robots.txt 含无效控制字符，已停止。')
            if key == 'user-agent':
                if not re.fullmatch(r'[A-Za-z0-9_-]+|\*', value):
                    raise CollectionError('robots.txt 的 User-agent 无法安全解析。')
                if rules or delays:
                    groups.append((agents, rules, delays))
                    agents, rules, delays = [], [], []
                agents.append(value.lower())
            elif agents and key in ('allow', 'disallow'):
                if value and not value.startswith(('/', '*')):
                    raise CollectionError('robots.txt 路径无法安全解析，已停止。')
                # Empty rules still separate a subsequent User-agent group.
                rules.append((value, key == 'allow'))
            elif agents and key == 'crawl-delay':
                delays.append(value)
            elif key not in ('allow', 'disallow', 'crawl-delay', 'sitemap', 'host', 'request-rate'):
                unknown_record = True
            # Other records, including Sitemap, must not terminate a group.
        if agents:
            groups.append((agents, rules, delays))
        if not groups and unknown_record:
            raise CollectionError('robots.txt 未提供可识别规则，已停止。')
        chosen = [group for group in groups if agent.lower() in group[0]]
        if not chosen:
            chosen = [group for group in groups if '*' in group[0]]
        self.rules = []
        self.delay = 1.0
        for _, group_rules, group_delays in chosen:
            for value, allow in group_rules:
                if value:
                    anchored = value.endswith('$')
                    pattern = _octets(value[:-1] if anchored else value, pattern=True) + ('$' if anchored else '')
                    # Count octets in the rule, not the text length of %XX.
                    specificity = len(re.sub(r'%[0-9A-F]{2}', 'x', pattern).encode('utf-8'))
                    self.rules.append((pattern, specificity, allow))
            for value in group_delays:
                try:
                    delay = Decimal(value)
                    if not delay.is_finite() or delay < 0:
                        raise InvalidOperation
                except InvalidOperation as exc:
                    raise CollectionError('robots.txt 的 crawl-delay 无效，已停止。') from exc
                if delay > 30:
                    raise CollectionError('店铺要求较长采集间隔，本次停止。')
                self.delay = max(self.delay, float(delay))

    def can_fetch(self, url):
        try:
            host = _origin(url)
        except CollectionError:
            return False
        if host != self.host:
            return False
        parts = urlsplit(url)
        path = _octets((parts.path or '/') + ('?' + parts.query if parts.query else ''))
        if path == '/robots.txt':
            return True
        matches = [(length, allow) for pattern, length, allow in self.rules if _matches(pattern, path)]
        return max(matches)[1] if matches else True


def load_robots(client, root, agent=AGENT):
    """Use the caller's safe client; no redirect, retry or identity/DNS change."""
    _origin(root)
    url = root.rstrip('/') + '/robots.txt'
    with client.stream('GET', url, follow_redirects=False) as response:
        if response.status_code != 200:
            raise CollectionError(f'robots.txt 返回 HTTP {response.status_code}，已停止采集。')
        if response.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'text/plain':
            raise CollectionError('robots.txt 未返回纯文本，已停止采集。')
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise CollectionError('robots.txt 响应超过 2 MB，已停止采集。')
    try:
        text = body.decode('utf-8-sig')
    except UnicodeError as exc:
        raise CollectionError('robots.txt 不是有效 UTF-8，已停止采集。') from exc
    return RobotsPolicy(text, root, agent)
