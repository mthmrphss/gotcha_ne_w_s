import feedparser
import json
import os
import hashlib
import time
import requests
from datetime import datetime
from g4f.client import Client
from g4f.Provider import PollinationsAI

# --- GÜÇLENDİRİLMİŞ KAYNAK LİSTESİ ---
RSS_SOURCES = [
    # 1. GOOGLE NEWS: Anlık Sıcak Çatışma ve Güvenlik (Son 1 Saat)
    {
        "name": "Google News (Breaking)",
        "url": "https://news.google.com/rss/search?q=(security+OR+conflict+OR+terror+OR+attack+OR+crash+OR+military)+when:1h&hl=en-US&gl=US&ceid=US:en"
    },
    
    # 2. REDDIT GEOPOLITICS: Stratejik Tartışmalar ve Analizler (İsteğiniz üzerine eklendi)
    {
        "name": "Reddit r/Geopolitics",
        "url": "https://www.reddit.com/r/geopolitics/new/.rss"
    },
    
    # 3. REDDIT WORLDNEWS: Küresel Son Dakika
    {
        "name": "Reddit r/WorldNews",
        "url": "https://www.reddit.com/r/worldnews/new/.rss"
    },

    # 4. WAR ON THE ROCKS: Askeri Strateji ve Dış Politika Analizi
    {
        "name": "War on the Rocks",
        "url": "https://warontherocks.com/feed/"
    },

    # 5. DEFENCE BLOG: Askeri Donanım ve Saha Hareketliliği
    {
        "name": "Defence Blog",
        "url": "https://defence-blog.com/feed/"
    }
]

# --- GELİŞMİŞ ANAHTAR KELİMELER ---
# Artık sadece saldırı değil, "gerginlik" ve "stratejik hamleleri" de yakalıyoruz.
KEYWORDS = [
    # Şiddet/Olay
    "attack", "blast", "explosion", "crash", "terror", "bomb", "strike", "killed", "dead", "injured",
    # Askeri/Operasyonel
    "military", "drone", "missile", "army", "navy", "air force", "mobilization", "deployment", "troops",
    # Politik/Stratejik (Geopolitics için eklendi)
    "coup", "riot", "protest", "sanctions", "tensions", "escalation", "treaty", "nuclear", "cyber", "hack",
    # Havacılık/Ulaşım
    "airport", "airline", "hijack", "emergency", "grounded"
]

# Filtre: Analiz edilmesi gereksiz içerikler
IGNORE_WORDS = [
    "opinion", "editorial", "history of", "biography", "book review", 
    "podcast", "webinar", "why the", "what is", "explained", 
    "lawsuit", "sues", "celebrity", "fashion", "sport"
]

HISTORY_FILE = "data/history.json"
OUTPUT_FILE = "data/latest_alerts.json"

# Bot Korumasını Aşmak İçin Header
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
}

def load_history():
    if not os.path.exists(HISTORY_FILE): return []
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f: return json.load(f)

def save_history(history_list):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history_list[-500:], f, ensure_ascii=False, indent=2)

def get_content_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def fetch_rss(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"Skipping {url} - Status: {response.status_code}")
            return []
        feed = feedparser.parse(response.content)
        return feed.entries
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return []

def analyze_with_g4f(title, summary):
    client = Client()
    
    prompt = f"""
    ACT AS: Senior Strategic Intelligence Analyst.
    TASK: Analyze this security/geopolitical event.
    
    EVENT: {title}
    CONTEXT: {summary}

    OUTPUT: Return ONLY a raw JSON string with these keys:
    - category: [Terrorism, Aviation, Civil Unrest, Cyber, Conflict, Geopolitics, Military, Other]
    - risk_score: (Integer 1-10)
    - location: (String)
    - detailed_analysis: (String, max 2 sentences. Focus on the strategic significance.)
    - immediate_forecast_24h: (String, immediate operational impact)
    - strategic_outlook: (String, long-term geopolitical consequence)
    - operational_impact: (String, advice for corporate/security assets)
    """
    
    try:
        # DeepSeek: Mantıksal analiz ve strateji için en iyisi
        response = client.chat.completions.create(
            model="deepseek", 
            provider=PollinationsAI,
            messages=[{"role": "user", "content": prompt}],
        )
        return clean_and_parse_json(response.choices[0].message.content)
    except:
        try:
            # Yedek: OpenAI
            response = client.chat.completions.create(
                model="openai", 
                provider=PollinationsAI,
                messages=[{"role": "user", "content": prompt}]
            )
            return clean_and_parse_json(response.choices[0].message.content)
        except:
            return None

def clean_and_parse_json(content):
    if not content: return None
    try:
        text = content.strip()
        if "```json" in text: text = text.split("```json")[1].split("```")[0]
        elif "```" in text: text = text.split("```")[1].split("```")[0]
        return json.loads(text)
    except: return None

def main():
    if not os.path.exists('data'): os.makedirs('data')

    history = load_history()
    processed_hashes = [item['id'] for item in history]
    new_alerts = []
    
    print(f"Scanning {len(RSS_SOURCES)} Intelligence Sources...")
    
    for source in RSS_SOURCES:
        entries = fetch_rss(source["url"])
        if not entries: continue
        
        print(f"Checking: {source['name']} ({len(entries)} items)")

        # Her kaynaktan en yeni 4 başlığı kontrol et
        for entry in entries[:4]: 
            title = entry.title
            summary = getattr(entry, 'summary', '')
            link = entry.link
            
            # --- FİLTRELER ---
            combined_text = (title + " " + summary).lower()
            
            if any(ignore in combined_text for ignore in IGNORE_WORDS):
                continue
                
            if not any(word in combined_text for word in KEYWORDS):
                continue

            news_hash = get_content_hash(title)
            if news_hash in processed_hashes:
                continue
            
            print(f"\n>>> Analyzing: {title}")
            
            analysis = analyze_with_g4f(title, summary)
            
            if analysis:
                score = analysis.get('risk_score', 0)
                category = analysis.get('category', 'Other')
                
                # RİSK FİLTRESİ:
                # Risk < 4 ise ve Kategori Kritik (Aviation/Military/Terror) değilse atla.
                # Geopolitics haberleri bazen düşük riskli ama yüksek stratejik önemdedir, 
                # bu yüzden 'Geopolitics' kategorisine de tolerans tanıyalım (Score >= 4 yeterli).
                
                if score < 4 and category not in ["Aviation", "Terrorism", "Military", "Geopolitics"]:
                    print(f"    Skipped (Low Risk: {score}/10)")
                    history.append({"id": news_hash, "timestamp": datetime.now().isoformat()})
                    continue

                print(f"    [SAVED] Score: {score} | Cat: {category} | Loc: {analysis.get('location')}")
                
                alert_obj = {
                    "id": news_hash,
                    "timestamp": datetime.now().isoformat(),
                    "original_title": title,
                    "link": link,
                    "source_name": source['name'],
                    "ai_analysis": analysis
                }
                new_alerts.append(alert_obj)
                history.append({"id": news_hash, "timestamp": datetime.now().isoformat()})
                time.sleep(2) # API nezaketi
            else:
                print("    Analysis failed.")

    # Sonuçları HER DURUMDA Kaydet (Haber varsa dolu, yoksa boş liste)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_alerts, f, ensure_ascii=False, indent=2)

    if new_alerts:
        print(f"\nSUCCESS: {len(new_alerts)} high-priority alerts saved.")
        save_history(history)
    else:
        print("\nNo new HIGH PRIORITY incidents found. (Output file cleared)")

if __name__ == "__main__":
    main()
