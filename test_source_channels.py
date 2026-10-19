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
