"""
fetch_news.py — Monitor Berita Dana Desa, BUM Desa, Daerah Tertinggal dan Kemendesa PDT
Ambil dari Google News RSS, akumulasi ke docs/data/news.json (tidak ditimpa).
Jalankan via GitHub Actions tiap 6 jam.
"""

import json, hashlib, re, time, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs, unquote
import urllib.request as urlreq

# ── Kata kunci (3 topik) ─────────────────────────────────────────────────────
KEYWORDS = [
    {"id": "danadesa", "label": "Dana Desa", "query": "Dana Desa"},
    {"id": "bumdesa",   "label": "BUM Desa", "query": "BUM Desa"},
    {"id": "daerahtertinggal", "label": "Daerah Tertinggal", "query": "Daerah Tertinggal"},
    {"id": "kemendesa", "label": "Kemendesa PDT", "query": "Kemendes PDT"},
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}

DATA_PATH = Path(__file__).parent.parent / "docs" / "data" / "news.json"


def normalize_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        if parsed.netloc == "news.google.com":
            qs = parse_qs(parsed.query)
            if "url" in qs:
                return normalize_url(unquote(qs["url"][0]))
        return parsed._replace(query="", fragment="").geturl().rstrip("/")
    except Exception:
        return url.split("?")[0].rstrip("/")


def make_id(title: str, source: str) -> str:
    return hashlib.md5(f"{title.strip().lower()}|{source.strip().lower()}".encode()).hexdigest()[:12]


def parse_rss_date(date_str: str) -> str:
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%d %b %Y %H:%M:%S %z"]:
        try:
            return datetime.strptime(date_str.strip(), fmt).astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return datetime.now(timezone.utc).isoformat()


def fetch_rss(keyword: dict) -> list:
    params = urlencode({"q": keyword["query"], "hl": "id", "gl": "ID", "ceid": "ID:id"})
    url = f"https://news.google.com/rss/search?{params}"
    articles = []
    try:
        req = urlreq.Request(url, headers=HEADERS)
        with urlreq.urlopen(req, timeout=20) as resp:
            root = ET.fromstring(resp.read())
        channel = root.find("channel")
        if channel is None:
            return articles
        for item in channel.findall("item"):
            title  = (item.findtext("title") or "").strip()
            link   = normalize_url((item.findtext("link") or "").strip())
            pub    = parse_rss_date(item.findtext("pubDate") or "")
            desc   = re.sub(r"<[^>]+>", "", item.findtext("description") or "").strip()
            src_el = item.find("source")
            source = src_el.text.strip() if src_el is not None and src_el.text else ""
            if not title or not link:
                continue
            articles.append({
                "id":          make_id(title, source),
                "title":       title,
                "link":        link,
                "source":      source,
                "pub_date":    pub,
                "desc":        desc[:300],
                "topic":       keyword["id"],
                "topic_label": keyword["label"],
            })
    except Exception as e:
        print(f"  [ERROR] {keyword['id']}: {e}")
    return articles


def main():
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Muat akumulasi lama
    existing = []
    if DATA_PATH.exists():
        try:
            existing = json.loads(DATA_PATH.read_text(encoding="utf-8"))
            print(f"Data lama: {len(existing)} artikel")
        except Exception:
            pass

    seen_ids  = {a["id"] for a in existing}
    seen_urls = {normalize_url(a["link"]) for a in existing}
    new_articles = []

    for kw in KEYWORDS:
        print(f"Fetching: {kw['label']} ...")
        count = 0
        for art in fetch_rss(kw):
            if art["id"] in seen_ids or normalize_url(art["link"]) in seen_urls:
                continue
            new_articles.append(art)
            seen_ids.add(art["id"])
            seen_urls.add(normalize_url(art["link"]))
            count += 1
        print(f"  +{count} artikel baru")
        time.sleep(1)

    all_articles = sorted(existing + new_articles, key=lambda a: a["pub_date"], reverse=True)
    DATA_PATH.write_text(json.dumps(all_articles, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nTotal: {len(all_articles)} artikel ({len(new_articles)} baru) → {DATA_PATH}")


if __name__ == "__main__":
    main()
