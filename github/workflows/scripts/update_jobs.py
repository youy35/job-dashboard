import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

OUTPUT = Path("jobs-feed.json")

# 第一版使用公开招聘 RSS 搜索源。
# 这些结果只是线索，不代表岗位已经核实。
SOURCES = [
    {
        "name": "Academic research jobs",
        "url": "https://www.google.com/alerts/feeds/00000000000000000000/00000000000000000000",
        "track": "科研",
    }
]


def fetch_feed(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def parse_feed(content, source):
    root = ET.fromstring(content)
    jobs = []

    for item in root.findall(".//item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()

        if not title or not link.startswith("http"):
            continue

        jobs.append({
            "org": "机构待核实",
            "role": title,
            "country": "待核实",
            "city": "待核实",
            "track": source["track"],
            "url": link,
            "source": source["name"],
            "notes": "自动发现的招聘线索，尚未核实是否仍在招聘。"
        })

    return jobs


def main():
    existing = []

    if OUTPUT.exists():
        try:
            existing = json.loads(
                OUTPUT.read_text(encoding="utf-8")
            ).get("jobs", [])
        except (ValueError, OSError):
            pass

    results = {
        item["url"]: item
        for item in existing
        if item.get("url")
    }

    for source in SOURCES:
        try:
            content = fetch_feed(source["url"])
            for job in parse_feed(content, source):
                results[job["url"]] = job

        except Exception as error:
            print(f"Source failed: {source['name']}: {error}")

    payload = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "jobs": list(results.values())[-500:]
    }

    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Saved {len(payload['jobs'])} job leads")


if __name__ == "__main__":
    main()
