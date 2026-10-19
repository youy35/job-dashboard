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
NOISE = re.compile(r'申办|流程|政策|事业单位公开招聘$|报考准备|重要提示|合格分数|成绩公告|拟聘|拟录用|公示|考试成绩|面试名单|体检|资格复审|取消|撤销|招聘办法|报考指南|招聘流程|招聘系统|人才招聘网|^人才招聘$|^招聘信息$|^博士后招聘$|招聘工作(?!人员)|\b(hiring freeze|layoffs|how to|guide|tips)\b',re.I)

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
        if source.get('channel_group')=='human_resources' and not re.search(r'招聘|招考|招录|招募|招收|引进.*人才|人才.*引进',title):continue
        if source['group']=='国内' and source.get('channel_group')!='human_resources' and not re.search(r'博物|文化|文物|考古|历史|大学|学院|高校|科研|博士|教育|行政|管理|国际|艺术|图书|档案|交流|留学',title):continue
        if source['group']=='国内' and source.get('channel_group')!='human_resources' and re.search(r'医院|疾控|疾病|结核|医学',title):continue
        if source['group']=='海外' and not re.search(r'\b(histor\w*|archaeolog\w*|heritage|humanit\w*|museums?|arts?|curat\w*|asian|china|chinese|program\w*|project\w*|coordinat\w*|administr\w*|communicat\w*|fellow\w*|scholarship\w*|intern\w*|volunteer\w*|education\w*|fund\w*)\b',title,re.I):continue
        if re.search(r'/(?:list|index)(?:[_.]|/|$)|/col/|\.(?:pdf|docx?|xlsx?|zip)(?:\?|$)',urllib.parse.urlsplit(url).path,re.I):continue
        if url in seen:continue
        seen.add(url);results.append({'title':title,'url':url,'published_at':''})
    return results[:source.get('max_items',30)]


def recruitment_columns(html,source,base_url):
    """Follow at most two same-domain recruitment columns; never recurse."""
    parser=ListingLinks();parser.feed(html);out=[]
    for href,title in parser.links:
        url=urllib.parse.urljoin(base_url,href).split('#')[0]
        if not allowed_host(url,source['domain']) or url.rstrip('/')==base_url.rstrip('/'):continue
        if not re.fullmatch(r'(?:事业单位|事业单位人事管理|事业单位公开招聘|事业单位招聘|公开招聘|招考招聘|招录公告|招聘公告|招聘信息|人事考试|通知公告|通知通告|招考录用|人才招聘|更多[>》]*)',title):continue
        if re.search(r'\.(?:pdf|docx?|xlsx?|zip)$',url,re.I):continue
        if url not in out:out.append(url)
    # Recruitment columns before broad notices.
    out.sort(key=lambda u:next((bool(re.search('通知|更多',t)) for h,t in parser.links if urllib.parse.urljoin(base_url,h).split('#')[0]==u),True))
    return out[:2]


def basic_information(title,source):
    """Only title-derived labels and publisher metadata, never applicant eligibility."""
    kind=('补充 / 调整通知' if re.search(r'延期|延长|补充|调整|更正',title) else
          '博士后招收' if '博士后' in title else '人才引进' if re.search(r'引进|高层次人才',title) else
          '公开招聘' if re.search(r'招聘|招考|招录',title) else '招募 / 项目申请')
    sector=('文博文化' if re.search('博物|文物|考古|文化馆|图书|档案|艺术',title) else
            '医疗卫生' if re.search('医院|医学|卫生|疾控',title) else
            '教育科研' if re.search('大学|学院|高校|学校|教师|科研|研究院|教育|校长',title) else '综合 / 其他')
    tags=[x for x in ('博士','硕士','应届','不限专业','编外','合同制','劳务派遣') if x in title]
    region=source.get('region','')
    summary='；'.join([kind,sector]+(['发布地区：'+region] if region else [])+(['标题提及：'+ '、'.join(tags)] if tags else []))
    return dict(announcement_type=kind,sector=sector,source_region=region,channel_group=source.get('channel_group',''),title_tags=tags,basic_summary=summary+'。分类来自标题，具体岗位、编制及条件请查看公告。')


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
        column_errors=[];visited_columns=[]
        if source.get('discover_columns'):
            for column in recruitment_columns(content,source,final_url):
                try:
                    page,redirect,_=request(column)
                    if not allowed_host(redirect,source['domain']):raise ValueError('栏目跳转域名不匹配')
                    visited_columns.append(column)
                    items=listing_items(page,source,redirect)+items
                except Exception as error:column_errors.append(str(error)[:150])
            items=list({item['url']:item for item in items}.values())[:source.get('max_items',15)]
    else:
        query='site:'+source['domain']+' '+source['terms']
        url='https://www.bing.com/search?'+urllib.parse.urlencode({'format':'rss','q':query})
        content,_,_=request(url);items,raw_count=web_index_items(content,source)
    jobs=[]
    for item in items:
        jobs.append({
            'org':'机构待核实','role':item['title'][:200],'country':'中国' if source.get('channel_group')=='human_resources' else '待核实',
            'city':'待核实','track':source['track'],'url':item['url'],
            'source':source['name'],'source_id':source['id'],'source_kind':source['source_kind'],
            'discovery_method':source['method'],'verification_status':'lead','verified':'','status':'待核实',
            'official_url':item['url'] if source['source_kind']=='official' else '',
            'deadline':'','salary':'待核实','published_at':item['published_at'],'indexed_at':item.get('indexed_at',''),
            **unknown_fields,**basic_information(item['title'],source),'estimated_self_cost_cny':None,
            'notes':'从公开列表或站点限定索引发现的线索。官方域名仅标识渠道，不代表已核实岗位有效、本人资格或费用。公众号及聚合平台须追溯招聘单位原公告。',
        })
    report={'source_id':source['id'],'source':source['name'],'method':source['method'],'status':'ok','leads':len(jobs),'url':source['url']}
    if source['method']=='html':
        report['visited_columns']=visited_columns if source.get('discover_columns') else []
        if source.get('discover_columns') and column_errors:
            report['column_errors']=column_errors;report['coverage']='partial'
    if raw_count is not None:report['indexed_results']=raw_count
    if raw_count and not jobs:
        report['coverage']='unconfirmed'
        report['note']='返回内容未通过域名或相关性检查，不能确认该渠道已覆盖'
    report.setdefault('note','仅发现线索；未核实开放状态或个人资格' if jobs else '本次无匹配结果；不代表没有招聘，也可能未被索引或静态页面不含职位')
    return jobs,report
