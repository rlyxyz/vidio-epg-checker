import json
import requests
from bs4 import BeautifulSoup

CHANNEL_ID = "6685"
TARGET_DATE = "2026-08-08"

def load_cookie_from_file():
    """Membaca string cookie dari file cookies.json"""
    try:
        with open("cookies.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("cookie_string", "")
    except FileNotFoundError:
        print("❌ File cookies.json tidak ditemukan!")
        return ""
    except Exception as e:
        print(f"❌ Error membaca cookies.json: {e}")
        return ""

def parse_cms_schedules():
    cookie_str = load_cookie_from_file()
    if not cookie_str:
        print("⚠️ Cookie kosong, proses dibatalkan.")
        return

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": cookie_str
    }

    url_schedules = f"https://www.vidio.com/admin/livestreamings/{CHANNEL_ID}/schedules?selected_date={TARGET_DATE}"
    print(f"🔍 Mengambil data HTML dari: {url_schedules}...")
    
    response = requests.get(url_schedules, headers=headers, timeout=10)
    if response.status_code != 200:
        print(f"❌ Gagal terhubung ke CMS. Status Code: {response.status_code}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    all_rows = soup.find_all('tr')
    schedules_data = []
    
    for row in all_rows:
        tds = row.find_all('td')
        if len(tds) < 5:
            continue
            
        cols = [td.text.strip() for td in tds]
        row_text = " ".join(cols).upper()
        
        if any(st in row_text for st in ["ENDED", "LIVE", "UPCOMING"]):
            sched_id = cols[1] if len(cols) > 1 else "N/A"
            status = cols[2] if len(cols) > 2 else "N/A"
            title = cols[3] if len(cols) > 3 else "N/A"
            
            thumb_col = cols[8] if len(cols) > 8 else ""
            has_thumbnail = "YES" in thumb_col.upper()
            
            schedules_data.append({
                "id": sched_id,
                "status": status,
                "title": title,
                "has_thumbnail": has_thumbnail
            })
            
            badge = "🟡 MANUAL REVISION" if has_thumbnail else "🟢 REGULAR"
            print(f"[{badge}] ID: {sched_id:<8} | Status: {status:<8} | Title: {title[:40]}")

    print(f"\n✅ Total jadwal terbaca: {len(schedules_data)}")

if __name__ == "__main__":
    parse_cms_schedules()