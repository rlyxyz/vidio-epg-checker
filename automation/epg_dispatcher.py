import os
import re
import time
import json
import unicodedata
import requests
from datetime import datetime, date, timedelta
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import gspread
from google.oauth2.service_account import Credentials

# =======================================================
# CONFIGURATION PANEL
# =======================================================
# Ambil dari Environment Variable agar API Key tidak bocor
WEBHOOK_URL = os.getenv("GOOGLE_CHAT_WEBHOOK", "https://chat.googleapis.com/v1/spaces/AAQAPN7Jp50/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=m4_B83pnhLGWiIEMdRvwz8o39b1dyP61JF5NA9Y_6RE")

URL_SPORT = "https://docs.google.com/spreadsheets/d/1gjT0SPz5dN36MWslyDcRGYOfzmkfTFg4LQKXZfRDhYo/edit?gid=1710292612"
URL_NON_SPORT = "https://docs.google.com/spreadsheets/d/1T9jQGWJHEwzb85tpTLdbo8nyrmnLoLanXk7TxGWEzxM/edit?gid=217062556"
CUSTOM_CHANNELS_FILE = "custom_channels.json"

KNOWN_CHANNELS_BASE = {
    "TVN": "6362", "CITRA DRAMA": "21179", "ROCK ACTION": "8121",
    "TV5MONDE": "17278", "ARIRANG": "6784", "MENTARI": "8237",
    "HIP HIP HOREE!": "7052", "ABC AUSTRALIA": "7150", "NHK JAPAN": "7968",
    "NEWS ASIA": "6411", "DW ENGLISH": "5075", "DAYSTAR": "18622",
    "CHAMPIONS TV 1": "6685", "CHAMPIONS TV 2": "6686", "CHAMPIONS TV 3": "6786",
    "BEIN 1": "6299", "BEIN 2": "17875", "BEIN 3": "6317", "HOREE CHANNEL": "6397",
    "CHAMPIONS FIGHT": "20216", "CHAMPIONS TV 5": "9182", "CHAMPIONS TV 6": "9183",
    "CHAMPIONS TV GOLF 1": "18189", "CHAMPIONS TV GOLF 2": "18190",
    "PREMIER LEAGUE TV": "9353", "SPOTV 1": "17139", "SPOTV 2": "17140",
    "REAL MADRID TV": "19538" , "SCTV": "204" , "INDOSIAR": "205" , "MOJI": "206",
    "KOMPAS TV": "874", "RCTI": "665", "TVONE": "783", "TRANS TV": "733",
    "MDTV": "875", "GTV": "778", "MNCTV": "870", "INEWS": "5409", "BTV": "6165",
    "BERITA SATU": "18280", "JAKTV": "5415", "TRANS7": "734", "RTV": "1561",
    "CITRA PLUS": "21289", "ANTV": "782"
}

def load_all_channels():
    channels = KNOWN_CHANNELS_BASE.copy()
    if os.path.exists(CUSTOM_CHANNELS_FILE):
        try:
            with open(CUSTOM_CHANNELS_FILE, "r", encoding="utf-8") as f:
                channels.update(json.load(f))
        except: pass
    return channels

def bersihkan_teks(teks):
    if not teks: return ""
    teks = str(teks).lower()
    teks = re.sub(r'\(.*?\)', '', teks)
    teks = unicodedata.normalize('NFD', teks)
    teks = "".join([c for c in teks if unicodedata.category(c) != 'Mn'])
    teks = teks.replace('’', "'").replace('`', "'").replace('“', "").replace('”', "")
    teks = teks.replace('-', ' ').replace('_', ' ').replace(':', '').replace("'", "")
    teks = re.sub(r'[\u2013\u2014]', ' ', teks)
    teks = teks.replace('\xa0', ' ').replace('\n', ' ').replace('\t', ' ')
    return re.sub(r'\s+', ' ', teks).strip()

def hancurkan_spasi(teks):
    return re.sub(r'[^a-z0-9]', '', bersihkan_teks(teks))

def fix_time(t):
    if not t: return "00:00"
    t = str(t).strip().replace('.', ':')
    if ":" in t:
        parts = t.split(":")
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)[:2]}"
    return t[:5]

def normalisasi_tanggal(tgl_str):
    tgl_str = str(tgl_str).strip().split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try: return datetime.strptime(tgl_str, fmt).date()
        except ValueError: continue
    return None

def init_gspread():
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    return gspread.authorize(creds)

def fetch_valid_tabs(gc, url):
    sh = gc.open_by_url(url)
    return [ws.title for ws in sh.worksheets() if ("HASIL" in ws.title.upper() or "TO CSV" in ws.title.upper()) and not any(x in ws.title.upper() for x in ["COPY", "TRIAL", "TES", "TEST"])]

def create_selenium_driver():
    options = ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--mute-audio")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36")
    
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver

def send_webhook_alert(message):
    if not WEBHOOK_URL or "PASTE_WEBHOOK" in WEBHOOK_URL:
        print("Webhook URL belum dikonfigurasi dengan benar.")
        return
    batas_karakter = 4000
    potongan_pesan = [message[i:i+batas_karakter] for i in range(0, len(message), batas_karakter)]
    for i, teks in enumerate(potongan_pesan):
        payload = {"text": teks}
        try:
            response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
            if response.status_code != 200:
                print(f" ❌ Gagal bagian {i+1}. Error {response.status_code}: {response.text}")
        except Exception as e: 
            print(f" ❌ Gagal koneksi webhook: {e}")
        time.sleep(1.0)

def jalankan_dispatcher_harian():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Memulai pengecekan EPG otomatis...")
    gc = init_gspread()
    target_dates = [date.today(), date.today() + timedelta(days=1)]
    known_channels = load_all_channels()
    
    daftar_tugas = [("⚽ SPORTS", URL_SPORT), ("📺 NON-SPORTS", URL_NON_SPORT)]
    laporan_error_global = []
    total_channel_dicek = 0
    
    # Inisialisasi Driver awal
    driver = create_selenium_driver()
    
    try:
        for nama_kategori, url_sheet in daftar_tugas:
            tabs = fetch_valid_tabs(gc, url_sheet)
            sh = gc.open_by_url(url_sheet)
            
            for tab in tabs:
                total_channel_dicek += 1
                raw_name = re.sub(r'[^\w\s]', '', tab.upper())
                for kata in ['TO CSV', 'HASIL CSV', 'HASIL', 'CSV', 'JADWAL', 'WIB']:
                    raw_name = raw_name.replace(kata, ' ')
                channel_name = re.sub(r'\s+', ' ', raw_name).strip()
                
                exact_aliases = {
                    'PLTV': 'PREMIER LEAGUE TV', 'RMTV': 'REAL MADRID TV', 'CGOLF': 'CHAMPIONS TV GOLF',
                    'CGOLF 1': 'CHAMPIONS TV GOLF 1', 'CGOLF 2': 'CHAMPIONS TV GOLF 2',
                    'CTV 1': 'CHAMPIONS TV 1', 'CTV 2': 'CHAMPIONS TV 2', 'CTV 3': 'CHAMPIONS TV 3',
                    'CTV 4': 'CHAMPIONS TV 4', 'CTV 5': 'CHAMPIONS TV 5', 'CTV 6': 'CHAMPIONS TV 6', 'CTV': 'CHAMPIONS TV',
                    'HIP HIP': 'HIP HIP HOREE!', 'HIP HIP HOREE': 'HIP HIP HOREE!', 'HOREE': 'HOREE CHANNEL', 'HORE': 'HOREE CHANNEL',           
                    'ABC': 'ABC AUSTRALIA', 'NHK': 'NHK JAPAN', 'TTV': 'TRANS TV', 'KOMPAS': 'KOMPAS TV'
                }
                if channel_name in exact_aliases: channel_name = exact_aliases[channel_name]
                if channel_name not in known_channels: continue
                channel_id = known_channels[channel_name]
                
                try: 
                    data_mentah = sh.worksheet(tab).get_all_values()
                except Exception: 
                    continue
                if len(data_mentah) < 2: continue
                
                df = pd.DataFrame(data_mentah[1:], columns=data_mentah[0])
                cols_lower = [str(c).lower() for c in df.columns]
                if 'attribute:start_date' in cols_lower or 'start_date' in cols_lower:
                    col_date = [c for c in df.columns if 'start_date' in str(c).lower()][0]
                    col_title = [c for c in df.columns if 'title' in str(c).lower()][0]
                    col_start = [c for c in df.columns if 'start_time' in str(c).lower()][0]
                    col_end = [c for c in df.columns if 'end_time' in str(c).lower()][0]
                else:
                    col_date = [c for c in df.columns if 'tanggal' in str(c).lower() or 'date' in str(c).lower()][0]
                    col_title = [c for c in df.columns if 'nama program' in str(c).lower() or 'judul' in str(c).lower() or 'title' in str(c).lower()][0]
                    col_start = [c for c in df.columns if 'jam tayang' in str(c).lower() or 'start_time' in str(c).lower()][0]
                    col_end = [c for c in df.columns if 'jam selesai' in str(c).lower() or 'end_time' in str(c).lower()][0]
                
                df['parsed_date_obj'] = df[col_date].apply(normalisasi_tanggal)
                
                for tgl_target in target_dates:
                    df_filtered = df[df['parsed_date_obj'] == tgl_target].copy()
                    if df_filtered.empty: continue
                    
                    tgl_str = tgl_target.strftime('%d-%m-%Y')
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 Memeriksa {tab.upper()} ({tgl_str})...")
                    
                    df_epg = df_filtered[[col_title, col_start, col_end]].copy()
                    df_epg.columns = ['title', 'start_time', 'end_time']
                    df_epg['start_time'] = df_epg['start_time'].apply(fix_time)
                    df_epg['end_time'] = df_epg['end_time'].apply(fix_time)

                    lokal_errors = []
                    
                    # 1. Pengecekan Gap
                    gap_errors = []
                    df_epg_seq = df_epg.reset_index(drop=True)
                    for idx in range(len(df_epg_seq) - 1):
                        curr_end = df_epg_seq.loc[idx, 'end_time']
                        next_start = df_epg_seq.loc[idx+1, 'start_time']
                        is_gap = True
                        if curr_end == next_start:
                            is_gap = False
                        else:
                            try:
                                t1 = datetime.strptime(curr_end, "%H:%M")
                                t2 = datetime.strptime(next_start, "%H:%M")
                                if (t2 - t1).total_seconds() / 60.0 == 1.0: is_gap = False
                            except: pass
                        if is_gap:
                            gap_errors.append(f"⏱️ [{tgl_str}] Gap sblm jam {next_start} ('{df_epg_seq.loc[idx+1, 'title']}')")
                    
                    lokal_errors.extend(gap_errors)

                    # 2. Pengecekan Full Coverage
                    coverage_errors = []
                    if not df_epg_seq.empty:
                        akhir_hari = df_epg_seq.iloc[-1]['end_time']
                        mulai_akhir_hari = df_epg_seq.iloc[-1]['start_time']
                        is_aman = akhir_hari in ['00:00', '23:59', '24:00']
                        if not is_aman:
                            try:
                                if int(akhir_hari.split(":")[0]) < int(mulai_akhir_hari.split(":")[0]): is_aman = True
                            except: pass
                        if not is_aman:
                            coverage_errors.append(f"🌙 [{tgl_str}] Jadwal tidak full (selesai jam {akhir_hari})")

                    lokal_errors.extend(coverage_errors)
                    
                    # Safe Selenium Execution Wrapper per-page
                    try:
                        driver.get("data:,")
                        time.sleep(0.5)
                        driver.get(f"https://www.vidio.com/live/{channel_id}")
                        time.sleep(5.0)
                        
                        if str(channel_id) not in driver.current_url:
                            lokal_errors.append(f"🚧 [{tgl_str}] Terblokir banner / Link di-redirect!")
                            if lokal_errors:
                                laporan_error_global.append(f"🔴 *{tab.upper()}*\n" + "\n".join([f"  • {e}" for e in lokal_errors]))
                            continue

                        # Scroll Page
                        for i in range(8):
                            driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {(i+1)/8});")
                            time.sleep(0.3)
                        driver.execute_script("window.scrollTo(0, 0);")
                        time.sleep(0.5)

                        # Klik Tanggal / Besok
                        selisih_hari = (tgl_target - date.today()).days
                        if selisih_hari > 0:
                            angka_tgl = str(tgl_target.day)
                            bulan_id = {1:'jan', 2:'feb', 3:'mar', 4:'apr', 5:'mei', 6:'jun', 7:'jul', 8:'agu', 9:'sep', 10:'okt', 11:'nov', 12:'des'}[tgl_target.month]
                            bulan_en = {1:'jan', 2:'feb', 3:'mar', 4:'apr', 5:'may', 6:'jun', 7:'jul', 8:'aug', 9:'sep', 10:'oct', 11:'nov', 12:'dec'}[tgl_target.month]
                            
                            elements = driver.find_elements("xpath", "//button | //a | //div[@role='tab' or @role='button']")
                            berhasil_klik = False
                            
                            if selisih_hari == 1:
                                for el in elements:
                                    try:
                                        teks = el.text.strip().lower() if el.text else ""
                                        if teks in ['besok', 'tomorrow']:
                                            driver.execute_script("arguments[0].click();", el)
                                            berhasil_klik = True
                                            time.sleep(2.5)
                                            break
                                    except: pass
                            if not berhasil_klik:
                                for el in elements:
                                    try:
                                        teks = el.text.strip().lower() if el.text else ""
                                        if not teks or len(teks) > 30: continue
                                        if re.search(rf"(^|\D)0?{angka_tgl}(\D|$)", teks) and (bulan_id in teks or bulan_en in teks):
                                            driver.execute_script("arguments[0].click();", el)
                                            berhasil_klik = True
                                            time.sleep(2.5)
                                            break
                                    except: pass

                            if berhasil_klik:
                                for i in range(6):
                                    driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {(i+1)/6});")
                                    time.sleep(0.3)
                                driver.execute_script("window.scrollTo(0, 0);")
                                time.sleep(0.5)

                        # Expand Load More
                        try:
                            for btn in driver.find_elements("xpath", "//button | //span | //a"):
                                txt = btn.text.strip().lower() if btn.text else ""
                                if any(x in txt for x in ['show', 'lihat', 'lebih banyak', 'tampilkan']):
                                    driver.execute_script("arguments[0].click();", btn)
                                    time.sleep(1.0)
                                    break
                        except Exception: pass

                        soup = BeautifulSoup(driver.page_source, 'html.parser')
                        all_text = re.sub(r'\s+', ' ', soup.get_text(" ")).strip()
                        pola_jadwal = r'(\d{1,2}[:\.]\d{2})(?:\s*(?:WIB|AM|PM|am|pm))?\s*[-–—]+\s*(\d{1,2}[:\.]\d{2})(?:\s*(?:WIB|AM|PM|am|pm))?\s+(.*?)(?=\s*(?:\d{1,2}[:\.]\d{2}(?:\s*(?:WIB|AM|PM|am|pm))?\s*[-–—]+\s*\d{1,2}[:\.]\d{2})|$)'
                        semua_cocok = re.findall(pola_jadwal, all_text, flags=re.IGNORECASE)
                        
                        web_schedules = []
                        for cocok in semua_cocok:
                            start_w, end_w = fix_time(cocok[0]), fix_time(cocok[1])
                            title_w = re.sub(r'\s*LIVE\s*$', '', re.sub(r'^[Oo•-]\s*', '', cocok[2].strip()), flags=re.IGNORECASE).strip()
                            if not any(x['start'] == start_w and x['end'] == end_w for x in web_schedules):
                                web_schedules.append({
                                    'start': start_w, 'end': end_w, 
                                    'title_clean': bersihkan_teks(title_w),
                                    'title_no_space': hancurkan_spasi(title_w)
                                })
                        
                        if not web_schedules:
                            if selisih_hari > 0: lokal_errors.append(f"ℹ️ [{tgl_str}] Data EPG belum di-update di Web Vidio.")
                            else: lokal_errors.append(f"⚠️ [{tgl_str}] Gagal parsing EPG dari Web Vidio.")
                            if lokal_errors:
                                laporan_error_global.append(f"🔴 *{tab.upper()}*\n" + "\n".join([f"  • {e}" for e in lokal_errors]))
                            continue
                            
                        # 4. Pencocokan Data Mismatch
                        mismatched_programs = []
                        for _, row in df_epg.iterrows():
                            judul_csv_bersih = bersihkan_teks(row['title'])
                            judul_csv_no_space = hancurkan_spasi(row['title'])
                            start_csv = row['start_time']
                            
                            try: jam_int, menit_str = int(start_csv.split(":")[0]), start_csv.split(":")[1]
                            except: jam_int, menit_str = 0, "00"
                                
                            kemungkinan_waktu = [start_csv]
                            if jam_int <= 12: kemungkinan_waktu.append(f"{str(jam_int + 12).zfill(2)}:{menit_str}")
                            if jam_int > 12:  kemungkinan_waktu.append(f"{str(jam_int - 12).zfill(2)}:{menit_str}")

                            is_match = False
                            for web_item in web_schedules:
                                if web_item['start'] in kemungkinan_waktu:
                                    if (judul_csv_no_space in web_item['title_no_space']) or (web_item['title_no_space'] in judul_csv_no_space):
                                        is_match = True; break
                                    abaikan = ['live', 'replay', 'delay', 'delayed', 'match', 'vs', 'versus', 'champions', 'tv', 'liga', 'league']
                                    words_csv = set([w for w in judul_csv_bersih.split() if len(w) >= 3 and w not in abaikan])
                                    words_web = set([w for w in web_item['title_clean'].split() if len(w) >= 3 and w not in abaikan])
                                    intersect = words_csv.intersection(words_web)
                                    if len(intersect) >= 2 or (len(intersect) >= 1 and any(len(w) >= 3 for w in intersect)):
                                        is_match = True; break
                            if not is_match:
                                mismatched_programs.append(f"jam {start_csv} ('{row['title']}')")
                                
                        if mismatched_programs:
                            for prog in mismatched_programs:
                                lokal_errors.append(f"📊 [{tgl_str}] Mismatch di {prog}")
                            
                        if lokal_errors:
                            laporan_error_global.append(f"🔴 *{tab.upper()}*\n" + "\n".join([f"  • {e}" for e in lokal_errors]))

                    except Exception as e:
                        print(f"⚠️ Driver error saat proses tab {tab}: {e}")
                        # Auto recover browser jika Selenium crash/hang
                        try: driver.quit()
                        except: pass
                        driver = create_selenium_driver()

    finally:
        try: driver.quit()
        except: pass
        
    if laporan_error_global:
        pesan_final = f"🚨 *[EPG ALERT BOT]*\nTelah memeriksa *{total_channel_dicek} channel* untuk Hari Ini & Besok. Detail masalah:\n\n"
        pesan_final += "\n\n".join(laporan_error_global)
    else:
        pesan_final = f"✅ *[EPG SUCCESS BOT]*\nSeluruh *{total_channel_dicek} channel* telah diperiksa (Hari Ini & Besok). Jadwal 100% sinkron!"
        
    send_webhook_alert(pesan_final)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Proses selesai! Laporan dikirim.")

if __name__ == "__main__":
    jalankan_dispatcher_harian()