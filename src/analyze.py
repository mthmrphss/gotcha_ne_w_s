import feedparser
import json
import os
import hashlib
import time
import requests
import math
from datetime import datetime
from g4f.client import Client
from g4f.Provider import PollinationsAI

# --- AYARLAR ---
ASSETS_FILE = "assets.json"
HISTORY_FILE = "data/history.json"
OUTPUT_FILE = "data/latest_alerts.json"

# Tarayıcı gibi görünmek için Header
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
}

# --- GÜÇLENDİRİLMİŞ KAYNAK LİSTESİ ---
RSS_SOURCES = [
    # 1. GOOGLE NEWS: Anlık Sıcak Çatışma (Son 1 Saat)
    {
        "name": "Google News (Breaking)",
        "url": "https://news.google.com/rss/search?q=(security+OR+conflict+OR+terror+OR+attack+OR+crash+OR+military)+when:1h&hl=en-US&gl=US&ceid=US:en"
    },
    
    # 2. HAVACILIK GÜVENLİĞİ
    {
        "name": "SafeAirspace Warnings",
        "url": "https://safeairspace.net/feed/"
    },
    {
        "name": "Aviation Safety Network",
        "url": "http://aviation-safety.net/rss/recent.xml"
    },
    {   # Squawk 7700/7500 (Acil Durum Kodları)
        "name": "Live Flight Emergencies (Squawk)",
        "url": "https://news.google.com/rss/search?q=(squawk+7700+OR+squawk+7500+OR+emergency+landing)+when:1h&hl=en-US&gl=US&ceid=US:en"
    },

    # 3. REDDIT & STRATEJİ
    {
        "name": "Reddit r/Geopolitics",
        "url": "https://www.reddit.com/r/geopolitics/new/.rss"
    },
    {
        "name": "Reddit r/WorldNews",
        "url": "https://www.reddit.com/r/worldnews/new/.rss"
    },
    {
        "name": "War on the Rocks",
        "url": "https://warontherocks.com/feed/"
    }
]

# --- ANAHTAR KELİMELER ---
KEYWORDS = [
    "attack", "blast", "explosion", "crash", "terror", "bomb", "strike", "killed", "dead", "injured",
    "military", "drone", "missile", "army", "navy", "air force", "mobilization", "deployment",
    "coup", "riot", "protest", "sanctions", "tensions", "escalation", "nuclear", "cyber", "hack",
    "airport", "airline", "hijack", "emergency", "grounded", "squawk", "7700", "7500", "fuselage"
]

IGNORE_WORDS = [
    "opinion", "editorial", "history of", "biography", "book review", "podcast", 
    "why the", "what is", "explained", "lawsuit", "sues", "celebrity", "fashion", "sport", "deal"
]

def load_assets():
    """Varlıkları harici JSON dosyasından yükler"""
    if not os.path.exists(ASSETS_FILE):
        print(f"UYARI: {ASSETS_FILE} bulunamadı! Yarıçap kontrolü pasif.")
        return []
    try:
        with open(ASSETS_FILE, 'r', encoding='utf-8') as f:
            assets = json.load(f)
            print(f"Varlıklar yüklendi: {len(assets)} nokta.")
            return assets
    except Exception as e:
        print(f"Varlık dosyası hatası: {e}")
        return []

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
            return []
        feed = feedparser.parse(response.content)
        return feed.entries
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return []

# --- MESAFE HESAPLAMA (Haversine) ---
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371 
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def analyze_with_g4f(title, summary):
    client = Client()
    
    prompt = f"""
    ACT AS: Senior Strategic Intelligence Analyst.
    TASK: Analyze this event and estimate geolocation coordinates.
    
    EVENT: {title}
    CONTEXT: {summary}

    OUTPUT: Return ONLY a raw JSON string with these keys:
    - category: [Terrorism, Aviation, Civil Unrest, Cyber, Conflict, Geopolitics, Military, Other]
    - risk_score: (Integer 1-10)
    - location: (String) City/Region
    - latitude: (Float) Estimated latitude (Use 0.0 if unknown)
    - longitude: (Float) Estimated longitude (Use 0.0 if unknown)
    - detailed_analysis: (String, max 2 sentences.)
    - immediate_forecast_24h: (String, immediate operational impact)
    - strategic_outlook: (String, long-term consequence)
    - operational_impact: (String, advice for assets)
    """
    
    try:
        response = client.chat.completions.create(
            model="deepseek", 
            provider=PollinationsAI,
            messages=[{"role": "user", "content": prompt}],
        )
        return clean_and_parse_json(response.choices[0].message.content)
    except:
        try:
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

    assets = load_assets()
    history = load_history()
    processed_hashes = [item['id'] for item in history]
    new_alerts = []
    
    print(f"Scanning {len(RSS_SOURCES)} Intelligence Sources...")
    
    for source in RSS_SOURCES:
        entries = fetch_rss(source["url"])
        if not entries: continue
        
        for entry in entries[:4]: 
            title = entry.title
            summary = getattr(entry, 'summary', '')
            link = entry.link
            
            combined_text = (title + " " + summary).lower()
            if any(ignore in combined_text for ignore in IGNORE_WORDS): continue
            if not any(word in combined_text for word in KEYWORDS): continue

            news_hash = get_content_hash(title)
            if news_hash in processed_hashes: continue
            
            print(f"\n>>> Analyzing: {title}")
            
            analysis = analyze_with_g4f(title, summary)
            
            if analysis:
                # --- VARLIK YARIÇAP KONTROLÜ ---
                event_lat = analysis.get('latitude', 0.0)
                event_lon = analysis.get('longitude', 0.0)
                proximity_alert = None
                
                if event_lat and event_lon and assets:
                    for asset in assets:
                        # Hatalı JSON verisi varsa çökme, atla
                        if asset.get('lat') is None or asset.get('lon') is None:
                            continue

                        dist = calculate_distance(event_lat, event_lon, asset['lat'], asset['lon'])
                        threshold = 30 if asset.get('type') == 'Airport' else 10
                        
                        if dist < threshold:
                            proximity_alert = f"🚨 YAKIN TEHDİT: {asset['name']} lokasyonuna {int(dist)} km!"
                            analysis['risk_score'] = 10 
                            break
                
                analysis['proximity_alert'] = proximity_alert

                score = analysis.get('risk_score', 0)
                category = analysis.get('category', 'Other')
                
                # RİSK FİLTRESİ
                if not proximity_alert:
                    if score < 4 and category not in ["Aviation", "Terrorism", "Military", "Geopolitics"]:
                        print(f"    Skipped (Low Risk: {score}/10)")
                        history.append({"id": news_hash, "timestamp": datetime.now().isoformat()})
                        continue

                print(f"    [SAVED] Score: {score} | Cat: {category} | {proximity_alert if proximity_alert else ''}")
                
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
                time.sleep(2)
            else:
                print("    Analysis failed.")

    # HER DURUMDA YAZ (Dosyayı temizlemek veya doldurmak için)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_alerts, f, ensure_ascii=False, indent=2)

    if new_alerts:
        print(f"\nSUCCESS: {len(new_alerts)} high-priority alerts saved.")
        save_history(history)
    else:
        print("\nNo new HIGH PRIORITY incidents found. (Output file cleared)")

if __name__ == "__main__":
    main()
