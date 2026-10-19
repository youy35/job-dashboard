import unittest
from scripts.source_channels import listing_items,web_index_items,allowed_host

SOURCE={'url':'https://hr.example.edu/jobs/','domain':'hr.example.edu','group':'国内','name':'示例官网'}
class ChannelTests(unittest.TestCase):
 def test_only_same_domain_and_actual_announcements(self):
  html='''<a href="/jobs/">事业单位公开招聘</a><a href="/2026/1.html" title="博物馆2026年招聘博士公告">简称</a><a href="/2026/2.html">博物馆拟录用人员公示</a><a href="https://fake.example/jobs/1">历史学院招聘博士公告</a><a href="/2026/3.html">引进人才申办流程及材料清单</a><a href="/2026/4.html">大学附属医院2026年公开招聘公告</a>'''
  items=listing_items(html,SOURCE)
  self.assertEqual([x['title'] for x in items],['博物馆2026年招聘博士公告'])
  self.assertEqual(items[0]['published_at'],'')
 def test_ignore_offdomain_index_results(self):
  content='<rss><channel><item><title>博物馆招聘</title><link>https://fake.example/job</link></item><item><title>历史学院招聘博士</title><link>https://hr.example.edu/2026/a.html</link><pubDate>today</pubDate></item></channel></rss>'
  rows,count=web_index_items(content,SOURCE)
  self.assertEqual(count,2);self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]['published_at'],'');self.assertEqual(rows[0]['indexed_at'],'today')
 def test_foreign_job_title_uses_job_path(self):
  source={**SOURCE,'group':'海外','entry_pattern':r'/job/'}
  rows=listing_items('<a href="/job/1">Programme Coordinator</a><a href="/job/2">Clinical Surgeon</a>',source)
  self.assertEqual([x['title'] for x in rows],['Programme Coordinator'])
 def test_bad_hosts_and_captcha(self):
  self.assertFalse(allowed_host('https://hr.example.edu.attacker.org/a','hr.example.edu'))
  self.assertFalse(allowed_host('javascript:alert(1)','hr.example.edu'))
  with self.assertRaises(ValueError):listing_items('<title>Access Denied</title>',SOURCE)

class ExpandedHRTests(unittest.TestCase):
 def test_all_provinces_and_unique_registry(self):
  from scripts.source_channels import load_sources
  sources=load_sources();hr=[s for s in sources if s.get('channel_group')=='human_resources']
  self.assertEqual(len({s['region'] for s in hr if s['level']=='省级'}),31)
  self.assertGreaterEqual(len(hr),43)
  self.assertEqual(len({s['id'] for s in sources}),len(sources))
  self.assertEqual(len({s['url'] for s in hr}),len(hr))
 def test_hr_keeps_general_announcements_without_inventing_facts(self):
  from scripts.source_channels import basic_information
  hr={**SOURCE,'channel_group':'human_resources','region':'广东'}
  rows=listing_items('<a href="/2026/a.html">某县事业单位2026年公开招聘工作人员公告</a><a href="/2026/b.html">某医院2026年公开招聘行政人员公告</a>',hr)
  self.assertEqual(len(rows),2)
  result=basic_information(rows[1]['title'],hr)
  self.assertEqual(result['announcement_type'],'公开招聘');self.assertEqual(result['sector'],'医疗卫生')
  self.assertEqual(result['source_region'],'广东');self.assertNotIn('eligibility',result)
 def test_bounded_column_discovery(self):
  from scripts.source_channels import recruitment_columns
  html='<a href="/a/">事业单位招聘</a><a href="https://evil.example/a/">公开招聘</a><a href="/b/">通知公告</a><a href="/c/">招聘公告</a><a href="/position/1">大学招聘博士公告</a>'
  cols=recruitment_columns(html,SOURCE,SOURCE['url'])
  self.assertEqual(len(cols),2);self.assertIn('https://hr.example.edu/a/',cols)
  self.assertFalse(any('evil.example' in u for u in cols))
