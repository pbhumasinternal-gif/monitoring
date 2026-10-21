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
    """
    Analisis semantik kontekstual berbahasa Indonesia untuk pemberitaan desa.
    Mengembalikan dict: {sentiment, sentiment_score, sentiment_tag}
    """
    text = f"{title} {desc}".lower()
    text = re.sub(r"&nbsp;|&amp;|<[^>]+>", " ", text)

    score = 0
    matched_tag = None

    # 1. Evaluasi frasa komposit positif terlebih dahulu
    for pattern, weight, tag in POSITIVE_PHRASES:
        if re.search(pattern, text):
            score += weight
            if not matched_tag:
                matched_tag = tag

    # 2. Evaluasi frasa komposit negatif (kecuali jika dalam konteks pencegahan/antikorupsi)
    for pattern, weight, tag in NEGATIVE_PHRASES:
        match = re.search(pattern, text)
        if match:
            # Cek 3 kata sebelum frasa negatif, apakah ada kata mitigasi/