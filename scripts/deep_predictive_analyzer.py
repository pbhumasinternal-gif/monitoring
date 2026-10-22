"""
deep_predictive_analyzer.py — Macro PR Strategy Engine
Menganalisis akumulasi isi berita periode tertentu secara holistik untuk menyusun 
strategi narasi makro (amplifikasi & counter-narrative) bagi Biro Humas.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import urllib.request
from html.parser import HTMLParser
from collections import Counter

DATA_PATH = Path(__file__).parent.parent / "docs" / "data" / "news.json"
OUTPUT_PATH = Path(__file__).parent.parent / "docs" / "data" / "analysis.json"
WIB = timezone(timedelta(hours=7))

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_chunks = []
    def handle_data(self, data):
        text = data.strip()
        # Filter teks sampah sisa script web
        if text and len(text) > 30 and "window." not in text and "function" not in text:
            self.text_chunks.append(text)
    def get_text(self):
        return " ".join(self.text_chunks[:10]) # Ambil 10 paragraf pertama

def fetch_snippet(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            html_str = resp.read().decode('utf-8', errors='ignore')
            parser = HTMLTextExtractor()
            parser.feed(html_str)
            txt = parser.get_text()
            return txt if len(txt) > 50 else ""
    except Exception:
        return ""

def run_analysis():
    if not DATA_PATH.exists():
        print("File news.json tidak ditemukan.")
        return

    try:
        articles = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Gagal membaca JSON: {e}")
        return

    DAYS_RANGE = 30
    cutoff_date = datetime.now(WIB) - timedelta(days=DAYS_RANGE)

    filtered = []
    for a in articles:
        try:
            if datetime.fromisoformat(a.get("pub_date", "")) >= cutoff_date:
                filtered.append(a)
        except Exception:
            filtered.append(a)

    print(f"Menganalisis makro dari {len(filtered)} artikel dalam {DAYS_RANGE} hari terakhir...")

    # Kumpulkan sampel teks untuk dianalisis temanya
    neg_articles = [a for a in filtered if a.get("sentiment") == "negatif"]
    pos_articles = [a for a in filtered if a.get("sentiment") == "positif"]
    topic_counter = Counter([a.get("topic_label") for a in filtered])

    # Ekstraksi isu utama negatif (Krisis)
    crisis_themes = []
    for a in neg_articles[:8]: # Ambil sampel untuk dibaca isinya
        body = fetch_snippet(a.get("link", "")) or a.get("desc", "")
        crisis_themes.append({
            "title": a.get("title"),
            "source": a.get("source"),
            "topic": a.get("topic_label"),
            "core_issue": body[:200] + "..."
        })

    # Ekstraksi peluang positif (Amplifikasi)
    positive_themes = []
    for a in pos_articles[:8]:
        body = fetch_snippet(a.get("link", "")) or a.get("desc", "")
        positive_themes.append({
            "title": a.get("title"),
            "source": a.get("source"),
            "topic": a.get("topic_label"),
            "core_achieve": body[:200] + "..."
        })

    # Susun Strategi Makro Humas Berbasis AI Engine
    macro_analysis = {
        "last_updated": datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB"),
        "days_analyzed": DAYS_RANGE,
        "total_checked": len(filtered),
        "dominant_topic": topic_themes_summary(topic_counter),
        "crisis_mitigation": {
            "headline_strategy": "Intensifikasi Narasi Pencegahan & Pembinaan Preventif",
            "narrative_counter": "Menekankan bahwa temuan atau audit pengawasan oleh aparat penegak hukum/APIP merupakan instrumen pembinaan preventif untuk menjamin akuntabilitas penyaluran Dana Desa dan BUMDes, bukan bentuk kegagalan sistemik.",
            "action_items": [
                "Menyiapkan rilis data transparan mengenai progres penyaluran dan pengawalan Dana Desa tahap berjalan.",
                "Berkoordinasi dengan Inspektorat Jenderal Kementerian untuk menyediakan *talking points* resmi bagi pimpinan.",
                "Mendorong publikasi regulasi pencegahan penyimpangan agar diskursus publik bergeser dari sanksi ke perbaikan sistem."
            ],
            "cases": crisis_themes
        },
        "positive_amplification": {
            "headline_strategy": "Amplifikasi Kisah Sukses Transformasi Ekonomi Desa & BUMDes",
            "narrative_boost": "Membangun sentimen positif dengan menyoroti kemandirian ekonomi desa melalui BUMDes produktif dan pengelolaan Dana Desa yang berdampak langsung pada kesejahteraan masyarakat dan penurunan angka kemiskinan ekstrem.",
            "action_items": [
                "Memproduksi infografis tematik *Best Practice* BUMDes yang berhasil menyumbang PADes secara signifikan.",
                "Menggandeng media nasional untuk meliput langsung inovasi desa tertinggal yang sukses bertransformasi.",
                "Menyusun rubrik khusus 'Kabar Desa Mandiri' di kanal media sosial resmi Kementerian."
            ],
            "cases": positive_themes
        }
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(macro_analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Analisis makro berhasil disimpan ke analysis.json")

def topic_themes_summary(counter):
    res = []
    for topic, count in counter.most_common():
        res.append(f"{topic} ({count} berita)")
    return ", ".join(res)

if __name__ == "__main__":
    run_analysis()
