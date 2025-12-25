import feedparser
import json
import os
import hashlib
import time
import requests
import math
from datetime import datetime, timedelta
from groq import Groq
from dotenv import load_dotenv

# --- ORTAM DEĞİŞKENLERİNİ YÜKLE ---
load_dotenv()

# --- AYARLAR ---
ASSETS_FILE = "assets.json"
HISTORY_FILE = "data/history.json"
OUTPUT_FILE = "data/latest_alerts.json"
DAILY_COLLECTION_FILE = "data/daily_collection.json"

# API Key kontrolü
if not os.getenv("GROQ_API_KEY"):
    raise ValueError("HATA: .env dosyasında GROQ_API_KEY bulunamadı!")

RETENTION_MINUTES = 70 

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
}

RSS_SOURCES = [
    {
        "name": "Google News (Breaking)",
        "url": "https://news.google.com/rss/search?q=(security+OR+conflict+OR+terror+OR+attack+OR+crash+OR+military)+when:1h&hl=en-US&gl=US&ceid=US:en"
    },
    {
        "name": "SafeAirspace Warnings",
        "url": "https://safeairspace.net/feed/"
    },
    {
        "name": "Aviation Safety Network",
        "url": "http://aviation-safety.net/rss/recent.xml"
    },
    { 
        "name": "NewYork Times",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"
    },    
    {    
        "name": "Live Flight Emergencies (Squawk)",
        "url": "https://news.google.com/rss/search?q=(squawk+7700+OR+squawk+7500+OR+emergency+landing)+when:1h&hl=en-US&gl=US&ceid=US:en"
    },
    { "name": "Reddit r/Geopolitics", "url": "https://www.reddit.com/r/geopolitics/new/.rss" },
    { "name": "Reddit r/WorldNews", "url": "https://www.reddit.com/r/worldnews/new/.rss" },
    { "name": "War on the Rocks", "url": "https://warontherocks.com/feed/" },
    { "name": "Africa News", "url": "https://www.africanews.com/feed/rss" },
    { "name": "France 24 ME", "url": "https://www.france24.com/en/rss" },
    { "name": "US State Dept", "url": "https://travel.state.gov/_res/rss/TAsTWs.xml" },
    { "name": "Paddle Your Own Kanoo", "url": "https://www.paddleyourownkanoo.com/category/airline-news/feed/" },
    { "name": "Independent Travel", "url": "https://www.independent.co.uk/travel/rss" }
]

KEYWORDS = [
    "attack", "blast", "explosion", "crash", "terror", "bomb", "strike", "killed", "injured", "shooting",
    "military", "missile", "drone", "army", "coup", "riot", "protest", "tensions",
    "airport", "airline", "hijack", "emergency", "grounded", "squawk", "7700", "7500", 
    "evacuation", "bomb threat", "hoax", "security alert",
    "theft", "stolen", "robbery", "heist", "smuggling", "cargo", "freight", "drugs",
    "migrant", "border", "stowaway", "cyber", "hack", "ransomware"
]

IGNORE_WORDS = [
    "opinion", "editorial", "history of", "biography", "book review", "podcast", 
    "why the", "what is", "explained", "lawsuit", "sues", "celebrity", "fashion", "sport", "deal",
    "crash test", "dummy", "dummies", "regulatory", "policy change", "best hotels", "vacation ideas"
]

def load_assets():
    if not os.path.exists(ASSETS_FILE): return []
    try:
        with open(ASSETS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return []

def load_history():
    if not os.path.exists(HISTORY_FILE): return []
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return []

def save_history(history_list):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history_list[-500:], f, ensure_ascii=False, indent=2)

def load_current_alerts():
    if not os.path.exists(OUTPUT_FILE): return []
    try:
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return []

def get_content_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def fetch_rss(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200: return []
        return feedparser.parse(response.content).entries
    except: return []

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371 
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# --- GÜNCELLENEN FONKSİYON ---
def analyze_with_groq(title, summary):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    
    # Hata veren 'compound' yerine daha stabil ve yüksek limitli model seçildi
    MODEL_ID = "llama-3.3-70b-versatile"
    
    prompt = f"""
    ACT AS: Security Operations Center (SOC) Analyst.
    TASK: Analyze news for threats to Assets, Cargo, Aviation, and Personnel.
    
    EVENT TITLE: {title}
    CONTEXT: {summary}

    CRITICAL INSTRUCTIONS:
    1. IGNORE: Regulatory, historical, crash tests, lawsuits, routine traffic accidents, tourist guides. (Set Risk = 0)
    2. CARGO/CRIME: Theft, smuggling, heists, drug busts in logistics => Risk 5-8.
    3. MIGRANTS: Stowaways, border breaches affecting transport => Risk 4-7.
    4. AVIATION: Bomb threats, drone sightings, strikes, crashes => Risk 6-9.
    5. "Crash" in aviation = HIGH RISK. "Crash" on road = LOW RISK (0).

    OUTPUT: Raw JSON string only (NO MARKDOWN blocks):
    {{
        "category": "Terrorism/Aviation/Crime/Border/Civil Unrest/Cyber/Conflict/Other/Irrelevant",
        "risk_score": 0,
        "location": "City, Country",
        "latitude": 0.0,
        "longitude": 0.0,
        "detailed_analysis": "Summary of the threat...",
        "immediate_forecast_24h": "What happens next...",
        "strategic_outlook": "Long term view...",
        "operational_impact": "Impact on transport/logistics..."
    }}
    """
    
    # Retry (Yeniden Deneme) Mekanizması
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=1024 # Token kontrolü
            )
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            error_msg = str(e)
            print(f"⚠️ AI Error (Attempt {attempt+1}/{max_retries}): {error_msg}")
            
            # Rate limit (429) hatası ise bekle ve tekrar dene
            if "429" in error_msg:
                wait_time = 5 * (attempt + 1)
                print(f"⏳ Rate limit hit. Waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                # Başka bir hataysa (JSON hatası vb.) direkt çık
                return None
    
    return None

def update_daily_collection(new_alerts):
    if not new_alerts: return
    
    # Dosya okuma/oluşturma
    if os.path.exists(DAILY_COLLECTION_FILE):
        try:
            with open(DAILY_COLLECTION_FILE, 'r', encoding='utf-8') as f:
                daily_data = json.load(f)
        except: daily_data = []
    else:
        daily_data = []

    existing_ids = [item['id'] for item in daily_data]
    added_count = 0

    for alert in new_alerts:
        if alert['id'] in existing_ids: continue
        
        # Risk Analizi
        if not alert.get('ai_analysis'): continue # Analiz yoksa atla
        
        risk_score = alert['ai_analysis'].get('risk_score', 0)
        category = alert['ai_analysis'].get('category', 'Other')
        has_proximity = alert['ai_analysis'].get('proximity_alert') is not None
        
        is_high_risk = risk_score >= 6
        is_aviation_risk = (category == "Aviation" and risk_score >= 5)
        
        if is_high_risk or has_proximity or is_aviation_risk:
            daily_data.append(alert)
            added_count += 1
    
    if added_count > 0:
        with open(DAILY_COLLECTION_FILE, 'w', encoding='utf-8') as f:
            json.dump(daily_data, f, ensure_ascii=False, indent=2)
        print(f"-> Added {added_count} items to Daily Collection.")

def main():
    if not os.path.exists('data'): os.makedirs('data')

    assets = load_assets()
    history = load_history()
    processed_hashes = [item['id'] for item in history]
    
    current_alerts = load_current_alerts()
    new_alerts_found = []
    
    print(f"Scanning {len(RSS_SOURCES)} Sources...")
    
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
            analysis = analyze_with_groq(title, summary)
            
            if analysis:
                score = analysis.get('risk_score', 0)
                category = analysis.get('category', 'Other')
                
                if score == 0 or category == "Irrelevant":
                    print("    Skipped (Irrelevant)")
                    history.append({"id": news_hash, "timestamp": datetime.now().isoformat()})
                    continue

                # Varlık Kontrolü
                event_lat = analysis.get('latitude', 0.0)
                event_lon = analysis.get('longitude', 0.0)
                proximity_alert = None
                
                if event_lat and event_lon and assets:
                    for asset in assets:
                        if asset.get('lat') is None or asset.get('lon') is None: continue
                        dist = calculate_distance(event_lat, event_lon, asset['lat'], asset['lon'])
                        threshold = 30 if asset.get('type') == 'Airport' else 10
                        if dist < threshold:
                            proximity_alert = f"YAKIN TEHDİT: {asset['name']} ({int(dist)} km)"
                            analysis['risk_score'] = 10
                            score = 10
                            break
                
                analysis['proximity_alert'] = proximity_alert

                if not proximity_alert:
                    critical = ["Aviation", "Terrorism", "Military", "Geopolitics", "Crime/Theft", "Border/Migration"]
                    if score < 4 and category not in critical:
                        print(f"    Skipped (Low Risk: {score})")
                        history.append({"id": news_hash, "timestamp": datetime.now().isoformat()})
                        continue

                print(f"    [SAVED] Score: {score} | {proximity_alert if proximity_alert else ''}")
                
                alert_obj = {
                    "id": news_hash,
                    "timestamp": datetime.now().isoformat(),
                    "original_title": title,
                    "link": link,
                    "source_name": source['name'],
                    "ai_analysis": analysis
                }
                new_alerts_found.append(alert_obj)
                history.append({"id": news_hash, "timestamp": datetime.now().isoformat()})
                time.sleep(1) # Rate limit koruması

    # Temizlik ve Kayıt
    combined_alerts = current_alerts + new_alerts_found
    final_alerts = []
    now = datetime.now()
    
    print("\n--- Cleaning Old Alerts ---")
    for alert in combined_alerts:
        try:
            alert_time = datetime.fromisoformat(alert['timestamp'])
            age_minutes = (now - alert_time).total_seconds() / 60
            
            if age_minutes < RETENTION_MINUTES:
                final_alerts.append(alert)
            else:
                pass # Süresi dolanlar sessizce silinir
        except:
            final_alerts.append(alert)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_alerts, f, ensure_ascii=False, indent=2)

    if new_alerts_found:
        print(f"\nSUCCESS: {len(new_alerts_found)} NEW alerts added.")
        save_history(history)
        update_daily_collection(new_alerts_found)
    else:
        print(f"\nNo NEW incidents. Total active buffer: {len(final_alerts)}")

if __name__ == "__main__":
    main()
