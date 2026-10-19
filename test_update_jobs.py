import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape
from scripts import update_jobs as radar


def rss(title, url='https://example.org/opportunity'):
    return f'<rss><channel><item><title>{escape(title)}</title><link>{escape(url)}</link><pubDate>Mon, 19 Oct 2026 01:00:00 GMT</pubDate></item></channel></rss>'.encode()


class RadarTests(unittest.TestCase):
    def parse(self, title, kind='job', url='https://example.org/opportunity'):
        return radar.parse_rss(rss(title, url), {'query':'test','track':'test','kind':kind})

    def test_legacy_and_new_tracks(self):
        tracks={s['track'] for s in radar.SEARCHES}
        self.assertTrue({'科研','博物馆','高校行政','博士后','海外非学术','全球跨专业工作','资助志愿者','奖学金与交流培训','国内国际项目'} <= tracks)

    def test_categories_and_no_fabrication(self):
        for title, kind in [('Museum recruitment','job'),('Funded volunteer applications open','volunteer'),('Scholarship applications open','funded'),('国际交流公开招募','china')]:
            with self.subTest(kind=kind):
                j=self.parse(title,kind)[0]
                self.assertEqual(j['verification_status'],'lead')
                self.assertIsNone(j['estimated_self_cost_cny'])
                self.assertEqual(j['official_url'],'')
                self.assertEqual(j['deadline'],'')
                for key in radar.UNKNOWN_FIELDS:
                    self.assertIn('待',j[key])

    def test_irrelevant_and_unsafe_links(self):
        self.assertEqual(self.parse('Museum hiring freeze'),[])
        self.assertEqual(self.parse('Scholarship applications open','volunteer'),[])
        self.assertEqual(self.parse('Volunteer stories','volunteer'),[])
        for url in ['javascript:alert(1)','httpx://example.org','https://','https://[']:
            self.assertEqual(self.parse('Museum hiring',url=url),[])

    def test_html_error_is_failure(self):
        with self.assertRaises(ValueError):
            radar.parse_rss(b'<html/>',{'query':'test'})

    def test_merge_preserves_verified_and_prioritizes_new(self):
        old=[{'url':f'https://example.org/{i}','role':'old','visa':'已核实','notes':'我的备注'} for i in range(1000)]
        found=[{'url':'https://example.org/new','role':'new'}, {'url':old[0]['url'],'role':'overwrite','visa':'待核实'}]
        rows=radar.merge_leads(old,found+found)
        self.assertEqual(len(rows),1000)
        self.assertEqual(rows[0]['role'],'new')
        self.assertEqual(rows[1]['visa'],'已核实')
        self.assertEqual(rows[1]['notes'],'我的备注')

    def test_total_failure_leaves_file_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'feed.json';out.write_text('{"jobs":[]}')
            before=out.read_bytes()
            with patch.object(radar,'fetch_rss',side_effect=OSError('offline')),contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):radar.main(out,radar.SEARCHES[:1])
            self.assertEqual(before,out.read_bytes())

    def test_partial_success_and_legacy_format(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'feed.json';out.write_text('{"jobs":[{"url":"https://example.org/old","role":"legacy","track":"科研"}]}')
            with patch.object(radar,'fetch_rss',side_effect=[rss('Museum hiring'),OSError('offline')]),contextlib.redirect_stdout(io.StringIO()):
                p=radar.main(out,radar.SEARCHES[:2])
            self.assertEqual(len(p['jobs']),2)
            self.assertEqual(p['jobs'][1]['role'],'legacy')
            self.assertEqual([r['status'] for r in p['search_report']],['ok','failed'])
            self.assertIn('generated_at',json.loads(out.read_text()))

    def test_corrupt_input_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'feed.json';out.write_text('{broken')
            with self.assertRaises(ValueError):radar.main(out,[])
            self.assertEqual(out.read_text(),'{broken')

    def test_no_hard_cost_ceiling(self):
        self.assertIsNone(radar.COST_POLICY['hard_limit'])
        self.assertEqual(radar.COST_POLICY['preferred_range'],[3000,15000])


if __name__=='__main__':unittest.main()
