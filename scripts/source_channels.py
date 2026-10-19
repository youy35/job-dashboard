"""Public listing adapters. A source classification is not applicant verification."""
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

SOURCES_FILE = Path(__file__).with_name('sources.json')
RECRUIT = re.compile(r'招聘|招募|引进|征集|申请|\b(jobs?|vacanc\w*|recruit\w*|hiring|apply|applications?|fellowship\w*|scholarship\w*|position\w*)\b', re.I)
NOISE = re.compile(r'申办|流程|政策|事业单位公开招聘$|报考准备|重要提示|合格分数|成绩公告|拟聘|拟录用|公示|考试成绩|面试名单|体检|资格复审|取消|撤销|招聘办法|报考指南|招聘流程|招聘系统|人才招聘网|^人才招聘$|^招聘信息$|^博士后招聘$|招聘工作|\b(hiring freeze|layoffs|how to|guide|tips)\b',re.I)

def load_sources():
    return json.loads(SOURCES_FILE.read_text(encoding='utf-8'))


def allowed_host(url, domain):
    try:
        u=urllib.parse.urlsplit(url)
        return u.scheme in ('https','http') and bool(u.hostname) and (u.hostname==domain or u.hostname.endswith('.'+domain))
    except ValueError:return False


def request(url):
    req=urllib.request.Request(url,headers={'User-Agent':'JobOpportunityRadar/2.0 (public recruitment listings; low frequency)','Accept':'text/html,application/rss+xml,application/xml'})
    with urllib.request.urlopen(req,timeout=18) as response:
        content=response.read(3_000_001)
        if len(content)>3_000_000:raise ValueError('来源响应过大，跳过')
        content_type=response.headers.get('Content-Type','')
        charset=response.headers.get_content_charset()
        if not charset:
            m=re.search(rb'charset\s*=\s*["\x27]?([A-Za-z0-9_-]+)',content[:4096])
            charset=m.group(1).decode() if m else 'utf-8'
        return content.decode(charset,errors='replace'),response.url,content_type


class ListingLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.links=[];self.current=None
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            d=dict(attrs);self.current={'href':d.get('href',''),'title':d.get('title',''),'text':[]}
    def handle_data(self,text):
        if self.current is not None:self.current['text'].append(text)
    def handle_endtag(self,tag):
        if tag=='a' and self.current is not None:
            c=self.current;self.links.append((c['href'],re.sub(r'\s+',' ',c['title'] or ''.join(c['text'])).strip()));self.current=None


def listing_items(html,source,base_url=None):
    if re.search(r'<title[^>]*>[^<]*(?:captcha|access denied|just a moment|验证|访问受限)',html,re.I):
        raise ValueError('来源要求浏览器验证，未绕过')
    parser=ListingLinks();parser.feed(html)
    if not parser.links:raise ValueError('未发现静态列表；可能依赖脚本，需人工打开')
    results=[];seen=set()
    for href,title in parser.links:
        url=urllib.parse.urljoin(base_url or source['url'],href).split('#')[0]
        if not allowed_host(url,source['domain']) or not (8<=len(title)<=250):continue
        if source.get('entry_pattern') and not re.search(source['entry_pattern'],url,re.I):continue
        if not (RECRUIT.search(title) or (source.get('entry_pattern') and re.search(source['entry_pattern'],url,re.I))) or NOISE.search(title):continue
        if url.rstrip('/')==(base_url or source['url']).rstrip('/'):continue
        if source['group']=='国内' and not re.search(r'博物|文化|文物|考古|历史|大学|学院|高校|科研|博士|教育|行政|管理|国际|艺术|图书|档案|交流|留学',title):continue
        if source['group']=='国内' and re.search(r'医院|疾控|疾病|结核|医学',title):continue
        if source['group']=='海外' and not re.search(r'\b(histor\w*|archaeolog\w*|heritage|humanit\w*|museums?|arts?|curat\w*|asian|china|chinese|program\w*|project\w*|coordinat\w*|administr\w*|communicat\w*|fellow\w*|scholarship\w*|intern\w*|volunteer\w*|education\w*|fund\w*)\b',title,re.I):continue
        if re.search(r'/(?:list|index)(?:[_.]|/|$)|/col/|\.(?:pdf|docx?|xlsx?|zip)(?:\?|$)',urllib.parse.urlsplit(url).path,re.I):continue
        if url in seen:continue
        seen.add(url);results.append({'title':title,'url':url,'published_at':''})
    return results[:30]


def web_index_items(xml,source):
    root=ET.fromstring(xml)
    if root.tag!='rss' or root.find('channel') is None:raise ValueError('搜索服务未返回有效 RSS')
    items=root.findall('./channel/item');results=[]
    for item in items:
        url=(item.findtext('link') or '').strip();title=(item.findtext('title') or '').strip()
        # Search engines can ignore site:; never mislabel an off-domain result as official.
        if not allowed_host(url,source['domain']) or not RECRUIT.search(title) or NOISE.search(title):continue
        path=urllib.parse.urlsplit(url).path
        if path in ('','/') or re.search(r'/(list|index)([_.]|/|$)|/col/',path,re.I):continue
        results.append({'title':title,'url':url,'published_at':'','indexed_at':(item.findtext('pubDate') or '').strip()})
    return results[:10],len(items)


def collect_source(source,unknown_fields):
    if source['method']=='html':
        content,final_url,_=request(source['url'])
        if not allowed_host(final_url,source['domain']):raise ValueError('官方列表跳转到配置域名之外，需人工核对')
        items=listing_items(content,source,final_url);raw_count=None
    else:
        query='site:'+source['domain']+' '+source['terms']
        url='https://www.bing.com/search?'+urllib.parse.urlencode({'format':'rss','q':query})
        content,_,_=request(url);items,raw_count=web_index_items(content,source)
    jobs=[]
    for item in items:
        jobs.append({
            'org':'机构待核实','role':item['title'][:200],'country':'中国' if source['group']=='国内' else '待核实',
            'city':'待核实','track':source['track'],'url':item['url'],
            'source':source['name'],'source_id':source['id'],'source_kind':source['source_kind'],
            'discovery_method':source['method'],'verification_status':'lead','verified':'','status':'待核实',
            'official_url':item['url'] if source['source_kind']=='official' else '',
            'deadline':'','salary':'待核实','published_at':item['published_at'],'indexed_at':item.get('indexed_at',''),
            **unknown_fields,'estimated_self_cost_cny':None,
            'notes':'从公开列表或站点限定索引发现的线索。官方域名仅标识渠道，不代表已核实岗位有效、本人资格或费用。公众号及聚合平台须追溯招聘单位原公告。',
        })
    report={'source_id':source['id'],'source':source['name'],'method':source['method'],'status':'ok','leads':len(jobs),'url':source['url']}
    if raw_count is not None:report['indexed_results']=raw_count
    if raw_count and not jobs:
        report['coverage']='unconfirmed'
        report['note']='返回内容未通过域名或相关性检查，不能确认该渠道已覆盖'
    report.setdefault('note','仅发现线索；未核实开放状态或个人资格' if jobs else '本次无匹配结果；不代表没有招聘，也可能未被索引或静态页面不含职位')
    return jobs,report
