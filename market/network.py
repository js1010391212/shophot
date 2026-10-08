"""公开商品网络访问：公网地址校验、Fake-IP DoH 兼容和固定连接。"""
import ipaddress
import socket
import httpx
from .collectors import CollectionError

def public_address(host):
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if addresses and all(ipaddress.ip_address(item[4][0]) in ipaddress.ip_network('198.18.0.0/15') for item in addresses):
            # 部分本地代理返回 Fake-IP；用固定可信 DoH 取得真实公网 IP 后仍固定连接。
            with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as resolver:
                response = resolver.get('https://cloudflare-dns.com/dns-query', params={'name': host, 'type': 'A'},
                                        headers={'Accept': 'application/dns-json'})
                response.raise_for_status()
                payload = response.json()
                answers = [item['data'] for item in payload.get('Answer', []) if item.get('type') == 1]
                if payload.get('Status') != 0 or not answers or any(not ipaddress.ip_address(value).is_global for value in answers):
                    raise CollectionError('公开 DNS 未返回可验证的公网地址。')
                return answers[0]
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise CollectionError('店铺地址不能指向本地或私有网络。')
        return addresses[0][4][0]
    except (ValueError, socket.gaierror) as exc:
        raise CollectionError('店铺域名无法解析。') from exc


class PublicProductTransport(httpx.BaseTransport):
    """连接到已校验 IP，同时保留原请求域名用于 Cookie 与证书验证。"""
    def __init__(self, transport=None):
        self.transport = transport or httpx.HTTPTransport()
        self.addresses = {}

    def handle_request(self, request):
        host = request.url.host
        address = self.addresses.get(host)
        if address is None:
            address = public_address(host)
            self.addresses[host] = address
        target = request.url.copy_with(host=address)
        headers = request.headers.copy()
        headers['Host'] = host
        extensions = dict(request.extensions, sni_hostname=host)
        pinned = httpx.Request(request.method, target, headers=headers, stream=request.stream, extensions=extensions)
        return self.transport.handle_request(pinned)

    def close(self):
        self.transport.close()
