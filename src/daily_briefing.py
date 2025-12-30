import json
import os
from datetime import datetime
from groq import Groq
from dotenv import load_dotenv

# --- ORTAM DEĞİŞKENLERİNİ YÜKLE ---
load_dotenv()

DAILY_COLLECTION_FILE = "data/daily_collection.json"
FINAL_REPORT_FILE = "data/daily_final_report.json"

# API Key Kontrolü
if not os.getenv("GROQ_API_KEY"):
    raise ValueError("HATA: .env dosyasında GROQ_API_KEY bulunamadı!")

def main():
    print("--- Starting Daily Briefing Generation (Groq Powered) ---")
    
    if not os.path.exists(DAILY_COLLECTION_FILE):
        print("No daily collection file found.")
        save_report("No critical security events detected today.")
        return

    with open(DAILY_COLLECTION_FILE, 'r', encoding='utf-8') as f:
        try:
            events = json.load(f)
        except json.JSONDecodeError:
            events = []

    if not events:
        print("Daily collection is empty.")
        save_report("No critical security events detected today.")
        return

    print(f"Found {len(events)} total events.")

    # 1. SIRALAMA (En yüksek riskten düşüğe)
    try:
        events.sort(key=lambda x: x['ai_analysis']['risk_score'], reverse=True)
    except: pass

    # 2. SEÇME (Token limitini aşmamak için en kritik 15 olay)
    top_events = events[:15]
    print(f"Processing top {len(top_events)} events for the report.")
    
    # 3. METİN HAZIRLIĞI
    events_text = ""
    for i, event in enumerate(top_events, 1):
        title = event['original_title']
        risk = event['ai_analysis'].get('risk_score', 0)
        category = event['ai_analysis'].get('category', 'Unknown')
        location = event['ai_analysis'].get('location', 'Unknown')
        
        # Detay metnini kısalt
        raw_details = event['ai_analysis'].get('detailed_analysis', '')
        details = (raw_details[:300] + '..') if len(raw_details) > 300 else raw_details
        
        entry = f"{i}. [{category.upper()} - Risk: {risk}/10] {title}\n"
        entry += f"   Loc: {location} | Note: {details}\n\n"
        events_text += entry

    # Karakter Limiti Kontrolü
    if len(events_text) > 8000:
        print(f"Input too long ({len(events_text)} chars). Truncating safe limit.")
        events_text = events_text[:8000] + "\n...(truncated)..."

    # 4. GROQ API İLE RAPOR OLUŞTURMA
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    
    prompt = f"""
    ACT AS: Senior Security Intelligence Analyst.
    TASK: Write a professional Daily Security Briefing based on the provided logs.

    SOURCE DATA:
    {events_text}

    STRICT FORMATTING RULES:
    1. Do NOT use "Subject", "To", "From" lines.
    2. Do NOT use conversational fillers ("Here is the report").
    3. Use the following Markdown structure exactly:

    # 🌍 GLOBAL SECURITY BRIEFING - {datetime.now().strftime('%d %B %Y')}

    ## 🚨 EXECUTIVE SUMMARY
    (A 3-4 sentence high-level overview of the most critical threats today)

    ## 🔥 KEY INCIDENTS
    (List 3-5 most critical events with bullet points. Format: **Location**: Event summary)

    ## ✈️ AVIATION & LOGISTICS IMPACT
    (Specific impacts on flights, cargo routes, or borders)

    ## 🔭 STRATEGIC OUTLOOK
    (One paragraph on what to expect in the next 24-48 hours based on these events)
    """

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile", # Raporlama için en iyi model
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3 # Daha resmi ve tutarlı olması için düşük sıcaklık
        )
        
        summary_text = response.choices[0].message.content
        summary_text = summary_text.replace("```markdown", "").replace("```", "").strip()
        
        # Raporu Kaydet
        save_report(summary_text)
        print("✅ Report generated successfully.")
        
        # 5. TEMİZLİK (SADECE BAŞARILI OLURSA SİL)
        print("Cleaning up daily collection...")
        with open(DAILY_COLLECTION_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
        print("Daily collection cleared ready for tomorrow.")
        
    except Exception as e:
        print(f"❌ AI Generation Failed: {e}")
        # Hata durumunda dosyayı silmiyoruz, böylece veriler kaybolmuyor.
        save_report(f"⚠️ Report generation failed due to API error. Data preserved.\nError: {str(e)}")

def save_report(text):
    report_data = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary_text": text
    }
    with open(FINAL_REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    print(f"Report saved to {FINAL_REPORT_FILE}")

if __name__ == "__main__":
    main()
