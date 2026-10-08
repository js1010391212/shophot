"""纯结构化报价归属校验；不请求网络、不写数据、不按同价合并规格。"""
from urllib.parse import parse_qs, urljoin, urlsplit

from django.core.exceptions import ValidationError


class QuoteTarget:
    """由平台规范化器确定商品及规格；没有 URL 的 Offer 仅继承明确父节点。"""

    def __init__(self, target, normalizer, variant_key):
        self.normalizer = normalizer
        self.variant_key = variant_key
        self.url = normalizer(target)
        self.identity = self.reference(self.url)
        self.variant = self.identity[2]

    def reference(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValidationError('缺少明确商品链接。')
        # 空地址、单独片段和查询参数不能凭目标 URL 补造成商品身份。
        if not urlsplit(value).path:
            raise ValidationError('链接没有明确商品路径。')
        parts = urlsplit(self.normalizer(urljoin(self.url, value)))
        variant = parse_qs(parts.query).get(self.variant_key, [''])[0]
        return parts.hostname, parts.path, variant

    def matches(self, value, strict=False):
        try:
            identity = self.reference(value)
        except (ValidationError, ValueError):
            return False
        return identity[:2] == self.identity[:2] and (not strict or identity[2] == self.variant)

    def _product_variant(self, node):
        references = []
        invalid = False
        for key in ('url', '@id'):
            if key not in node:
                continue
            try:
                references.append(self.reference(node[key]))
            except (ValidationError, ValueError):
                invalid = True
        if not any(ref[:2] == self.identity[:2] for ref in references):
            return None
        if invalid or any(ref[:2] != self.identity[:2] for ref in references):
            raise ValidationError('商品 url 与 @id 归属冲突，未保存价格。')
        variants = {ref[2] for ref in references if ref[2]}
        if len(variants) > 1:
            raise ValidationError('商品节点的规格编号冲突，未保存价格。')
        return next(iter(variants), '')

    def select(self, products):
        matched = []
        for node in products:
            variant = self._product_variant(node)
            if variant is not None:
                matched.append((node, variant))
        if len(matched) != 1:
            raise ValidationError('无法唯一确认目标商品的结构化数据，未保存价格；不会读取推荐商品或无身份节点。')
        node, parent_variant = matched[0]
        if parent_variant and parent_variant != self.variant:
            raise ValidationError('商品节点属于特定或不同规格，请核对链接中的 '+self.variant_key+'，未保存价格。')
        offers = node.get('offers', [])
        if isinstance(offers, dict):
            offers = [offers]
        candidates = []
        for offer in offers if isinstance(offers, list) else []:
            if not isinstance(offer, dict) or offer.get('@type') != 'Offer':
                continue
            if 'url' in offer:
                try:
                    identity = self.reference(offer['url'])
                except (ValidationError, ValueError):
                    raise ValidationError('Offer 商品链接无效，无法确认报价归属。')
                if identity[:2] != self.identity[:2]:
                    raise ValidationError('Offer 报价属于其他商品，未保存价格。')
                offered_variant = identity[2]
                if parent_variant and offered_variant and parent_variant != offered_variant:
                    raise ValidationError('Product 与 Offer 的规格编号冲突，未保存价格。')
            else:
                offered_variant = parent_variant
            if '@id' in offer:
                try:
                    identifier = self.reference(offer['@id'])
                except (ValidationError, ValueError):
                    raise ValidationError('Offer @id 无法确认商品归属。')
                if identifier[:2] != self.identity[:2] or identifier[2] and identifier[2] != offered_variant:
                    raise ValidationError('Offer url、@id 或继承规格的归属冲突，未保存价格。')
            if not self.variant and offered_variant:
                raise ValidationError('报价属于特定规格，请在目标商品链接保留 '+self.variant_key+' 后重新导入，避免混合规格历史。')
            if offered_variant != self.variant:
                continue
            if 'price' in offer and 'priceCurrency' in offer:
                candidates.append(offer)
        if len(candidates) != 1:
            raise ValidationError('缺少唯一明确的规格 Offer 报价与币种；不取最低价、划线价或分期月付款。')
        return node, candidates[0]
