"""仅统计已发现商品标题，不把词频解释为市场搜索量。"""
import re
from collections import Counter
from urllib.parse import urlsplit
from decimal import Decimal, ROUND_CEILING
from django.core.exceptions import ValidationError
from .validation import clean_price, clean_rating, clean_count
from .review_analysis import analyze_reviews

AVAILABILITY = {'InStock':'有货','OutOfStock':'缺货','SoldOut':'售罄',
                'PreOrder':'预售','BackOrder':'可延期订购','Mixed':'不同规格状态不同'}

STOP_WORDS = set('a an and are as at be by for from in is it of on or the to with your our new'.split())


def title_terms(title, store_url):
    # 使用英语单词和连续中文词组；未做中文语义分词或自动翻译。
    brand_words = set(re.findall(r'[a-z]+', urlsplit(store_url).hostname or ''))
    normalized = re.sub(r"([a-z]+)[’']s\b", r'\1s', title.lower())
    return set(re.findall(r'[a-z][a-z0-9]{2,}|[\u4e00-\u9fff]{2,}', normalized)) - STOP_WORDS - brand_words


def numeric(value, cleaner):
    try:
        return cleaner(value) if value not in (None, '') else None
    except (ValidationError, TypeError, ValueError):
        return None


def price_distribution(products):
    groups = {}
    for p in products:
        if p['_low'] is not None and p.get('currency'):
            groups.setdefault(p['currency'], []).append(p['_low'])
    distributions = []
    for currency, values in sorted(groups.items()):
        low, high = min(values), max(values)
        if low == high:
            labels, counts = [f'{low:.2f}'], [len(values)]
        else:
            step = ((high-low+Decimal('.01'))/5).quantize(Decimal('.01'), rounding=ROUND_CEILING)
            counts = [0]*5
            for value in values:
                counts[min(4, int((value-low)/step))] += 1
            labels = [f'{low+step*i:.2f} ≤ 价格 < {low+step*(i+1):.2f}' for i in range(5)]
        distributions.append({'currency': currency, 'labels': labels, 'counts': counts, 'total':len(values),
                              'rows':[{'label':label,'count':count} for label,count in zip(labels,counts)]})
    return distributions


def sort_products(products, sort, currency):
    fields = {'price_asc':('_low',False), 'price_desc':('_low',True), 'rating_desc':('_rating',True), 'reviews_desc':('_reviews',True)}
    if sort in fields and (not sort.startswith('price_') or currency):
        field, descending = fields[sort]
        products.sort(key=lambda p:(p[field] is None, -(p[field] or 0) if descending else (p[field] or 0)))
    elif sort == 'title':
        products.sort(key=lambda p:p['display_title'].casefold())


def build_research(scan, term='', currency='', *, q='', price_min=None, price_max=None,
                   min_rating=None, min_reviews=None, sort='catalog', availability='', coverage=''):
    products = []
    seen = set()
    for catalog_index, item in enumerate(scan.products):
        if item.get('url') in seen or not item.get('url'):
            continue
        seen.add(item['url'])
        title = item.get('price_title') or item.get('title') or ''
        low = numeric(item.get('price_low'), clean_price) if item.get('price_observed_at') else None
        high = numeric(item.get('price_high'), clean_price) if item.get('price_observed_at') else None
        if high is None or low is None or high < low:
            low = high = None
        state = item.get('availability') if item.get('price_observed_at') else None
        state = state if state in AVAILABILITY else 'unknown'
        sample_count = analyze_reviews(item)['sample_count']
        products.append({**item, 'display_title': title, 'catalog_index': catalog_index, 'terms': title_terms(title, scan.url),
                         'inventory_state':state, 'inventory_label':AVAILABILITY.get(state,'未知'),
                         'review_sample_count':sample_count,
                         '_low':low, '_high':high, '_rating':numeric(item.get('rating'), clean_rating),
                         '_reviews':numeric(item.get('review_count'), clean_count),
                         'has_rating': numeric(item.get('rating'), clean_rating) is not None,
                         'has_reviews': numeric(item.get('review_count'), clean_count) is not None})
    frequencies = Counter(token for product in products for token in product['terms'])
    count = len(products)
    keywords = [{'term': word, 'count': freq, 'share': round(freq * 100 / count, 1)}
                for word, freq in sorted(frequencies.items(), key=lambda pair: (-pair[1], pair[0]))]
    currencies = sorted({p['currency'] for p in products if p.get('price_observed_at') and p.get('currency')})
    filtered = [p for p in products if (not term or term in p['terms']) and (not currency or p.get('currency') == currency)]
    filtered = [p for p in filtered if (not q or q.casefold() in p['display_title'].casefold())
                and (not availability or p['inventory_state'] == availability)
                and (price_min is None or p['_high'] is not None and p['_high'] >= price_min)
                and (price_max is None or p['_low'] is not None and p['_low'] <= price_max)
                and (min_rating is None or p['_rating'] is not None and p['_rating'] >= min_rating)
                and (min_reviews is None or p['_reviews'] is not None and p['_reviews'] >= min_reviews)]
    if coverage:
        filtered = [p for p in filtered if {
            'quoted': p['_low'] is not None and bool(p.get('currency')),
            'unquoted': p['_low'] is None or not p.get('currency'),
            'reviews': p['review_sample_count'] > 0,
            'no_reviews': p['review_sample_count'] == 0,
            'failed': bool(p.get('price_error')),
            'unattempted': not p.get('price_attempted_at') and not p.get('price_observed_at'),
        }.get(coverage, False)]
    sort_products(filtered, sort, currency)
    groups = {}
    for index, product in enumerate(filtered):
        product['row_id'] = f'catalog-product-{index}'
        # 每件商品只在树中出现一次，归入其标题覆盖商品数最多的词。
        primary = min(product['terms'], key=lambda word: (-frequencies[word], word)) if product['terms'] else '未提取词条'
        group = groups.setdefault(primary, [])
        group.append({'name': product['display_title'], 'kind': 'product', 'rowId': product['row_id']})
    tree = {'name': urlsplit(scan.url).hostname or scan.url, 'kind': 'root', 'children': [
        {'name': f'{word} · {len(children)} 件', 'term': word if word != '未提取词条' else '', 'kind': 'term', 'children': children}
        for word, children in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))]}
    return {'products': filtered, 'keywords': keywords[:40], 'keyword_count': len(keywords),
            'total_count': count, 'matched_count': len(filtered), 'currencies': currencies,
            'priced_count': sum(bool(p.get('price_observed_at')) for p in products),
            'tree_data': tree, 'tree_height': max(420, min(1100, len(filtered) * 24)),
            'distribution': price_distribution(filtered),
            'matched_priced_count': sum(p['_low'] is not None for p in filtered),
            'term': term, 'currency': currency}
