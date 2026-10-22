"""
deep_predictive_analyzer.py — Smart Content Engine
Menganalisis berita dalam rentang waktu tertentu (misal 30 hari terakhir) 
dan menyimpannya ke format JSON agar bisa dibaca langsung oleh agenda.html
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import urllib.request
from html.parser import HTMLParser

DATA_PATH = Path(__file__).parent.parent / "docs" / "data" / "news.json"
OUTPUT_PATH = Path(__file__).parent.parent / "docs" / "data" / "analysis.json"
WIB = timezone(timedelta(hours=7))

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_chunks = []
    def handle_data(self, data):
        text = data.strip()
        if text and len(text) > 20:
            self.text_chunks.append(text)
    def get_text(self):
        return " ".join(self.text_chunks)

def fetch_full_content(url: str, timeout: int = 6) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html_str = resp.read().decode('utf-8', errors='ignore')
            parser = HTMLTextExtractor()
            parser.feed(html_str)
            return parser.get_text()[:1500]
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

    # --- PENGATURAN RENTANG WAKTU (Ubah ke 7 atau 30 hari terakhir) ---
    DAYS_RANGE = 30 
    cutoff_date = datetime.now(WIB) - timedelta(days=DAYS_RANGE)

    filtered_articles = []
    for a in articles:
        pub_str = a.get("pub_date", "")
        try:
            art_date = datetime.fromisoformat(pub_str)
            if art_date >= cutoff_date:
                filtered_articles.append(a)
        except Exception:
            # Jika tanggal gagal diparse, masukkan sebagai cadangan
            filtered_articles.append(a)

    print(f"Total artikel dalam {DAYS_RANGE} hari terakhir: {len(filtered_articles)}")

    # Ambil sampel berita krusial (misal 10 berita negatif/positif teratas untuk dianalisis isinya)
    target_articles = filtered_articles[:10]
    analyzed_items = []

    for idx, art in enumerate(target_articles, 1):
        title = art.get("title", "")
        link = art.get("link", "")
        source = art.get("source", "")
        topic = art.get("topic_label", "")
        sentiment = art.get("sentiment", "netral")
        tag = art.get("sentiment_tag", "")

        print(f"Menganalisis [{idx}/{len(target_articles)}]: {title[:45]}...")
        full_text = fetch_full_content(link) or art.get("desc", "")

        # Tentukan rekomendasi aksi PR berdasarkan sentimen
        if sentiment == "negatif":
            recommendation = "Siapkan rilis klarifikasi cepat, perkuat data tandingan, dan koordinasi dengan unit teknis terkait untuk mitigasi krisis."
            category = "Krisis & Pengawasan"
        elif sentiment == "positif":
            recommendation = "Jadikan model percontohan (best practice) dan amplifikasi melalui infografis media sosial kementerian."
            category = "Capaian & Prestasi"
        else:
            recommendation = "Pantau perkembangan isu secara berkala dan pastikan informasi regulasi tersampaikan dengan akurat."
            category = "Informatif & Regulasi"

        analyzed_items.append({
            "title": title,
            "source": source,
            "link": link,
            "topic": topic,
            "sentiment": sentiment,
            "sentiment_tag": tag,
            "category": category,
            "recommendation": recommendation,
            "summary_text": full_text[:250] + "..."
        })

    # Susun paket data JSON untuk dibaca web
    output_data = {
        "last_updated": datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB"),
        "days_analyzed": DAYS_RANGE,
        "total_checked": len(filtered_articles),
        "insights": analyzed_items
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Hasil analisis prediktif berhasil disimpan ke {OUTPUT_PATH}")

if __name__ == "__main__":
    run_analysis()
