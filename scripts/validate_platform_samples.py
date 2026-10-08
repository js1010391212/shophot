"""小规模真实跨平台验收探针。只读；不入库，不绕过验证，不取 cookies。"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
import httpx
from bs4 import BeautifulSoup
from market.network import PublicProductTransport
from market.forms import AnalyzeForm
from market.collectors import MAX_BYTES

SAMPLES=[
 ('OTTO','FDS GmbH / COSTWAY','https://www.otto.de/p/costway-hundeschermaschine-hundepflegetisch-trimmtisch-arbeitstisch-klappbar-S08F10JE/'),
 ('OTTO','Guru-Shop','https://www.otto.de/p/guru-shop-kerzenlaterne-orientalische-metall-glas-laterne-in-S0R0I0F0/'),
 ('Ozon','Tefal','https://www.ozon.ru/seller/tefal-ofitsialnyy-magazin/'),
 ('Ozon','Xiaomi','https://www.ozon.ru/seller/xiaomi-ofitsialnyy-magazin/products/'),
 ('SHEIN','All boutiques','https://us.shein.com/store/home?contentIds=&pageType=topBanner&store_code=1061637975'),
 ('SHEIN','ALET TREND','https://m.shein.com.mx/store/home?store_code=9658247474'),
 ('AliExpress','UMIDIGI','https://www.aliexpress.com/store/4089001'),
]

def read(client,url):
    with client.stream('GET',url) as response:
        size=0;parts=[]
        for chunk in response.iter_bytes():
            size+=len(chunk)
            if size>MAX_BYTES:
                return response.status_code,'',{'too_large':True}
            parts.append(chunk)
        return response.status_code,b''.join(parts).decode('utf-8',errors='replace'),{'bytes':size,'type':response.headers.get('content-type',''),'redirect':urlsplit(response.headers.get('location','')).path[:500]}

results=[];robots={};blocked=set()
with httpx.Client(transport=PublicProductTransport(),trust_env=False,follow_redirects=False,timeout=httpx.Timeout(20,connect=10),headers={'User-Agent':'ShopHot/0.1 (+personal seller analytics)'}) as client:
    for platform,name,url in SAMPLES:
        result={'platform':platform,'sample':name,'url':url,'at':datetime.now(timezone.utc).isoformat()}
        form=AnalyzeForm({'platform':'Auto','url':url},allow_store=True)
        result['app_accepted']=form.is_valid();result['app_errors']=form.errors.get_json_data()
        root='https://'+urlsplit(url).netloc
        try:
            if root not in robots:
                status,body,meta=read(client,root+'/robots.txt')
                policy=RobotFileParser();policy.set_url(root+'/robots.txt')
                if status==200 and not meta.get('too_large'):
                    policy.parse(body.splitlines());robots[root]=policy
                elif status==404:
                    robots[root]=True
                else:
                    robots[root]=False
                result['robots_status']=status
            policy=robots[root]
            if root in blocked:
                result['network']='同域此前返回访问限制，停止重复请求'
            elif policy is False or policy is not True and not policy.can_fetch('ShopHot',url):
                result['network']='robots 不允许或规则无法确认，未请求商品/店铺页'
            else:
                status,body,meta=read(client,url);result.update(http_status=status,**meta)
                if status in (403,429):
                    blocked.add(root)
                soup=BeautifulSoup(body,'html.parser')
                result['title']=soup.title.get_text(' ',strip=True)[:250] if soup.title else ''
                result['json_ld_blocks']=len(soup.find_all('script',type='application/ld+json'))
                result['challenge']=any(token in body.lower() for token in ('_____tmd_____','x5secdata','captcha','access denied','challenge-platform')) or 'challenge' in meta.get('redirect','')
        except Exception as exc:
            result['network_error']=type(exc).__name__
        results.append(result)
        print(json.dumps(result,ensure_ascii=False),flush=True)
Path('.local/platform-validation/http-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
