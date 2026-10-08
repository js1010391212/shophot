"""跟踪商品的评论样本历史；复用现有词频与证据分析。"""
from django.core.exceptions import ValidationError
from .models import ProductReviewBatch
from .review_analysis import analyze_reviews


def save_batch(quote, result, source_url, created_quote):
    """观测与样本在调用者事务中一起保存，重复导入不覆盖样本。"""
    samples=result.get('review_samples',[])
    saved=ProductReviewBatch.objects.filter(snapshot=quote).first()
    fingerprint=result['file_fingerprint']
    if saved:
        if saved.samples!=samples or saved.file_fingerprint!=fingerprint:
            raise ValidationError('该观测已有不同评论样本，未覆盖历史；请核对文件与观测时间。')
        return saved
    if not samples:
        return None
    if not created_quote and '文件 '+fingerprint+'；' not in quote.context:
        raise ValidationError('该时间的已有观测来自其他记录，不能附加本文件评论；请核对实际观测时间。')
    return ProductReviewBatch.objects.create(snapshot=quote,source_url=source_url,
        file_fingerprint=fingerprint,samples=samples)



def catalog_samples(product):
    from .workflows import saved_catalog_product
    from .models import StoreDiscovery
    try:
        matched=saved_catalog_product(product.url)
    except (ValidationError,ValueError):
        return None
    if not matched:
        return None
    pk,index=matched
    scan=StoreDiscovery.objects.get(pk=pk)
    item=scan.products[index]
    if not analyze_reviews(item)['sample_count']:
        return None
    return {'scan':pk,'index':index,'item':item}


def analysis_item(product,batch,catalog=None):
    from .catalog_content import plain_text, same_product
    from .reviews import five_star_rating
    item=dict(catalog['item']) if catalog else {'url':product.url,'title':product.title}
    if batch:
        item={'url':batch.source_url,'title':product.title,'review_samples':batch.samples}
    raw=item.get('review_samples',[])
    raw=raw if isinstance(raw,list) else []
    samples=[];seen=set()
    for sample in raw[:10]:
        if not isinstance(sample,dict):continue
        if sample.get('source_url') and not same_product(sample['source_url'],item['url']):continue
        body=plain_text(sample.get('body'),2000)
        if not body or body.casefold() in seen:continue
        seen.add(body.casefold())
        samples.append({'body':body,'title':plain_text(sample.get('title'))[:300],
            'rating':five_star_rating({'ratingValue':sample.get('rating')}),
            'date':plain_text(sample.get('date'))[:50],'source_url':item['url']})
    item['review_samples']=samples
    return item
