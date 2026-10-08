"""共享的严格 JSON-LD 文件解析；只接受明确归属和唯一报价。"""
import json
from bs4 import BeautifulSoup
from django.core.exceptions import ValidationError
from .collectors import MAX_BYTES
from .validation import clean_price, clean_currency, clean_rating, clean_count
from .catalog_content import plain_text
from .quote_identity import QuoteTarget


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
    identity=QuoteTarget(target,normalizer,variant_key)
    variant=identity.variant
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
            if kinds=='Product' or isinstance(kinds,list) and 'Product' in kinds:
                nodes.append(node)
    node,offer=identity.select(nodes)
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
    samples=product_reviews(node,target,identity_match=identity.matches)['review_samples']
    return {'review_samples':samples,'title':title,'price':str(clean_price(offer['price'])),'currency':clean_currency(offer['priceCurrency']),
            'rating':str(rating) if rating is not None else None,'review_count':reviews,
            'specification':variant or plain_text(node.get('sku'))[:80] or '文件中唯一明确报价（未提供规格编号）'}
