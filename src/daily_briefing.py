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
        save_report("No critical security events detected today.")
        return

    with open(DAILY_COLLECTION_FILE, 'r', encoding='utf-8') as f:
        events = json.load(f)

    if not events:
        print("Daily collection is empty.")
        save_report("No critical security events detected today.")
        return

    print(f"Found {len(events)} total events.")

    # 1. ÖNCELİKLENDİRME (Sıralama ve Filtreleme)
    try:
        # Risk skoruna göre çoktan aza sırala
        events.sort(key=lambda x: x['ai_analysis']['risk_score'], reverse=True)
    except: pass

    # İlk 20 olayı al (Token limitini aşmamak için)
    top_events = events[:20]
    
    # 2. AI İÇİN METİN HAZIRLIĞI
    events_text = ""
    for i, event in enumerate(top_events, 1):
        title = event['original_title']
        risk = event['ai_analysis']['risk_score']
        category = event['ai_analysis']['category']
        location = event['ai_analysis']['location']
        details = event['ai_analysis']['detailed_analysis']
        
        entry = f"{i}. [{category} - Risk: {risk}/10] {title}\n"
        entry += f"   Loc: {location} | Note: {details}\n\n"
        events_text += entry

    # Karakter limiti koruması
    if len(events_text) > 9000:
        events_text = events_text[:9000] + "\n...(truncated)..."

    # 3. YENİ PROMPT
    client = Client()
    prompt = f"""
    ACT AS: Security Analyst.
    TASK: Summarize these high-risk security events.

    DATA:
    {events_text}

    STRICT OUTPUT RULES:
    1. DO NOT include a "Subject", "To:", "From:", or "Date" line at the top.
    2. DO NOT write "Executive Briefing" or "Leadership Report".
    3. START DIRECTLY with the first section header.
    4. Use these emoji headers exactly:
       -  EXECUTIVE SUMMARY
       -  KEY INCIDENTS (Group by region if possible)
       - ✈️ AVIATION & OPERATIONS IMPACT
       -  OUTLOOK
    5. Be concise and professional.
    """

    try:
        response = client.chat.completions.create(
            model="deepseek", 
            provider=PollinationsAI,
            messages=[{"role": "user", "content": prompt}],
        )
        summary_text = response.choices[0].message.content
        
        # Olası Markdown hatalarını temizle
        summary_text = summary_text.replace("```markdown", "").replace("```", "").strip()
        
        save_report(summary_text)
        print("Report generated successfully.")
        
    except Exception as e:
        print(f"AI Generation Failed: {e}")
        save_report(f"⚠️ Report generation failed due to AI error: {str(e)}")
    
    finally:
        # --- KRİTİK DÜZELTME BURASI ---
        # Hata olsa da olmasa da bu blok ÇALIŞIR ve dosyayı boşaltır.
        # Böylece yarın temiz bir sayfa açılır.
        print("Cleaning up daily collection...")
        with open(DAILY_COLLECTION_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
        print("Daily collection cleared.")

def save_report(text):
    report_data = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "summary_text": text
    }
    with open(FINAL_REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
