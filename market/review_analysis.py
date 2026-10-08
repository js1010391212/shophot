"""本地评论样本统计：评分分组、词频及明确问题表述，不推断全量质量。"""
import re
from collections import Counter
from .catalog_content import plain_text, same_product
from .reviews import five_star_rating

STOP_WORDS=set('a an and are as at be been being but by can could did do does for from had has have he her here him his how i if in into is it its just like me more most my of on one or our out really she so some than that the their them then there these they this those through to too very was we were what when which while who will with would you your also all am any because bought buy get got much now only product products'.split())
STOP_WORDS.update(("don't","doesn't","didn't","it's","i'm","i've","that's","can't"))
LEMMA={'combs':'comb','hairs':'hair','beards':'beard','sizes':'size','smells':'smell','scents':'scent','works':'work','prices':'price','using':'use','used':'use','pulling':'pull','tangles':'tangle','designs':'design'}
CHINESE=('质量','做工','材质','耐用','断裂','破损','尺寸','大小','太小','太大','合适','好用','难用','顺滑','卡顿','方便','清洁','气味','香味','刺鼻','持久','价格','便宜','贵','性价比','物流','配送','包装','客服','满意','失望','推荐')
TOPICS={
 '品质与耐用':('quality','durable','material','broke','broken','flimsy','质量','做工','材质','耐用','断裂','破损'),
 '尺寸与适配':('size','small','big','large','fit','pocket','尺寸','大小','太小','太大','合适'),
 '使用体验':('use','smooth','smooooth','pull','tangle','work','easy','clean','好用','難用','难用','顺滑','卡顿','方便','清洁'),
 '气味与持久':('smell','scent','fragrance','lasting','气味','香味','刺鼻','持久'),
 '价格与价值':('price','value','worth','expensive','cheap','价格','便宜','贵','性价比'),
 '物流与包装':('shipping','delivery','package','packaging','物流','配送','包装'),
}
ISSUES={
 '尺寸偏小表述':r'\btoo small\b|\bsmaller than\b|太小|尺寸偏小',
 '尺寸偏大表述':r'\btoo (?:big|large)\b|太大|尺寸偏大',
 '效果不足表述':r"\b(?:doesn['’]t|does not|didn['’]t|did not) (?:work|do enough)\b|不好用|效果不好|没有效果",
 '气味不适表述':r'\bbad smell\b|\btoo strong\b|刺鼻|难闻',
 '破损表述':r'\bbroken\b|\bbroke\b|\bdamaged\b|破损|断裂',
}
PRAISE={
 '品质肯定表述':r'\b(?:good|great|nice|amazing|excellent|top notch) quality\b|质量好|质量不错|做工好',
 '使用顺滑表述':r'\bsmooth\b|\bsmooooth\b|\bno (?:pulling|tangles?|snagging)\b|顺滑|好用',
 '便于携带表述':r'\bgreat size to carry\b|\beasy to carry\b|\bportable\b|便携|方便携带',
 '价格值得表述':r'\bworth every penny\b|\bgood value\b|\bworth the price\b|性价比高|物有所值',
}


def tokens(text):
    words={LEMMA.get(word,word) for word in re.findall(r'[a-z][a-z\']{2,}',text.casefold())}
    words-=STOP_WORDS
    words.update(word for word in CHINESE if word in text)
    return words


def explicit_phrase(text, pattern):
    for match in re.finditer(pattern,text,re.I):
        prefix=text[max(0,match.start()-30):match.start()]
        if not re.search(r'\b(?:not|no|never|without)(?:\s+\w+){0,2}\s*$|(?:并不|不是|没有|不)\s*$',prefix,re.I):
            return True
    return False


def analyze_reviews(item):
    source=item.get('url','')
    excluded=tokens((item.get('price_title') or item.get('title') or '')+' '+(item.get('brand') or ''))
    samples=[];seen=set()
    raw=item.get('review_samples',[])
    raw=raw if isinstance(raw,list) else []
    for index,sample in enumerate(raw[:10]):
        if not isinstance(sample,dict):continue
        if sample.get('source_url') and not same_product(sample['source_url'],source):continue
        body=plain_text(sample.get('body'),2000)
        if not body or body.casefold() in seen:continue
        seen.add(body.casefold())
        text=plain_text(sample.get('title'))+' '+body
        rating=five_star_rating({'ratingValue':sample.get('rating')})
        group='unknown' if rating is None else 'positive' if float(rating)>=4 else 'low' if float(rating)<=2 else 'middle'
        samples.append({'index':index,'tokens':tokens(text),'text':text,'group':group})
    groups=Counter(sample['group'] for sample in samples)
    frequency=Counter(word for sample in samples for word in sample['tokens']-excluded)
    count=len(samples)
    keywords=[{'word':word,'count':freq,'share':round(freq*100/count,1),
               'evidence':[s['index'] for s in samples if word in s['tokens']]}
              for word,freq in sorted(frequency.items(),key=lambda pair:(-pair[1],pair[0])) if freq>=2][:20]
    topics=[]
    for name,words in TOPICS.items():
        evidence=[s['index'] for s in samples if s['tokens'].intersection(words)]
        if evidence:topics.append({'name':name,'count':len(evidence),'evidence':evidence})
    issues=[]
    for name,pattern in ISSUES.items():
        evidence=[]
        for sample in samples:
            # 用户明确归因自己的损坏，不标成商品质量问题。
            if name=='破损表述' and re.search(r'my (?:own|fault)|own doing|i dropped|自己弄坏',sample['text'],re.I):continue
            if explicit_phrase(sample['text'],pattern):evidence.append(sample['index'])
        if evidence:issues.append({'name':name,'count':len(evidence),'evidence':evidence})
    praise=[]
    for name,pattern in PRAISE.items():
        evidence=[s['index'] for s in samples if explicit_phrase(s['text'],pattern)]
        if evidence:praise.append({'name':name,'count':len(evidence),'evidence':evidence})
    labels=['4–5 分样本','大于 2 且小于 4 分样本','0–2 分样本','未提供评分']
    counts=[groups[key] for key in ('positive','middle','low','unknown')]
    return {'sample_count':count,'rated_count':count-groups['unknown'],
            'positive_count':groups['positive'],'low_count':groups['low'], 'unknown_count':groups['unknown'],
            'keywords':keywords,'topics':topics,'issues':issues,'praise':praise,
            'chart':{'labels':labels,'counts':counts,'words':[k['word'] for k in keywords],
                     'frequencies':[k['count'] for k in keywords],'evidence':[k['evidence'] for k in keywords]}}
