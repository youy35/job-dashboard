"""Discover opportunity leads, never infer eligibility or funding from news titles."""
import argparse
import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
try:
    from .source_channels import load_sources, collect_source
except ImportError:
    from source_channels import load_sources, collect_source

OUTPUT = Path(__file__).resolve().parents[1] / 'jobs-feed.json'
SEARCHES = [
    {'query': q, 'track': track, 'lang': lang, 'kind': kind}
    for q, track, lang, kind in [
        ('考古 博士 招聘', '科研', 'zh', 'job'),
        ('博物馆 研究人员 招聘', '博物馆', 'zh', 'job'),
        ('高校 国际交流 行政 招聘', '高校行政', 'zh', 'job'),
        ('艺术史 博士后 招聘', '博士后', 'zh', 'job'),
        ('East Asian studies postdoctoral position', '博士后', 'en', 'job'),
        ('Asian art museum curator vacancy', '博物馆', 'en', 'job'),
        ('cultural heritage research job', '海外非学术', 'en', 'job'),
        ('university research coordinator hiring', '海外非学术', 'en', 'job'),
        ('international NGO program officer jobs visa sponsorship', '全球跨专业工作', 'en', 'job'),
        ('international education operations coordinator jobs relocation', '全球跨专业工作', 'en', 'job'),
        ('animal welfare conservation project assistant jobs international', '全球跨专业工作', 'en', 'job'),
        ('paid internship international applicants any discipline', '全球跨专业工作', 'en', 'job'),
        ('UNV international volunteer applications living allowance', '资助志愿者', 'en', 'volunteer'),
        ('international volunteer opportunities funded accommodation travel', '资助志愿者', 'en', 'volunteer'),
        ('国际 志愿者 招募 资助 食宿', '资助志愿者', 'zh', 'volunteer'),
        ('fully funded fellowship scholarship applications international any discipline', '奖学金与交流培训', 'en', 'funded'),
        ('funded exchange training summer school residency call applications', '奖学金与交流培训', 'en', 'funded'),
        ('国际 交流 培训 奖学金 全额资助 申请', '奖学金与交流培训', 'zh', 'funded'),
        ('中国 青年 国际交流 项目 资助 公开招募', '国内国际项目', 'zh', 'china'),
        ('基金会 国际组织 海外 派遣 培训 招募 资助', '国内国际项目', 'zh', 'china'),
        ('高校 国际交流 项目 社会人员 个人申请 资助', '国内国际项目', 'zh', 'china'),
    ]
]
JOB_WORDS = re.compile(
    r'招聘|招募|聘用|岗位|职位|博士后|\b(vacanc(?:y|ies)|hiring|recruitment|job openings?|job listings?|job postings?|jobs in|apply|'
    r'internships?|postdoc\w*|applications? invited)\b', re.I)
OPPORTUNITY_WORDS = re.compile(
    r'招募|申请|报名|征集|招收|\b(apply|applications?|opportunit\w*|call|open)\b', re.I)
TOPIC_WORDS = {
    'volunteer': re.compile(r'志愿|\b(volunteer\w*|UNV)\b', re.I),
    'funded': re.compile(r'奖学金|交流|培训|驻留|访学|暑期|\b(scholarship\w*|fellowship\w*|exchange|training|residenc\w*|summer school)\b', re.I),
    'china': re.compile(r'国际|海外|出国|交流|外事'),
}
NOISE = re.compile(r'招聘冻结|招聘骗局|\b(hiring freeze|hiring scam|job cuts|layoffs)\b', re.I)
COST_POLICY = {
    'currency': 'CNY', 'preferred_range': [3000, 15000], 'hard_limit': None,
    'notes': '低于3000元同样优先；3000–8000元优先，其次8000–15000元；更高费用不自动排除。比较总自费、时长及海外发展价值；费用未知不视为免费。',
}
UNKNOWN_FIELDS = {
    'nationality': '待核实：中国公民及中国大陆居民能否申请',
    'age': '待核实：年龄限制',
    'language': '待核实：语言及证明要求',
    'eligibility': '待核实：专业、学历、毕业时间、经验、在读/在职及单位推荐要求',
    'visa': '待核实：合法工作/活动许可、是否协助及费用',
    'funding': '待核实：补贴、食宿、交通、保险、资助期限及报销条件',
    'costs': '待核实：项目费、机票、签证、食宿、保险、当地交通和报销前垫付',
    'duration': '待核实：起止时间及持续时长',
    'development_value': '待评估：可迁移技能、人脉、海外就业及后续签证路径',
}


def valid_url(url):
    try:
        parts = urllib.parse.urlsplit(url)
        return parts.scheme in ('http', 'https') and bool(parts.hostname)
    except ValueError:
        return False


def fetch_rss(query, lang):
    settings = ({'hl': 'zh-CN', 'gl': 'CN', 'ceid': 'CN:zh-Hans'} if lang == 'zh'
                else {'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})
    settings['q'] = query + ' when:90d'
    request = urllib.request.Request(
        'https://news.google.com/rss/search?' + urllib.parse.urlencode(settings),
        headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/rss+xml, application/xml'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def parse_rss(content, search):
    root = ET.fromstring(content)
    # A consent/error HTML page is not a successful empty RSS response.
    if root.tag != 'rss' or root.find('channel') is None:
        raise ValueError('响应不是 RSS，保留旧数据')
    jobs = []
    kind = search.get('kind', 'job')
    for item in root.findall('./channel/item'):
        title = (item.findtext('title') or '').strip()
        link = (item.findtext('link') or '').strip()
        if not title or not valid_url(link) or NOISE.search(title):
            continue
        if kind == 'job':
            relevant = JOB_WORDS.search(title)
        else:
            relevant = TOPIC_WORDS[kind].search(title) and OPPORTUNITY_WORDS.search(title)
        if not relevant:
            continue
        source = (item.findtext('source') or '').strip()
        jobs.append({
            'org': '机构待核实', 'role': title[:200], 'country': '待核实',
            'city': '待核实', 'track': search['track'], 'url': link,
            'source': 'Google News RSS / ' + (source or '来源待核实'),
            'verification_status': 'lead', 'verified': '', 'official_url': '',
            'status': '待核实', 'deadline': '', 'salary': '待核实',
            'published_at': (item.findtext('pubDate') or '').strip(),
            'search_query': search['query'], 'opportunity_type': kind,
            **UNKNOWN_FIELDS,
            'estimated_self_cost_cny': None,
            'notes': '自动发现的机会线索，并非已核实的在招岗位或开放项目。搜索方向不代表专业不限、适合本人或中国申请者合格；标题声称资助不代表已确认。须查官方当期公告核实资格、截止日期、签证、资助及总自费，排查高额中介费和商业游学。',
        })
    return jobs


def merge_leads(existing, found):
    # Fresh discoveries first so a full historical feed cannot crowd them out.
    old = {j['url']: j for j in existing if isinstance(j, dict) and valid_url(j.get('url', ''))}
    merged = {}
    for job in found:
        url = job['url']
        if url not in merged:
            # Preserve any manually verified facts and notes, including unknown extensions.
            merged[url] = {**job, **old.get(url, {})}
            # Refresh source provenance without changing user-maintained facts.
            for key in ('source_id', 'source_kind', 'discovery_method', 'announcement_type', 'sector', 'source_region', 'channel_group', 'title_tags', 'basic_summary'):
                if key in job: merged[url][key] = job[key]
    for url, job in old.items():
        merged.setdefault(url, job)
    return list(merged.values())[:1000]


def main(output=OUTPUT, searches=None, include_channels=None):
    include_channels = searches is None if include_channels is None else include_channels
    searches = SEARCHES if searches is None else searches
    existing = []
    if output.exists():
        payload = json.loads(output.read_text(encoding='utf-8'))
        existing = payload.get('jobs')
        if not isinstance(existing, list):
            raise ValueError('现有文件缺少 jobs 数组，停止以免丢失数据')
    found, reports = [], []
    for search in searches:
        try:
            jobs = parse_rss(fetch_rss(search['query'], search['lang']), search)
            found.extend(jobs)
            reports.append({'query': search['query'], 'status': 'ok', 'leads': len(jobs)})
            print(f"OK {search['track']}: {len(jobs)} leads; {search['query']}")
        except Exception as error:
            reports.append({'query': search['query'], 'status': 'failed', 'error': str(error)[:300]})
            print(f"FAILED {search['query']}: {error}")
    sources = load_sources() if include_channels else []
    def run_source(source):
        try:
            return collect_source(source, UNKNOWN_FIELDS)
        except Exception as error:
            return [], {'source_id': source['id'], 'source': source['name'], 'url': source['url'],
                        'method': source['method'], 'status': 'failed', 'error': str(error)[:300]}
    if sources:
        with ThreadPoolExecutor(max_workers=4) as pool:
            channel_results = list(pool.map(run_source, sources))
        # Put source-specific results before broad news discoveries.
        channel_jobs = []
        for jobs, report in channel_results:
            channel_jobs.extend(jobs); reports.append(report)
            print(f"{report['status'].upper()} {report['source']}: {len(jobs)} leads")
        found = channel_jobs + found
    if not any(r['status'] == 'ok' for r in reports):
        raise RuntimeError('全部来源请求失败，未更新机会数据')
    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'jobs': merge_leads(existing, found), 'cost_policy': COST_POLICY,
        'search_report': reports, 'sources': sources,
    }
    # Replace only after serialization succeeds.
    temp = output.with_suffix('.json.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(output)
    print(f"Saved {len(payload['jobs'])} leads; failures: {sum(r['status'] == 'failed' for r in reports)}")
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--channels-only', action='store_true', help='仅测试新增官网与站点索引渠道')
    mode.add_argument('--news-only', action='store_true', help='仅使用兼容的新闻检索')
    args = parser.parse_args()
    main(args.output, searches=[] if args.channels_only else None, include_channels=not args.news_only)
