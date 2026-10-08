"""只读取已经匹配目标商品的 JSON-LD 节点；不解析营销星星或店铺轮播。"""
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup
from django.core.exceptions import ValidationError
from .validation import clean_rating, clean_count
from .catalog_content import plain_text, same_product


def five_star_rating(value):
    if not isinstance(value, dict):
        return None
    try:
        if str(value.get('bestRating', 5)) not in ('5', '5.0', '5.00'):
            return None
        rating = clean_rating(value.get('ratingValue'))
        return str(rating) if rating is not None else None
    except ValidationError:
        return None


def product_reviews(node, source_url, identity_match=None):
    aggregate = node.get('aggregateRating')
    aggregate = aggregate if isinstance(aggregate, dict) else {}
    def count(key):
        try:
            return clean_count(aggregate.get(key))
        except ValidationError:
            return None
    samples = node.get('review', [])
    samples = samples if isinstance(samples, list) else [samples]
    reviews = []
    seen = set()
    for sample in samples:
        if not isinstance(sample, dict) or not isinstance(sample.get('reviewBody'), str):
            continue
        reviewed = sample.get('itemReviewed')
        identity=reviewed if isinstance(reviewed,str) else None
        if isinstance(reviewed,dict):
            types=reviewed.get('@type',[])
            types=[types] if isinstance(types,str) else types
            if isinstance(types,list) and any(t in types for t in ('Organization','LocalBusiness','Store')):
                continue
            identity=reviewed.get('url') or reviewed.get('@id')
        if isinstance(identity,str):
            if identity_match:
                if not identity_match(urljoin(source_url,identity)):continue
            elif not same_product(identity,source_url):
                continue
        body = BeautifulSoup(sample['reviewBody'], 'html.parser').get_text(' ', strip=True)[:2000]
        if not body or body.casefold() in seen:
            continue
        seen.add(body.casefold())
        date = sample.get('datePublished')
        reviews.append({'body': body, 'title': plain_text(sample.get('name'))[:300], 'rating': five_star_rating(sample.get('reviewRating')),
                        'date': date[:50] if isinstance(date, str) else '', 'source_url': source_url})
        if len(reviews) >= 10:
            break
    return {'rating': five_star_rating(aggregate), 'review_count': count('reviewCount'),
            'rating_count': count('ratingCount'), 'review_samples': reviews,
            'review_source': source_url if aggregate or reviews else '',
            'review_scope': '目标商品结构化数据', 'review_samples_limited': bool(reviews)}


def widget_review_samples(soup, node, source_url):
    """只读商品页已嵌入的 Judge.me 评论，不请求第三方私有接口。"""
    canonical = soup.select('link[rel="canonical"]')
    if len(canonical) != 1 or not same_product(canonical[0].get('href'), source_url):
        return []
    title = plain_text(node.get('name'))
    widgets = [widget for widget in soup.select('.jdgm-review-widget')
               if title and plain_text(widget.get('data-product-title')) == title]
    if len(widgets) != 1:
        return []
    result, seen = [], set()
    for row in widgets[0].select('.jdgm-rev'):
        if not same_product(row.get('data-product-url'), source_url):
            continue
        body_node = row.select_one('.jdgm-rev__body')
        body = plain_text(str(body_node), 2000) if body_node else ''
        if not body or body in seen:
            continue
        seen.add(body)
        rating_node = row.select_one('.jdgm-rev__rating')
        time_node = row.select_one('time[datetime]')
        title_node = row.select_one('.jdgm-rev__title')
        result.append({'body': body,
                       'title': plain_text(str(title_node)) if title_node else '',
                       'rating': five_star_rating({'ratingValue': rating_node.get('data-score')}) if rating_node else None,
                       'date': time_node.get('datetime', '')[:50] if time_node else '',
                       'source_url': source_url})
        if len(result) >= 10:
            break
    return result
