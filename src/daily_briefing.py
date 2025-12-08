import json
import os
from datetime import datetime
from g4f.client import Client
from g4f.Provider import PollinationsAI

DAILY_COLLECTION_FILE = "data/daily_collection.json"
FINAL_REPORT_FILE = "data/daily_final_report.json"

def main():
    print("--- Starting Daily Briefing Generation ---")
    
    if not os.path.exists(DAILY_COLLECTION_FILE):
        print("No daily collection file found.")
        # Boş bir rapor oluştur ki Power Automate hata vermesin
        save_report("Bugün raporlanacak kritik bir olay tespit edilmedi.")
        return

    with open(DAILY_COLLECTION_FILE, 'r', encoding='utf-8') as f:
        events = json.load(f)

    if not events:
        print("Daily collection is empty.")
        save_report("Bugün raporlanacak kritik bir olay tespit edilmedi.")
        return

    print(f"Found {len(events)} events to summarize.")

    # AI İçin Özet Metni Hazırla
    events_text = ""
    for i, event in enumerate(events, 1):
        events_text += f"{i}. [{event['ai_analysis']['category']}] {event['original_title']} (Risk: {event['ai_analysis']['risk_score']})\n"
        events_text += f"   - Location: {event['ai_analysis']['location']}\n"
        events_text += f"   - Details: {event['ai_analysis']['detailed_analysis']}\n\n"

    # AI Analizi
    client = Client()
    prompt = f"""
    ACT AS: Chief Security Officer (CSO).
    TASK: Write a "Daily Security Executive Briefing" based on the events below.
    
    EVENTS OF THE DAY:
    {events_text}

    INSTRUCTIONS:
    1. Write in clear, professional English.
    2. Format using clear headers (e.g., "EXECUTIVE SUMMARY", "KEY INCIDENTS", "AVIATION IMPACT", "OUTLOOK").
    3. Do not list every single event. Group them by region or threat type.
    4. Highlight high-risk threats affecting aviation or corporate assets.
    5. Keep it concise but detailed enough for a C-level executive.
    6. Use emoji icons for headers (e.g., , ✈️, ).
    """

    try:
        response = client.chat.completions.create(
            model="deepseek", 
            provider=PollinationsAI,
            messages=[{"role": "user", "content": prompt}],
        )
        summary_text = response.choices[0].message.content
        
        # Raporu Kaydet
        save_report(summary_text)
        print("Report generated successfully.")
        
        # ÖNEMLİ: Günlük havuzu temizle (Yarına hazırlık)
        with open(DAILY_COLLECTION_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
        print("Daily collection cleared.")
        
    except Exception as e:
        print(f"AI Generation Failed: {e}")

def save_report(text):
    # Power Automate'in okuyacağı format
    report_data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "summary_text": text
    }
    with open(FINAL_REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
