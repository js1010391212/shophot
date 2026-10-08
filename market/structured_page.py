"""共享的严格 JSON-LD 文件解析；只接受明确归属和唯一报价。"""
import json
from urllib.parse import urlsplit, parse_qs, urljoin
from bs4 import BeautifulSoup
from django.core.exceptions import ValidationError
from .collectors import MAX_BYTES
from .validation import clean_price, clean_currency, clean_rating, clean_count
from .catalog_content import plain_text


def parse_structured_page(raw, target, normalizer, variant_key, platform):
    target=normalizer(target)
    if len(raw)>MAX_BYTES:
        raise ValidationError('页面文件超过 2 MB。')
    try:
        html=raw.decode('utf-8-sig')
    except UnicodeError:
        raise ValidationError('请保存并上传 UTF-8 HTML 页面文件。')
    soup=BeautifulSoup(html,'html.parser')
    if ('KPSDK' in html and not soup.find('h1')) or '_____tmd_____' in html or 'x5secdata' in html:
        raise ValidationError('这是安全验证文件，不含商品内容；未保存价格。')
    expected=urlsplit(target)
    variant=parse_qs(expected.query).get(variant_key,[''])[0]
    def matches(value,strict=False):
        if not isinstance(value,str):return False
        try:
            normalized=urlsplit(normalizer(urljoin(target,value)))
        except (ValidationError, ValueError):return False
        return normalized.path==expected.path and (not strict or parse_qs(normalized.query).get(variant_key,[''])[0]==variant)
    nodes=[]
    for script in soup.find_all('script',type='application/ld+json'):
        try:data=json.loads(script.string or script.get_text())
        except (ValueError,TypeError,RecursionError):continue
        pending=[data]
        while pending:
            node=pending.pop()
            if isinstance(node,list):
                pending.extend(node)
                continue
            if not isinstance(node,dict):continue
            pending.extend(value for value in node.values() if isinstance(value,(dict,list)))
            kinds=node.get('@type',[])
            if (kinds=='Product' or isinstance(kinds,list) and 'Product' in kinds) and any(matches(node.get(k)) for k in ('url','@id')):
                nodes.append(node)
    if len(nodes)!=1:
        raise ValidationError('文件中无法唯一确认目标商品的结构化数据。请核对原页面或改用手动记录，不会读取推荐商品价格。')
    node=nodes[0];offers=node.get('offers',[])
    if isinstance(offers,dict):offers=[offers]
    offers=[o for o in offers if isinstance(o,dict) and o.get('@type')=='Offer' and ('url' not in o or matches(o['url'],strict=bool(variant)))] if isinstance(offers,list) else []
    if variant:
        offers=[o for o in offers if matches(o.get('url'),strict=True) or matches(node.get('url'),strict=True) and 'url' not in o]
    if len(offers)!=1 or 'price' not in offers[0] or 'priceCurrency' not in offers[0]:
        raise ValidationError('缺少唯一明确的规格报价与币种。请在商品链接保留规格编号，或改用手动记录；不取最低价、划线价或分期月付款。')
    offer=offers[0]
    if not variant and isinstance(offer.get('url'),str):
        offered_variant=parse_qs(urlsplit(normalizer(urljoin(target,offer['url']))).query).get(variant_key,[''])[0]
        if offered_variant:
            raise ValidationError('文件报价属于特定规格，请在目标商品链接保留 '+variant_key+' 后重新导入，避免混合规格历史。')
    aggregate=node.get('aggregateRating',{})
    rating=reviews=None
    if isinstance(aggregate,dict):
        try:
            if str(aggregate.get('bestRating',5)) in ('5','5.0','5.00'):rating=clean_rating(aggregate.get('ratingValue'))
        except ValidationError:pass
        try:reviews=clean_count(aggregate.get('reviewCount'))
        except ValidationError:pass
    title=plain_text(node.get('name'))[:300]
    if not title:raise ValidationError('商品名称缺失，无法预览。')
    from .reviews import product_reviews
    samples=product_reviews(node,target,identity_match=matches)['review_samples']
    return {'review_samples':samples,'title':title,'price':str(clean_price(offer['price'])),'currency':clean_currency(offer['priceCurrency']),
            'rating':str(rating) if rating is not None else None,'review_count':reviews,
            'specification':variant or plain_text(node.get('sku'))[:80] or '文件中唯一明确报价（未提供规格编号）'}
