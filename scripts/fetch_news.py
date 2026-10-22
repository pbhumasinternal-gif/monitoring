"""
fetch_news.py — Multi-Source Media Monitoring (Google News, Yahoo News, MSN/Bing, AntaraNews, Detik, Kompas)
Topik: Dana Desa, BUM Desa, Daerah Tertinggal, dan Kemendesa PDT
Dilengkapi Validasi Kata Kunci Ketat, Blacklist Geopolitik/Spam & sokongan Blacklist Manual.
"""

import json
import hashlib
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs, unquote
import urllib.request as urlreq

# ── Konfigurasi Zona Waktu (GMT+7 / WIB) ────────────────────────────────────
WIB = timezone(timedelta(hours=7))

# ── Kata Kunci Utama & Term Validasi Spesifik (4 Topik) ─────────────────────
KEYWORDS = [
    {
        "id": "danadesa",
        "label": "Dana Desa",
        "query": '"Dana Desa"',
        "raw_query": "Dana Desa",
        "match_terms": [
            "dana desa", "apbdes", "blt dd", "alokasi dana desa",
            "anggaran desa", "keuangan desa", "dana kampung", "dd tahap"
        ],
    },
    {
        "id": "bumdesa",
        "label": "BUM Desa",
        "query": '"BUMDes" OR "BUM Desa"',
        "raw_query": "BUMDes",
        "match_terms": [
            "bumdes", "bum desa", "badan usaha milik desa", "bumkal", "bumdesma"
        ],
    },
    {
        "id": "daerahtertinggal",
        "label": "Daerah Tertinggal",
        "query": '"Daerah Tertinggal" OR "Desa Tertinggal" OR "Wilayah 3T"',
        "raw_query": "Daerah Tertinggal",
        "match_terms": [
            "daerah tertinggal", "desa tertinggal", "wilayah 3t", "daerah 3t",
            "daerah perbatasan", "desa perbatasan", "kawasan perbatasan",
            "perbatasan negara", "3tp", "bnppdt"
        ],
    },
    {
        "id": "kemendesa",
        "label": "Kemendesa PDT",
        "query": '"Kemendes" OR "Kemendesa" OR "Mendes PDT" OR "Yandri Susanto"',
        "raw_query": "Kemendes PDT",
        "match_terms": [
            "kemendesa", "kemendes", "mendes pdt", "mendes yandri", "wamendes",
            "yandri susanto", "ahmad riza patria", "kementerian desa",
            "hari desa", "koperasi desa", "kopdes merah putih", "kdkmp"
        ],
    },
]

# ── Blacklist Isu Luar Negara, Sukan, Cuaca & Spam SEO ──────────────────────
NOISE_BLACKLIST = [
    r"\bisrael\b", r"\biran\b", r"\bpalestina\b", r"\bgaza\b", r"\blebanon\b",
    r"\bhouthi\b", r"\bukraina\b", r"\brusia\b", r"\btrump\b", r"\bkim\s+jong\s+un\b",
    r"latihan\s+tempur", r"rudal", r"liga\s+champions", r"manchester\s+united",
    r"real\s+madrid", r"villarreal", r"liverpool", r"persija", r"arema\s+fc",
    r"bali\s+united", r"garudayaksa", r"french\s+open", r"jadwal\s+shalat",
    r"samsat\s+keliling", r"cuaca\s+kota", r"harga\s+emas\s+antam",
    r"google\+externes", r"google\+ranking", r"google\+indexation",
    r"sistema\+di\+posizionamento", r"seleb\s+hollywood",
]

TARGET_PORTALS = [
    {"site": "detik.com", "default_source": "detikcom"},
    {"site": "kompas.com", "default_source": "Kompas.com"},
    {"site": "antaranews.com", "default_source": "ANTARA News"},
    {"site": "msn.com", "default_source": "MSN Indonesia"},
    {"site": "id.berita.yahoo.com", "default_source": "Yahoo News"},
]

DIRECT_PORTAL_FEEDS = [
    {"name": "ANTARA News Terkini", "url": "https://www.antaranews.com/rss/terkini.xml", "source": "ANTARA News"},
    {"name": "ANTARA News Nasional", "url": "https://www.antaranews.com/rss/nasional.xml", "source": "ANTARA News"},
    {"name": "Detik News", "url": "https://news.detik.com/berita/rss", "source": "detikcom"},
    {"name": "Detik Finance", "url": "https://finance.detik.com/rss", "source": "detikFinance"},
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
}

DATA_PATH = Path(__file__).parent.parent / "docs" / "data" / "news.json"
BLACKLIST_PATH = Path(__file__).parent.parent / "docs" / "data" / "blacklist.json"

# ── Kamus Semantik Sentimen ─────────────────────────────────────────────────
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
    "sinergi": 1, "kolaborasi": 1, "optimal": 1, "untung": 1,
}

NEGATIVE_WORDS = {
    "korupsi": -3, "tersangka": -3, "selewengkan": -3, "penyelewengan": -3,
    "penyimpangan": -2, "penggelapan": -3, "fiktif": -3, "mangkrak": -2,
    "mangkir": -2, "bungkam": -2, "polemik": -2, "sengketa": -2,
    "konflik": -2, "krisis": -2, "rusak": -2, "retak": -2,
    "dikriminalisasi": -2, "tertinggal": -1,
}

MITIGATION_PREFIXES = {
    "cegah", "mencegah", "pencegahan", "antisipasi", "atasi", "mengatasi",
    "redam", "entaskan", "pengentasan", "solusi", "melawan", "anti", "antikorupsi",
}
NEGATION_PREFIXES = {"tak", "tidak", "belum", "kurang", "bukan", "tanpa", "gagal", "minim"}

USER_IGNORED_IDS = set()
USER_BLOCKED_TERMS = []


def load_user_blacklist():
    global USER_IGNORED_IDS, USER_BLOCKED_TERMS
    if BLACKLIST_PATH.exists():
        try:
            data = json.loads(BLACKLIST_PATH.read_text(encoding="utf-8"))
            USER_IGNORED_IDS = set(data.get("ignored_ids", []))
            USER_BLOCKED_TERMS = [str(t).lower().strip() for t in data.get("blocked_terms", []) if str(t).strip()]
            print(f"Blacklist pengguna dimuat: {len(USER_IGNORED_IDS)} ID, {len(USER_BLOCKED_TERMS)} kata kunci")
        except Exception as e:
            print(f"  [WARN] Gagal memuat blacklist.json: {e}")


def analyze_sentiment(title: str, desc: str = "") -> dict:
    text = f"{title or ''} {desc or ''}".lower()
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

    tokens = re.findall(r"[a-z0-9-]+", str(title or "").lower())
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


def is_relevant_to_topic(title: str, desc: str, kw: dict, art_id: str = "") -> bool:
    if art_id and art_id in USER_IGNORED_IDS:
        return False

    combined = f"{title or ''} {desc or ''}".lower()
    combined = re.sub(r"&[^;]+;|<[^>]+>", " ", combined)

    for bad_pat in NOISE_BLACKLIST:
        if re.search(bad_pat, combined, flags=re.I):
            return False

    for custom_bad in USER_BLOCKED_TERMS:
        if custom_bad in combined:
            return False

    for term in kw["match_terms"]:
        if term in combined:
            return True
    return False


def normalize_url(url: str) -> str:
    if not url:
        return ""
    u = str(url).strip()
    try:
        parsed = urlparse(u)
        qs = parse_qs(parsed.query)
        for param in ["url", "u", "ru"]:
            if param in qs and qs[param][0].startswith("http"):
                return normalize_url(unquote(qs[param][0]))
        if "r.search.yahoo.com" in parsed.netloc:
            match = re.search(r"/RU=([^/]+)/", parsed.path)
            if match:
                return normalize_url(unquote(match.group(1)))
        return parsed._replace(query="", fragment="").geturl().rstrip("/")
    except Exception:
        return u.split("?")[0].rstrip("/")


def clean_title_for_dedup(title, source="") -> str:
    t = str(title or "").strip()
    src = str(source or "").strip()
    if src and t.lower().endswith(" - " + src.lower()):
        t = t[:-(len(src) + 3)].strip()
    t = re.sub(r"\s+[-|]\s+(detik[a-z]*|kompas\.com|antara\s*news.*|msn.*|yahoo.*)$", "", t, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", t.lower())


def make_id(title, source) -> str:
    slug = clean_title_for_dedup(title, source)
    src_str = str(source or "").strip().lower()
    return hashlib.md5(f"{slug}|{src_str}".encode()).hexdigest()[:12]


def infer_source_from_url(url: str, fallback: str = "Media Berita") -> str:
    try:
        host = urlparse(str(url or "")).netloc.lower().replace("www.", "")
        if "detik.com" in host:
            return "detikcom"
        if "kompas.com" in host:
            return "Kompas.com"
        if "antaranews.com" in host:
            return "ANTARA News"
        if "msn.com" in host:
            return "MSN Indonesia"
        if "yahoo.com" in host:
            return "Yahoo News"
        if host and "google.com" not in host and "bing.com" not in host:
            return host
    except Exception:
        pass
    return fallback


def parse_rss_date(date_str: str) -> str:
    if not date_str:
        return datetime.now(WIB).isoformat()
    raw = str(date_str).strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(WIB).isoformat()
    except Exception:
        pass
    for fmt in [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%a, %d %b %Y %H:%M:%S %z",
        "%d %b %Y %H:%M:%S %z",
    ]:
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(WIB).isoformat()
        except ValueError:
            continue
    return datetime.now(WIB).isoformat()


def build_article_dict(title, link, pub_raw, desc_raw, source, kw) -> dict:
    clean_link = normalize_url(link)
    clean_desc = re.sub(r"<[^>]+>", "", str(desc_raw or "")).strip()
    clean_desc = re.sub(r"\s+", " ", clean_desc)[:300]
    final_source = str(source or "").strip() or infer_source_from_url(clean_link)
    pub_iso = parse_rss_date(pub_raw)
    sem = analyze_sentiment(title, clean_desc)

    return {
        "id": make_id(title, final_source),
        "title": str(title or "").strip(),
        "link": clean_link,
        "source": final_source,
        "pub_date": pub_iso,
        "desc": clean_desc,
        "topic": kw["id"],
        "topic_label": kw["label"],
        "sentiment": sem["sentiment"],
        "sentiment_score": sem["sentiment_score"],
        "sentiment_tag": sem["sentiment_tag"],
    }


def sanitize_existing_article(art: dict) -> dict | None:
    if not isinstance(art, dict):
        return None
    title = str(art.get("title") or "").strip()
    link = str(art.get("link") or "").strip()
    if not title or not link:
        return None

    topic_id = str(art.get("topic") or "danadesa").strip()
    kw_def = next((k for k in KEYWORDS if k["id"] == topic_id), KEYWORDS[0])
    desc = str(art.get("desc") or "").strip()
    source = str(art.get("source") or "").strip() or infer_source_from_url(link)
    art_id = str(art.get("id") or make_id(title, source))

    if not is_relevant_to_topic(title, desc, kw_def, art_id):
        return None

    pub_date = parse_rss_date(art.get("pub_date") or "")
    sem = analyze_sentiment(title, desc)

    return {
        "id": art_id,
        "title": title,
        "link": link,
        "source": source,
        "pub_date": pub_date,
        "desc": desc,
        "topic": kw_def["id"],
        "topic_label": kw_def["label"],
        "sentiment": art.get("sentiment") if art.get("sentiment") in ("positif", "netral", "negatif") else sem["sentiment"],
        "sentiment_score": int(art.get("sentiment_score", sem["sentiment_score"])) if isinstance(art.get("sentiment_score"), (int, float)) else sem["sentiment_score"],
        "sentiment_tag": str(art.get("sentiment_tag") or sem["sentiment_tag"]),
    }


def fetch_xml_items(url: str) -> list:
    try:
        req = urlreq.Request(url, headers=HEADERS)
        with urlreq.urlopen(req, timeout=15) as resp:
            raw_bytes = resp.read()
        root = ET.fromstring(raw_bytes)
        channel = root.find("channel")
        if channel is not None:
            return channel.findall("item")
        return root.findall(".//item")
    except Exception:
        return []


def fetch_google_news(query: str, kw: dict, default_source: str = "") -> list:
    params = urlencode({"q": query, "hl": "id", "gl": "ID", "ceid": "ID:id"})
    url = f"https://news.google.com/rss/search?{params}"
    articles = []
    try:
        for item in fetch_xml_items(url):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = item.findtext("pubDate") or ""
            desc = item.findtext("description") or ""
            src_el = item.find("source")
            source = src_el.text.strip() if (src_el is not None and src_el.text) else default_source
            if not title or not link:
                continue
            art = build_article_dict(title, link, pub, desc, source, kw)
            if not is_relevant_to_topic(title, desc, kw, art["id"]):
                continue
            articles.append(art)
    except Exception:
        pass
    return articles


def fetch_msn_bing_news(query: str, kw: dict) -> list:
    params = urlencode({"q": query, "format": "rss", "mkt": "id-ID"})
    url = f"https://www.bing.com/news/search?{params}"
    articles = []
    try:
        for item in fetch_xml_items(url):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = item.findtext("pubDate") or ""
            desc = item.findtext("description") or ""
            source = "MSN / Bing News"
            for child in item:
                if child.tag.lower().endswith("source") and child.text:
                    source = child.text.strip()
                    break
            if not title or not link:
                continue
            art = build_article_dict(title, link, pub, desc, source, kw)
            if not is_relevant_to_topic(title, desc, kw, art["id"]):
                continue
            articles.append(art)
    except Exception:
        pass
    return articles


def fetch_yahoo_news(query: str, kw: dict) -> list:
    params = urlencode({"p": query, "ei": "UTF-8"})
    url = f"https://news.search.yahoo.com/rss?{params}"
    articles = []
    try:
        for item in fetch_xml_items(url):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = item.findtext("pubDate") or ""
            desc = item.findtext("description") or ""
            src_el = item.find("source")
            source = src_el.text.strip() if (src_el is not None and src_el.text) else "Yahoo News"
            if not title or not link:
                continue
            art = build_article_dict(title, link, pub, desc, source, kw)
            if not is_relevant_to_topic(title, desc, kw, art["id"]):
                continue
            articles.append(art)
    except Exception:
        pass
    return articles


def match_keyword_topic(text: str):
    t = text.lower()
    for kw in KEYWORDS:
        for term in kw["match_terms"]:
            if term in t:
                return kw
    return None


def fetch_portal_feeds() -> list:
    matched_articles = []
    for feed in DIRECT_PORTAL_FEEDS:
        try:
            items = fetch_xml_items(feed["url"])
            for item in items:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub = item.findtext("pubDate") or ""
                desc = item.findtext("description") or ""
                if not title or not link:
                    continue
                matched_kw = match_keyword_topic(f"{title} {desc}")
                if matched_kw:
                    art = build_article_dict(title, link, pub, desc, feed["source"], matched_kw)
                    if is_relevant_to_topic(title, desc, matched_kw, art["id"]):
                        matched_articles.append(art)
        except Exception:
            pass
    return matched_articles


def main():
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    load_user_blacklist()

    existing = []
    if DATA_PATH.exists():
        try:
            raw_existing = json.loads(DATA_PATH.read_text(encoding="utf-8"))
            print(f"Data lama terbaca: {len(raw_existing)} artikel")
            for item in raw_existing:
                clean_item = sanitize_existing_article(item)
                if clean_item:
                    existing.append(clean_item)
            print(f"Data lama valid & relevan: {len(existing)} artikel")
        except Exception as e:
            print(f"  [WARN] Gagal membaca data lama: {e}")

    seen_ids = {a["id"] for a in existing}
    seen_urls = {normalize_url(a["link"]) for a in existing}
    seen_slugs = {clean_title_for_dedup(a["title"], a["source"]) for a in existing}
    new_articles = []

    def register_articles(candidates: list) -> int:
        added = 0
        for art in candidates:
            norm_u = normalize_url(art["link"])
            slug = clean_title_for_dedup(art["title"], art["source"])
            if not slug or art["id"] in seen_ids or norm_u in seen_urls or slug in seen_slugs:
                continue
            new_articles.append(art)
            seen_ids.add(art["id"])
            seen_urls.add(norm_u)
            seen_slugs.add(slug)
            added += 1
        return added

    for kw in KEYWORDS:
        print(f"\n=== Topik: {kw['label']} ===")
        c_gnews = register_articles(fetch_google_news(kw["query"], kw))
        print(f"  + Google News       : {c_gnews} baru")

        c_msn = register_articles(fetch_msn_bing_news(kw["raw_query"], kw))
        print(f"  + MSN / Bing News   : {c_msn} baru")

        c_yahoo = register_articles(fetch_yahoo_news(kw["raw_query"], kw))
        print(f"  + Yahoo News        : {c_yahoo} baru")

        c_portals = 0
        for portal in TARGET_PORTALS:
            site_query = f'{kw["query"]} site:{portal["site"]}'
            c_portals += register_articles(
                fetch_google_news(site_query, kw, default_source=portal["default_source"])
            )
            time.sleep(0.3)
        print(f"  + Deep Portal Search: {c_portals} baru")
        time.sleep(0.5)

    print("\n=== Memeriksa Direct RSS Portal Utama ===")
    c_direct = register_articles(fetch_portal_feeds())
    print(f"  + Direct RSS Match  : {c_direct} baru")

    all_articles = sorted(existing + new_articles, key=lambda a: a["pub_date"], reverse=True)
    DATA_PATH.write_text(json.dumps(all_articles, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSelesai! Total: {len(all_articles)} artikel ({len(new_articles)} baru) → {DATA_PATH}")


if __name__ == "__main__":
    main()
