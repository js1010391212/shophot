"""Exact single-spec catalog references; no Snapshot conversion or network access."""
import json
from urllib.parse import parse_qsl, urlencode, urlsplit

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.dateparse import parse_datetime

from .candidates import candidate_url
from .forms import ProfitForm
from .models import CatalogCandidate, CatalogPriceObservation
from .price_history import capture_quote_scope, observations_for_url

UNAVAILABLE = '目录报价须为单一明确规格的单值金额，并保留有效规格依据；范围、缺失或不明确的报价不能直接带入，请选择有效历史记录或手填假设。'
CONDITIONS = ['目录公开页面的历史报价，不是实时价格或成交价。', '收货国家、税费、运费及结账优惠未确认；规格不用于推断物流适用性。']
SOURCE_KEYS = {'kind', 'id', 'discovery_id', 'job_id', 'candidate_id', 'title', 'url', 'store_url', 'price', 'captured_price', 'currency', 'observed_at', 'source', 'sku_id', 'market_country', 'conditions', 'conditions_unknown', 'quote_scope', 'availability'}


def single_scope(url, price, currency, scope):
    """Rebuild the producer's signature rather than trusting a nonempty hash."""
    try:
        if not isinstance(scope, dict) or type(scope.get('version')) is not int or scope['version'] != 1:
            raise ValueError
        if type(scope.get('variant_count')) is not int or scope['variant_count'] != 1:
            raise ValueError
        identities = scope['identities']
        if not isinstance(identities, list) or len(identities) != 1:
            raise ValueError
        identity = identities[0]
        if not isinstance(identity, dict) or set(identity) != {'url', 'sku', 'name', 'size', 'color', 'range'} or identity['range'] is not False:
            raise ValueError
        if any(not isinstance(identity[k], str) or len(identity[k]) > 1000 for k in ('url', 'sku', 'name', 'size', 'color')):
            raise ValueError
        variant_pairs = parse_qsl(urlsplit(identity['url']).query, keep_blank_values=True)
        if len({k for k, _ in variant_pairs}) != len(variant_pairs):
            raise ValueError
        query = dict(variant_pairs)
        if not (identity['sku'] or identity['size'] or identity['color'] or query.get('variant')):
            raise ValueError
        # A specification URL may add a variant, but cannot change target market parameters.
        target_pairs = parse_qsl(urlsplit(url).query, keep_blank_values=True)
        if len({k for k, _ in target_pairs}) != len(target_pairs):
            raise ValueError
        target_params = dict(target_pairs)
        if any(query.get(k) != target_params.get(k) for k in ('country', 'currency')):
            raise ValueError
        if any(query.get(k) != v for k, v in target_params.items()):
            raise ValueError
        rebuilt = capture_quote_scope({'currency': currency, 'variants': [{**identity, 'price_low': price, 'price_high': price, 'currency': currency}]}, url)
        if not rebuilt or rebuilt != scope:
            raise ValueError
        return identity
    except (KeyError, TypeError, ValueError, ValidationError):
        raise ValidationError(UNAVAILABLE) from None


def validate_quote(quote):
    try:
        price = ProfitForm.base_fields['selling_price'].clean(quote.price_low)
        if price != quote.price_low or quote.price_high != price or candidate_url(quote.url) != quote.url:
            raise ValueError
        if not isinstance(quote.currency, str) or len(quote.currency) != 3 or not quote.currency.isascii() or not quote.currency.isalpha() or not quote.currency.isupper():
            raise ValueError
        if quote.observed_at is None or quote.observed_at.tzinfo is None:
            raise ValueError
        return single_scope(quote.url, price, quote.currency, quote.quote_scope)
    except (ValidationError, ValueError, TypeError):
        raise ValidationError(UNAVAILABLE) from None


def resolve_catalog(owner, pk, candidate_id=None):
    quote = get_object_or_404(CatalogPriceObservation.objects.select_related('discovery', 'job'), pk=pk)
    validate_quote(quote)
    if quote.job.discovery_id != quote.discovery_id:
        raise ValidationError(UNAVAILABLE)
    candidate = None
    if candidate_id is not None:
        candidate = get_object_or_404(CatalogCandidate, pk=candidate_id, owner=owner)
        if candidate.url != candidate_url(quote.url) or candidate.store_url != quote.discovery.url:
            raise ValidationError('候选商品与目录报价不一致，请从自己的候选清单重新选择。')
    return {'kind': 'catalog', 'id': quote.pk, 'quote': quote, 'candidate': candidate}


def catalog_source(reference):
    quote = reference['quote']
    identity = validate_quote(quote)
    return dict(kind='catalog', id=quote.pk, discovery_id=quote.discovery_id, job_id=quote.job_id,
                candidate_id=reference['candidate'].pk if reference.get('candidate') else None,
                title=quote.title, url=quote.url, store_url=quote.discovery.url,
                price=format(quote.price_low, 'f'), captured_price=format(quote.price_low, 'f'), currency=quote.currency,
                observed_at=quote.observed_at.isoformat(), source='catalog', sku_id=identity['sku'] or None,
                market_country=None, conditions=list(CONDITIONS), conditions_unknown=True,
                quote_scope=quote.quote_scope, availability=quote.availability)


def valid_catalog_source(source):
    """Strict version-2 saved-source shape, usable without database access."""
    try:
        if not isinstance(source, dict) or set(source) != SOURCE_KEYS or source['kind'] != 'catalog' or source['source'] != 'catalog':
            return False
        if any(type(source[k]) is not int or not 1 <= source[k] <= 9223372036854775807 for k in ('id', 'discovery_id', 'job_id')):
            return False
        cid = source['candidate_id']
        if cid is not None and (type(cid) is not int or not 1 <= cid <= 9223372036854775807):
            return False
        for key in ('title', 'url', 'store_url', 'price', 'captured_price', 'currency', 'observed_at', 'availability'):
            if not isinstance(source[key], str) or len(source[key]) > 1000:
                return False
        if source['price'] != source['captured_price'] or source['market_country'] is not None or source['conditions_unknown'] is not True or source['conditions'] != CONDITIONS:
            return False
        if candidate_url(source['url']) != source['url'] or len(source['currency']) != 3 or not source['currency'].isascii() or not source['currency'].isalpha() or not source['currency'].isupper():
            return False
        moment = parse_datetime(source['observed_at'])
        if moment is None or moment.tzinfo is None:
            return False
        price = ProfitForm.base_fields['selling_price'].clean(source['price'])
        if format(price, 'f') != source['price']:
            return False
        identity = single_scope(source['url'], price, source['currency'], source['quote_scope'])
        return source['sku_id'] == (identity['sku'] or None) and len(json.dumps(source, ensure_ascii=False)) <= 12000
    except (KeyError, TypeError, ValueError, ValidationError):
        return False


def catalog_report_link(reference):
    quote = reference['quote']
    for index, item in enumerate(quote.discovery.products):
        try:
            if candidate_url(item.get('url', '')) == quote.url:
                return reverse('catalog_detail', args=[quote.discovery_id, index])
        except ValidationError:
            continue
    return ''


def catalog_profit_link(quote, candidate=None):
    try:
        validate_quote(quote)
    except ValidationError:
        return ''
    params = {'catalog': quote.pk}
    if candidate:
        params['candidate'] = candidate.pk
    return reverse('profit') + '?' + urlencode(params)


def candidate_profit_link(candidate):
    quote = observations_for_url(candidate.url).filter(discovery__url=candidate.store_url).first()
    return catalog_profit_link(quote, candidate) if quote else ''
