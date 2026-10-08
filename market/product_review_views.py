from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET
from .models import Product, ProductReviewBatch
from .product_review_forms import ReviewHistoryForm
from .product_reviews import catalog_samples, analysis_item
from .review_analysis import analyze_reviews


@login_required
@require_GET
def product_reviews(request,pk):
    product=get_object_or_404(Product,pk=pk)
    batches=list(ProductReviewBatch.objects.filter(snapshot__product=product).exclude(snapshot__source='browser').select_related('snapshot')[:100])
    catalog=catalog_samples(product)
    form=ReviewHistoryForm(request.GET,batches=batches,catalog_available=bool(catalog))
    valid=form.is_valid()
    selected=form.cleaned_data.get('batch') if valid else None
    batch=(next((row for row in batches if row.pk==selected),None) if selected else (batches[0] if batches else None)) if valid else None
    use_catalog=bool(valid and catalog and (selected==-1 or (not selected and not batches)))
    item=analysis_item(product,batch,catalog if use_catalog else None)
    return render(request,'market/product_reviews.html',{'product':product,'form':form,'batch':batch,
        'review_analysis':analyze_reviews(item),'samples':item['review_samples'],'catalog':catalog if use_catalog else None,'page_import_supported':product.platform in ('AliExpress','OTTO')},status=200 if valid else 400)
