import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

OUTPUT = Path("jobs-feed.json")

# 公开资讯搜索源：返回的是待核实线索
QUERIES = [
    ("考古 博士 招聘 高校 博物馆", "科研"),
    ("艺术史 佛教艺术 博士后 招聘", "博士后"),
    ("museum curator Asian art jobs", "博物馆"),
    ("East Asian studies postdoctoral fellowship jobs", "博士后"),
    ("cultural heritage research jobs", "海外非学术"),
]


def fetch_news(query):
    params = urllib.parse.urlencode({
        "q": query + " when:30d",
        "hl": "zh-CN",
        "gl": "CN",
        "ceid": "CN:zh-Hans",
    })
    url = "https://news.google.com/rss/search?" + params

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def parse_news(content, track):
    root = ET.fromstring(content)
    jobs = []

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source = (item.findtext("source") or "Google News").strip()

        if not title or not link.startswith("https://"):
            continue

        jobs.append({
            "org": "机构待核实",
            "role": title,
            "country": "待核实",
            "city": "待核实",
            "track": track,
            "url": link,
            "source": source,
            "notes": (
                "公开资讯搜索结果，不代表岗位正在招聘。"
                "请打开原始公告核实单位、截止日期、"
                "学位要求、论文门槛、薪酬及工作签证。"
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
        except (OSError, ValueError):
            pass

    results = {
        job["url"]: job
        for job in existing
        if isinstance(job, dict) and job.get("url")
    }

    success = 0

    for query, track in QUERIES:
        try:
            content = fetch_news(query)
            jobs = parse_news(content, track)

            for job in jobs:
                results[job["url"]] = job

            success += 1
            print(f"{query}: {len(jobs)} leads")

        except Exception as error:
            print(f"Search failed: {query}: {error}")

    if success == 0:
        raise RuntimeError("所有资讯搜索源均失败，未更新数据")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "jobs": list(results.values())[-500:],
    }

    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Saved {len(payload['jobs'])} leads")


if __name__ == "__main__":
    main()
