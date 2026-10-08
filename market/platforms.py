"""平台链接识别与真实支持边界；识别域名不等于已接入采集。"""
from urllib.parse import urlsplit
from django.core.exceptions import ValidationError
from .ebay import EBAY_DOMAINS

PLATFORM_DOMAINS = {'SHEIN':('shein.com','shein.com.mx','shein.co.uk'),
                    'OTTO':('otto.de',), 'Ozon':('ozon.ru','ozon.com','ozon.kz','ozon.by'),
                    'AliExpress':('aliexpress.com','aliexpress.us'), 'eBay':EBAY_DOMAINS}


def known_platform(url):
    host=(urlsplit(url).hostname or '').lower().rstrip('.')
    for platform,domains in PLATFORM_DOMAINS.items():
        if any(host==domain or host.endswith('.'+domain) for domain in domains):
            return platform
    return None


def check_analysis_support(url):
    platform=known_platform(url)
    if platform in ('SHEIN','OTTO','Ozon','eBay'):
        raise ValidationError(f'已识别为 {platform}。该平台的店铺目录、价格与评价自动采集尚未接入；本次不会创建采集任务。可先手动记录或导入 CSV，不会按 Shopify 分析。')
    if platform=='AliExpress' and (urlsplit(url).hostname or '').lower().endswith('aliexpress.us'):
        raise ValidationError('已识别为 AliExpress 美国站；当前自动采集仅支持 aliexpress.com 商品链接，美国站尚未接入。')
    return platform
