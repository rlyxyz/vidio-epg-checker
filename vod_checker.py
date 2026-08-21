import base64
import os
import re
import time
import unicodedata
from datetime import datetime, date, timedelta
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# =======================================================
# UI KONFIGURASI STREAMLIT (KHUSUS VOD)
# =======================================================
try:
    st.set_page_config(page_title="Vidio VOD Checker", page_icon="🔗", layout="wide")
except:
    st.set_page_config(page_title="Vidio VOD Checker", page_icon="🔗", layout="wide")

def get_base64_image(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except Exception:
        return ""

bg_image_dark = get_base64_image("bg_dark.png")
bg_image_light = get_base64_image("bg_light.png")

custom_css = f"""
<style>
[data-testid="stHeader"] {{ display: none !important; }}
[data-testid="stAppViewContainer"]::before {{
    content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%;
    background-image: url("data:image/png;base64,{bg_image_light}");
    background-size: 80%; background-position: center; background-repeat: no-repeat;
    background-attachment: fixed; opacity: 0.05; pointer-events: none; z-index: 0; 
}}
@media (prefers-color-scheme: dark) {{
    [data-testid="stAppViewContainer"]::before {{ background-image: url("data:image/png;base64,{bg_image_dark}"); opacity: 0.05; }}
}}
.main {{ z-index: 1; }}
.teks-versi {{ position: fixed; bottom: 10px; left: 15px; color: var(--text-color); opacity: 0.7; font-size: 15px; font-weight: bold; z-index: 100; }}
</style>
<div class="teks-versi">VOD Checker v1.0 &copy;Arly</div>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# =======================================================
# CONFIGURATION & CONSTANTS
# =======================================================
KNOWN_CHANNELS = {
    "TVN": "6362", "CITRA DRAMA": "21179", "ROCK ACTION": "8121",
    "TV5MONDE": "17278", "ARIRANG": "6784", "MENTARI": "8237",
    "HIP HIP HORE": "7052", "ABC AUSTRALIA": "7150", "NHK JAPAN": "7968",
    "NEWS ASIA": "6411", "DW ENGLISH": "5075", "DAYSTAR": "18622",
    "CHAMPIONS TV 1": "6685", "CHAMPIONS TV 2": "6686", "CHAMPIONS TV 3": "6786",
    "BEIN 1": "6299", "BEIN 2": "17875", "BEIN 3": "6317", "HOREE CHANNEL": "6397",
    "CHAMPIONS FIGHT": "20216", "CHAMPIONS TV 5": "9182", "CHAMPIONS TV 6": "9183",
    "CHAMPIONS TV GOLF 1": "18189", "CHAMPIONS TV GOLF 2": "18190",
    "PREMIER LEAGUE TV": "9353", "SPOTV 1": "17139", "SPOTV 2": "17140",
    "REAL MADRID TV": "19538" , "SCTV": "204" , "INDOSIAR": "205" , "MOJI": "206",
    "KOMPAS TV": "874", "RCTI": "665", "TVONE": "783", "TRANS TV": "733",
    "MDTV": "875", "GTV": "778", "MNCTV": "870", "INEWS": "5409", "BTV": "6165",
    "BERITA SATU": "18280", "JAKTV": "5415"
}

URL_SPORT = "https://docs.google.com/spreadsheets/d/1gjT0SPz5dN36MWslyDcRGYOfzmkfTFg4LQKXZfRDhYo/edit?gid=1710292612#gid=1710292612"
URL_NON_SPORT = "https://docs.google.com/spreadsheets/d/1T9jQGWJHEwzb85tpTLdbo8nyrmnLoLanXk7TxGWEzxM/edit?gid=217062556#gid=217062556"

def fix_time(t):
    if not t: return "00:00"
    t = str(t).strip().replace('.', ':')
    if ":" in t:
        parts = t.split(":")
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)[:2]}"
    return t[:5]

@st.cache_resource
def init_gspread():
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly"]
    try:
        if os.path.exists("credentials.json"):
            import json
            with open("credentials.json", "r") as f: creds_dict = json.load(f)
        else:
            creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(credentials)
    except Exception as e:
        st.error(f"Gagal membaca rahasia (Secrets). Error: {e}")
        st.stop()

@st.cache_data(ttl=300)
def fetch_valid_tabs(url):
    gc = init_gspread()
    sh = gc.open_by_url(url)
    valid_tabs = []
    for ws in sh.worksheets():
        t = ws.title.upper()
        if ("HASIL" in t or "TO CSV" in t) and not any(x in t for x in ["COPY", "TRIAL", "TES", "TEST"]):
            valid_tabs.append(ws.title)
    return valid_tabs

# =======================================================
# MAIN WEB APP TAMPILAN
# =======================================================
col_logo, col_title = st.columns([1, 15])
with col_logo:
    st.markdown("🔗") 
with col_title: 
    st.title("Vidio VOD (Catch-up) Checker")
st.markdown("---")

col1, col2, col3 = st.columns(3)
with col1:
    kategori = st.selectbox("1. Pilih Kategori EPG:", ["⚽ Sports", "📺 Non-Sports"])
    target_url = URL_SPORT if kategori == "⚽ Sports" else URL_NON_SPORT
with col2:
    try: valid_tabs = fetch_valid_tabs(target_url)
    except Exception as e:
        st.error(f"Gagal terhubung ke Google Sheets. Error: {e}")
        st.stop()
    pilihan_tab = st.selectbox("2. Pilih Channel (Tab):", valid_tabs)

with col3: pilihan_tgl = st.date_input("3. Pilih Tanggal Jadwal:", value=date.today())
st.markdown("<br>", unsafe_allow_html=True)

if st.button("🔍 Cek Ketersediaan VOD Sekarang", type="primary", use_container_width=True):
    
    # Ambil ID Channel
    raw_name = re.sub(r'[^\w\s]', '', pilihan_tab.upper()) 
    for kata in ['TO CSV', 'HASIL CSV', 'HASIL', 'CSV', 'JADWAL', 'WIB']:
        raw_name = raw_name.replace(kata, ' ')
    channel_name = re.sub(r'\s+', ' ', raw_name).strip()
    
    exact_aliases = {
        'PLTV': 'PREMIER LEAGUE TV', 'RMTV': 'REAL MADRID TV',
        'CGOLF 1': 'CHAMPIONS TV GOLF 1', 'CGOLF 2': 'CHAMPIONS TV GOLF 2', 'CGOLF': 'CHAMPIONS TV GOLF',
        'CTV 1': 'CHAMPIONS TV 1', 'CTV 2': 'CHAMPIONS TV 2', 'CTV 3': 'CHAMPIONS TV 3',
        'CTV 4': 'CHAMPIONS TV 4', 'CTV 5': 'CHAMPIONS TV 5', 'CTV 6': 'CHAMPIONS TV 6', 'CTV': 'CHAMPIONS TV',
        'TTV': 'TRANS TV'
    }
    if channel_name in exact_aliases: channel_name = exact_aliases[channel_name]
    
    if channel_name in KNOWN_CHANNELS: channel_id = KNOWN_CHANNELS[channel_name]
    else:
        st.error(f"Channel '{channel_name}' belum ada di database.")
        st.stop()
        
    url_vidio = f"https://www.vidio.com/live/{channel_id}"
    target_date_obj = pilihan_tgl

    with st.status("Memulai Robot Pengecek VOD...", expanded=True) as status:
        st.write(f"Menghubungkan ke web Vidio (ID: {channel_id})...")
        
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium.webdriver.chrome.service import Service as ChromeService
        from webdriver_manager.chrome import ChromeDriverManager

        options = ChromeOptions()
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])

        try:
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            st.error(f"❌ Robot gagal menyala: {e}")
            st.stop()
            
        try:
            driver.get(url_vidio) 
            st.write("Memicu muat ulang halaman dengan Tunggu Cerdas...")
            for i in range(12): 
                driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {(i+1)/12});")
                time.sleep(1) 
                if re.search(r'\d{2}[:\.]\d{2}\s*[-–\s]*\s*\d{2}[:\.]\d{2}', driver.page_source):
                    break 
            
            driver.execute_script("window.scrollTo(0, 0);") 
            time.sleep(1)
            
            st.write(f"Menavigasi kalender ke tanggal {target_date_obj.strftime('%d-%m-%Y')}...")
            selisih_hari = (target_date_obj - date.today()).days
            if selisih_hari > 0:
                angka_tgl = str(target_date_obj.day)
                bulan_map = {1: 'jan', 2: 'feb', 3: 'mar', 4: 'apr', 5: 'mei', 6: 'jun', 7: 'jul', 8: 'agu', 9: 'sep', 10: 'okt', 11: 'nov', 12: 'des'}
                keyword_bulan = bulan_map[target_date_obj.month]
                elements = driver.find_elements("xpath", "//span | //button | //a | //div")
                
                berhasil_klik = False
                if selisih_hari == 1:
                    for el in elements:
                        teks = el.text.strip().lower() if el.text else ""
                        if 'besok' in teks or 'tomorrow' in teks:
                            if len(teks) < 30:
                                driver.execute_script("arguments[0].click();", el)
                                berhasil_klik = True
                                time.sleep(5)
                                break
                if not berhasil_klik:
                    elements_sorted = sorted(elements, key=lambda x: len(x.text.strip()) if x.text else 999)
                    for el in elements_sorted:
                        teks = el.text.strip().lower() if el.text else ""
                        if not teks or len(teks) > 40: continue
                        match_angka = re.search(rf"(^|\D)0?{angka_tgl}(\D|$)", teks)
                        if match_angka and keyword_bulan in teks:
                            driver.execute_script("arguments[0].click();", el)
                            time.sleep(5)
                            break
            
            # Show more
            try:
                for btn in driver.find_elements("xpath", "//button | //span | //a"):
                    txt = btn.text.strip().lower() if btn.text else ""
                    if 'show' in txt or 'lihat' in txt or 'more' in txt:
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(2)
                        break
            except Exception: pass
            
            st.write("Menganalisa tautan (Link VOD)...")
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            status.update(label="Analisa Selesai!", state="complete", expanded=False)
        finally:
            driver.quit() 

    st.markdown(f"### 🔗 Laporan Ketersediaan VOD - {channel_name} ({pilihan_tgl.strftime('%d-%m-%Y')})")
    web_schedules_vod = []
    
    for element in soup.find_all(['div', 'li', 'p', 'span', 'a']):
        text_item = element.get_text(" ").strip()
        if not text_item or len(text_item) > 300: continue
        
        pattern = r'(\d{2}[:\.]\d{2})\s*[-–\s]*\s*(\d{2}[:\.]\d{2})\s+(.*)'
        match = re.search(pattern, text_item)
        
        if match:
            start_w, end_w, title_w = fix_time(match.group(1)), fix_time(match.group(2)), match.group(3).strip()
            title_w = re.sub(r'\s*•\s*live.*', '', title_w, flags=re.IGNORECASE)
            
            a_tag = element if element.name == 'a' else element.find_parent('a')
            has_link = False
            link_url = "-"
            status_vod = "❌ Belum Ada / Live"
            
            if a_tag and a_tag.has_attr('href'):
                href = a_tag['href']
                if href and href != "#" and "/live/" not in href:
                    has_link = True
                    link_url = f"https://www.vidio.com{href}" if href.startswith('/') else href
                    status_vod = "✅ Ada Link VOD"
            
            if not any(x['Jam Tayang'] == f"{start_w} - {end_w}" for x in web_schedules_vod):
                web_schedules_vod.append({
                    'Jam Tayang': f"{start_w} - {end_w}",
                    'Judul Program di Vidio': title_w,
                    'Status Link': status_vod,
                    'URL Tersembunyi': link_url
                })
    
    if web_schedules_vod:
        df_vod = pd.DataFrame(web_schedules_vod)
        
        def highlight_status(val):
            color = '#1f77b4' if '✅' in str(val) else '#d62728'
            return f'color: {color}; font-weight: bold'
            
        st.dataframe(df_vod.style.map(highlight_status, subset=['Status Link']), use_container_width=True)
        st.info("💡 **Catatan:** Jika statusnya '❌ Belum Ada / Live', program tersebut mungkin belum selesai tayang. Link VOD otomatis ditanam oleh Vidio setelah acara selesai (Past Event).")
    else:
        st.error("Jadwal tidak terbaca dari web Vidio. Halaman mungkin kosong.")