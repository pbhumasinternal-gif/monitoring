"""
fetch_news.py — Monitor Berita Dana Desa, BUM Desa, Daerah Tertinggal dan Kemendesa PDT
Ambil dari Google News RSS, analisis sentimen semantik kontekstual,
dan akumulasi ke docs/data/news.json (tidak ditimpa).
Jalankan via GitHub Actions tiap 30 menit.
"""

import json, hashlib, re, time, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs, unquote
import urllib.request as urlreq

# ── Konfigurasi Zona Waktu (GMT+7 / WIB) ────────────────────────────────────
WIB = timezone(timedelta(hours=7))

# ── Kata kunci (4 topik) ─────────────────────────────────────────────────────
KEYWORDS = [
    {"id": "danadesa", "label": "Dana Desa", "query": "Dana Desa"},
    {"id": "bumdesa", "label": "BUM Desa", "query": "BUMDes"},
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

# ── Kamus & Aturan Semantik Kontekstual Pemberitaan Desa ────────────────────
POSITIVE_PHRASES = [
    (r"\b(desa\s+anti\s*korupsi|percontohan\s+anti\s*korupsi|anugerah\s+desa)\b", 3, "Apresiasi & Penghargaan"),
    (r"\b(raih\s+penghargaan|raih\s+anugerah|berprestasi\s+nasional|peringkat\s+dua|tercepat)\b", 3, "Apresiasi & Penghargaan"),
    (r"\b(tersalur\s+100\s+persen|tembus\s+100\s+persen|tuntas\s+100\s+persen|cair\s+100\s+persen)\b", 3, "Capaian Penyaluran"),
    (r"\b(cegah\s+korupsi|pencegahan\s+korupsi|cegah\s+penyimpangan|pencegahan\s+penyimpangan|cegah\s+anomali)\b", 2, "Mitigasi & Pengawasan"),
    (r"\b(pendampingan\s+hukum|penyuluhan\s+hukum|sosialisasi\s+pengawasan|perkuat\s+pengawasan|kawal\s+transparansi)\b", 2, "Mitigasi & Pengawasan"),
    (r"\b(batal\s+demo|tuntutan\s+.*?\s+disepakati|langsung\s+melempem)\b", 2, "Resolusi & Kondusif"),
    (r"\b(panen\s+perdana|panen\s+edamame|panen\s+telur|ketahanan\s+pangan|swasembada\s+pangan)\b", 2, "Inovasi & Ketahanan Pangan"),
    (r"\b(naik\s+kelas|tembus\s+pasar\s+ekspor|go\s+international|pasar\s+global|siap\s+ekspor)\b", 3, "Penguatan Ekonomi"),
    (r"\b(sumbang\s+pad|tembus\s+pad|raup\s+omzet|dongkrak\s+ekonomi|perkuat\s+ekonomi|motor\s+ekonomi)\b", 2, "Penguatan Ekonomi"),
    (r"\b(aplikasi\s+keuangan\s+gratis|laporan\s+keuangan\s+digital|mendigitalkan\s+arsip|kendaraan\s+listrik)\b", 2, "Inovasi & Digitalisasi"),
    (r"\b(cegah\s+stunting|atasi\s+stunting|pencegahan\s+stunting|entaskan\s+kemiskinan|bantu\s+\d+\s+anak)\b", 2, "Pemberdayaan Masyarakat"),
]

NEGATIVE_PHRASES = [
    (r"\b(tetapkan\s+tersangka|ditetapkan\s+tersangka|jadi\s+tersangka|ditetapkan\s+sebagai\s+tersangka)\b", -4, "Kasus Hukum & Korupsi"),
    (r"\b(dugaan\s+korupsi|terindikasi\s+korupsi|kasus\s+korupsi|korupsi\s+dana\s+desa|korupsi\s+apbdes|korupsi\s+bumdes)\b", -4, "Kasus Hukum & Korupsi"),
    (r"\b(selewengkan|penyelewengan|penyimpangan\s+dana|penggelapan\s+dana|digelapkan|digasak|tilep|maling\s+dana|rampok\s+dana)\b", -4, "Kasus Hukum & Korupsi"),
    (r"\b(judi\s+online|judi\s+slot|judol|dipakai\s+trading)\b", -4, "Penyalahgunaan Anggaran"),
    (r"\b(proyek\s+fiktif|kegiatan\s+fiktif|mark-up|pungli|kerugian\s+negara|bancakan\s+oknum)\b", -4, "Kasus Hukum & Korupsi"),
    (r"\b(dijebloskan\s+ke\s+penjara|ditahan\s+kejari|ditahan\s+polres|ditahan\s+kasus|dituntut\s+.*?\s+penjara|diborgol\s+kejari)\b", -4, "Kasus Hukum & Korupsi"),
    (r"\b(mangkir|bungkam|tak\s+dijawab|menjadi\s+misteri|simpang\s+siur|mengambang|aroma\s+kkn)\b", -3, "Sorotan Transparansi"),
    (r"\b(dipertanyakan|disorot\s+tajam|desak\s+aph|desak\s+inspektorat|desak\s+periksa|tuntut\s+transparansi|audit\s+investigatif)\b", -2, "Sorotan & Evaluasi Publik"),
    (r"\b(tak\s+untung|tidak\s+untung|tak\s+produktif|tak\s+dongkrak|mangkrak|bebek\s+fiktif|kambing\s+disebut\s+mati|sudah\s+retak)\b", -3, "Kendala Kinerja & Aset"),
    (r"\b(buang\s+limbah|cemari\s+saluran|krisis\s+air|tak\s+terawat|masih\s+tertinggal|belum\s+signifikan|belum\s+optimal|tersendat)\b", -2, "Kendala Infrastruktur & Layanan"),
    (r"\b(kepung\s+pemkab|geruduk\s+kantor|demo\s+besar-besaran|hearing\s+buntu|ancam\s+kades\s+mundur|tak\s+cair|tertahan)\b", -3, "Polemik & Aksi Massa"),
    (r"\b(susut\s+drastis|turun\s+drastis|anjlok|dipangkas)\b", -2, "Tekanan Anggaran"),
]

POSITIVE_WORDS = {
    "inovasi": 1, "transparan": 1, "akuntabel": 1, "profesional": 1,
    "berprestasi": 2, "apresiasi": 2, "penghargaan": 2, "sukses": 2,
    "berhasil": 2, "mandiri": 1, "sejahtera": 1, "produktif": 1,
    "sinergi": 1, "kolaborasi": 1, "optimal": 1, "untung": 1
}

NEGATIVE_WORDS = {
    "korupsi": -3, "tersangka": -3, "selewengkan": -3, "penyelewengan": -3,
    "penyimpangan": -2, "penggelapan": -3, "fiktif": -3, "mangkrak": -2,
    "mangkir": -2, "bungkam": -2, "polemik": -2, "sengketa": -2,
    "konflik": -2, "krisis": -2, "rusak": -2, "retak": -2,
    "dikriminalisasi": -2, "tertinggal": -1
}

MITIGATION_PREFIXES = {"cegah", "mencegah", "pencegahan", "antisipasi", "atasi", "mengatasi", "redam", "entaskan", "pengentasan", "solusi", "melawan", "anti", "antikorupsi"}
NEGATION_PREFIXES = {"tak", "tidak", "belum", "kurang", "bukan", "tanpa", "gagal", "minim"}


def analyze_sentiment(title: str, desc: str = "") -> dict:
    text = f"{title} {desc}".lower()
    text = re.sub(r"&nbsp;|&amp;|<[^>]+>", " ", text)

    score = 0
    matched_tag = None

    for pattern, weight, tag in POSITIVE_PHRASES:
        if re.search(pattern, text):
            score += weight
            if not matched_tag:
                matched_tag = tag

    for pattern, weight, tag in NEGATIVE_PHRASES:
        match = re.search(pattern, text)
        if match:
            start_idx = max(0, match.start() - 35)
            prefix_context = set(re.findall(r"[a-z]+", text[start_idx:match.start()]))
            if prefix_context.intersection(MITIGATION_PREFIXES):
                score += 2
                if not matched_tag:
                    matched_tag = "Mitigasi & Pengawasan"
            else:
                score += weight
                if not matched_tag or weight <= -3:
                    matched_tag = tag

    tokens = re.findall(r"[a-z0-9-]+", title.lower())
    for i, token in enumerate(tokens):
        prev_words = set(tokens[max(0, i - 3):i])

        if token in POSITIVE_WORDS:
            if prev_words.intersection(NEGATION_PREFIXES):
                score -= 2
                if not matched_tag:
                    matched_tag = "Kendala & Sorotan"
            else:
                score += POSITIVE_WORDS[token]

        elif token in NEGATIVE_WORDS:
            if prev_words.intersection(MITIGATION_PREFIXES):
                score += 2
                if not matched_tag:
                    matched_tag = "Mitigasi & Pengawasan"
            else:
                score += NEGATIVE_WORDS[token]

    if score >= 2:
        sentiment = "positif"
        final_tag = matched_tag or "Capaian & Pemberdayaan"
    elif score <= -2:
        sentiment = "negatif"
        final_tag = matched_tag or "Sorotan & Evaluasi"
    else:
        sentiment = "netral"
        final_tag = "Informatif & Regulasi"

    return {
        "sentiment": sentiment,
        "sentiment_score": score,
        "sentiment_tag": final_tag,
    }


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
        return datetime.now(WIB).isoformat()
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%d %b %Y %H:%M:%S %z"]:
        try:
            return datetime.strptime(date_str.strip(), fmt).astimezone(WIB).isoformat()
        except ValueError:
            continue
    return datetime.now(WIB).isoformat()


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

            sem = analyze_sentiment(title, desc)
            articles.append({
                "id":              make_id(title, source),
                "title":           title,
                "link":            link,
                "source":          source,
                "pub_date":        pub,
                "desc":            desc[:300],
                "topic":           keyword["id"],
                "topic_label":     keyword["label"],
                "sentiment":       sem["sentiment"],
                "sentiment_score": sem["sentiment_score"],
                "sentiment_tag":   sem["sentiment_tag"],
            })
    except Exception as e:
        print(f"  [ERROR] {keyword['id']}: {e}")
    return articles


def main():
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    existing = []
    if DATA_PATH.exists():
        try:
            existing = json.loads(DATA_PATH.read_text(encoding="utf-8"))
            print(f"Data lama: {len(existing)} artikel")
            backfilled = 0
            for art in existing:
                if "sentiment" not in art or "sentiment_tag" not in art:
                    sem = analyze_sentiment(art.get("title", ""), art.get("desc", ""))
                    art["sentiment"]       = sem["sentiment"]
                    art["sentiment_score"] = sem["sentiment_score"]
                    art["sentiment_tag"]   = sem["sentiment_tag"]
                    backfilled += 1
            if backfilled:
                print(f"  [SEMANTIK] Berhasil melengkapi sentimen pada {backfilled} artikel lama.")
        except Exception as e:
            print(f"  [WARN] Gagal membaca data lama: {e}")

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
