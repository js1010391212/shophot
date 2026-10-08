"""与目标商品报价一起观测的公开内容；不执行页面 HTML 或脚本。"""
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup


def plain_text(value, limit=300):
    if not isinstance(value, str):
        return ''
    soup = BeautifulSoup(value, 'html.parser')
    for tag in soup(['script', 'style']):
        tag.decompose()
    return soup.get_text(' ', strip=True)[:limit]


def same_product(value, target):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        actual, expected = urlsplit(urljoin(target, value)), urlsplit(target)
        return (actual.scheme == 'https' and not actual.username and not actual.password
                and actual.port in (None, 443)
                and (actual.hostname, actual.path.rstrip('/')) == (expected.hostname, expected.path.rstrip('/')))
    except ValueError:
        return False


def image_url(value, target):
    if isinstance(value, dict):
        value = value.get('url') or value.get('contentUrl') or value.get('image')
    if not isinstance(value, str) or len(value) > 2000:
        return ''
    try:
        url = urljoin(target, value)
        parts = urlsplit(url)
        # 只显示当前公开店铺或 Shopify 官方 CDN 的 HTTPS 图片。
        if (parts.scheme == 'https' and not parts.username and not parts.password
                and parts.port in (None, 443)
                and parts.hostname in (urlsplit(target).hostname, 'cdn.shopify.com')):
            return url
    except ValueError:
        pass
    return ''


def product_content(node, target, variants):
    raw_images = node.get('image', [])
    raw_images = raw_images if isinstance(raw_images, list) else [raw_images]
    raw_images = list(raw_images)
    # Shopify ProductGroup 常把图片放在各 hasVariant，而不是商品组顶层。
    children = node.get('hasVariant', [])
    if isinstance(children, list):
        for child in children[:100]:
            if not isinstance(child, dict) or not any(same_product(child.get(key), target) for key in ('url', '@id')):
                continue
            values = child.get('image', [])
            raw_images.extend(values if isinstance(values, list) else [values])
    images = []
    for value in raw_images[:30]:
        url = image_url(value, target)
        if url and url not in images:
            images.append(url)
        if len(images) == 6:
            break
    brand = node.get('brand')
    if isinstance(brand, dict):
        brand = brand.get('name')
    description = plain_text(node.get('description'), 6000)
    return {'images': images, 'description': description,
            'description_limited': len(plain_text(node.get('description'), 6001)) > 6000,
            'brand': plain_text(brand), 'category': plain_text(node.get('category')),
            'sku': plain_text(node.get('sku')),
            'variants': variants[:100], 'variants_limited': len(variants) > 100,
            'content_source': target}
