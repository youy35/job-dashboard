import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

OUTPUT = Path("jobs-feed.json")

# 国内和海外招聘搜索方向
SEARCHES = [
    {
        "query": "考古 博士 招聘",
        "track": "科研",
        "lang": "zh",
    },
    {
        "query": "博物馆 研究人员 招聘",
        "track": "博物馆",
        "lang": "zh",
    },
    {
        "query": "高校 国际交流 行政 招聘",
        "track": "高校行政",
        "lang": "zh",
    },
    {
        "query": "艺术史 博士后 招聘",
        "track": "博士后",
        "lang": "zh",
    },
    {
        "query": "East Asian studies postdoctoral position",
        "track": "博士后",
        "lang": "en",
    },
    {
        "query": "Asian art museum curator vacancy",
        "track": "博物馆",
        "lang": "en",
    },
    {
        "query": "cultural heritage research job",
        "track": "海外非学术",
        "lang": "en",
    },
    {
        "query": "university research coordinator hiring",
        "track": "海外非学术",
        "lang": "en",
    },
]

# 只保留标题中含招聘相关词语的资讯
JOB_WORDS = re.compile(
    r"招聘|招募|聘用|招聘公告|岗位|职位|博士后|"
    r"vacancy|vacancies|hiring|recruitment|"
    r"job opening|postdoctoral position|"
    r"research position|applications invited",
    re.IGNORECASE,
)


def fetch_rss(query, lang):
    if lang == "zh":
        settings = {
            "hl": "zh-CN",
            "gl": "CN",
            "ceid": "CN:zh-Hans",
        }
    else:
        settings = {
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }

    settings["q"] = query

    url = (
        "https://news.google.com/rss/search?"
        + urllib.parse.urlencode(settings)
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/rss+xml, application/xml",
        },
    )

    with urllib.request.urlopen(
        request, timeout=30
    ) as response:
        content = response.read()
        print(
            f"HTTP {response.status}, "
            f"bytes={len(content)}, "
            f"query={query}"
        )
        return content


def parse_rss(content, search):
    root = ET.fromstring(content)

    items = root.findall(".//item")
    print(f"RSS items: {len(items)}")

    jobs = []

    for item in items:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source = (item.findtext("source") or "").strip()

        if not title or not link.startswith("http"):
            continue

        if not JOB_WORDS.search(title):
            continue

        jobs.append({
            "org": "机构待核实",
            "role": title[:200],
            "country": "待核实",
            "city": "待核实",
            "track": search["track"],
            "url": link,
            "source": (
                "Google News RSS / "
                + (source or "来源待核实")
            ),
            "notes": (
                "自动发现的招聘资讯线索，"
                "并非已核实的在招岗位。"
                "请查找招聘单位官方网站，"
                "核实公告日期、截止时间、"
                "学历和论文要求、薪酬、"
                "工作许可及申请方式。"
            ),
        })

    return jobs


def main():
    existing = []

    if OUTPUT.exists():
        try:
            payload = json.loads(
                OUTPUT.read_text(encoding="utf-8")
            )
            existing = payload.get("jobs", [])
        except (ValueError, OSError):
            pass

    results = {
        job["url"]: job
        for job in existing
        if isinstance(job, dict) and job.get("url")
    }

    success = 0

    for search in SEARCHES:
        query = search["query"]

        print(f"\nSearching: {query}")

        try:
            content = fetch_rss(
                query,
                search["lang"],
            )

            jobs = parse_rss(content, search)

            for job in jobs:
                results[job["url"]] = job

            print(f"Relevant leads: {len(jobs)}")
            success += 1

        except Exception as error:
            print(f"Search failed: {query}: {error}")

    if success == 0:
        raise RuntimeError(
            "全部 RSS 请求失败，未更新招聘数据"
        )

    payload = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "jobs": list(results.values())[-500:],
    }

    OUTPUT.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"\nCompleted. Saved "
        f"{len(payload['jobs'])} leads."
    )


if __name__ == "__main__":
    main()
