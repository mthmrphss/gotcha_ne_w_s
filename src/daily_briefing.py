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

    # 1. SIRALAMA
    try:
        events.sort(key=lambda x: x['ai_analysis']['risk_score'], reverse=True)
    except: pass

    # 2. AGRESİF FİLTRELEME (LIMIT SORUNU ÇÖZÜMÜ)
    # 20 yerine en kritik 15 olayı alıyoruz.
    top_events = events[:15]
    print(f"Processing top {len(top_events)} events to fit context window.")
    
    # 3. METİN HAZIRLIĞI VE KIRPMA
    events_text = ""
    for i, event in enumerate(top_events, 1):
        title = event['original_title']
        risk = event['ai_analysis']['risk_score']
        category = event['ai_analysis']['category']
        location = event['ai_analysis']['location']
        
        # Detay metnini 300 karakterle sınırla (Çok uzunsa kes)
        raw_details = event['ai_analysis']['detailed_analysis']
        details = (raw_details[:300] + '..') if len(raw_details) > 300 else raw_details
        
        entry = f"{i}. [{category} - Risk: {risk}/10] {title}\n"
        entry += f"   Loc: {location} | Note: {details}\n\n"
        events_text += entry

    # TOPLAM KARAKTER KONTROLÜ (System Prompt payı için 7500'e çektik)
    if len(events_text) > 7500:
        print(f"Input still too long ({len(events_text)} chars). Truncating to 7500.")
        events_text = events_text[:7500] + "\n...(truncated)..."

    # 4. PROMPT
    client = Client()
    prompt = f"""
    ACT AS: Security Analyst.
    TASK: Create a concise Daily Security Briefing.

    DATA:
    {events_text}

    STRICT RULES:
    1. NO "Subject", "To", "From" lines.
    2. NO "Executive Briefing" title. Start with the first emoji header.
    3. HEADERS:
       -  EXECUTIVE SUMMARY
       -  KEY INCIDENTS
       - ✈️ AVIATION/OPS IMPACT
       -  OUTLOOK
    4. Keep it concise.
    """

    try:
        response = client.chat.completions.create(
            model="deepseek", 
            provider=PollinationsAI,
            messages=[{"role": "user", "content": prompt}],
        )
        summary_text = response.choices[0].message.content
        summary_text = summary_text.replace("```markdown", "").replace("```", "").strip()
        
        save_report(summary_text)
        print("Report generated successfully.")
        
    except Exception as e:
        print(f"AI Generation Failed: {e}")
        save_report(f"⚠️ Report generation failed due to AI limit/error: {str(e)}")
    
    finally:
        # Temizlik
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
