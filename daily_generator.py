import base64
import os
import re
import unicodedata
from datetime import datetime, date, timedelta
import pandas as pd
from bs4 import BeautifulSoup
import requests
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# =======================================================
# UI KONFIGURASI STREAMLIT
# =======================================================
try:
    st.set_page_config(page_title="Vidio EPG Checker", page_icon="logo_v.jpeg", layout="wide")
except:
    st.set_page_config(page_title="Vidio EPG Checker", page_icon="📺", layout="wide")

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
<div class="teks-versi">Version 0.1 &copy;Arly</div>
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
    "CHAMPIONS FIGHT": "20216", "CHAMPIONS TV 5" : "9182", "CHAMPIONS TV 6" : "9183",
    "CHAMPIONS TV GOLF 1" : "18189", "CHAMPIONS TV GOLF 2" : "18190",
    "PREMIER LEAGUE TV" : "9353", "SPOTV 1" : "17139", "SPOTV 2" : "17140",
    "REAL MADRID TV" : "19538" , "SCTV" : "204" , "INDOSIAR" : "205" , "MOJI" : "206"
}

URL_SPORT = "https://docs.google.com/spreadsheets/d/1gjT0SPz5dN36MWslyDcRGYOfzmkfTFg4LQKXZfRDhYo/edit?gid=1710292612#gid=1710292612"
URL_NON_SPORT = "https://docs.google.com/spreadsheets/d/1T9jQGWJHEwzb85tpTLdbo8nyrmnLoLanXk7TxGWEzxM/edit?gid=217062556#gid=217062556"

def bersihkan_teks(teks):
    if not teks: return ""
    teks = str(teks).lower()
    teks = re.sub(r'\(.*?\)', '', teks)
    teks = unicodedata.normalize('NFD', teks)
    teks = "".join([c for c in teks if unicodedata.category(c) != 'Mn'])
    teks = teks.replace('’', "'").replace('`', "'").replace('“', "").replace('”', "")
    teks = teks.replace('-', '').replace('_', '').replace(':', '').replace("'", "")
    teks = teks.replace('\xa0', ' ').replace('\n', ' ').replace('\t', ' ')
    return re.sub(r'\s+', ' ', teks).strip()

def hancurkan_spasi(teks): return bersihkan_teks(teks).replace(" ", "")

def fix_time(t):
    if not t: return "00:00"
    t = str(t).strip().replace('.', ':')
    if ":" in t:
        parts = t.split(":")
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)[:2]}"
    return t[:5]

def normalisasi_tanggal(tgl_str):
    tgl_str = str(tgl_str).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try: return datetime.strptime(tgl_str, fmt).date()
        except ValueError: continue
    return None

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

@st.cache_data(ttl=300)
def fetch_sheet_data(url, tab_name):
    gc = init_gspread()
    sh = gc.open_by_url(url)
    data_mentah = sh.worksheet(tab_name).get_all_values()
    if len(data_mentah) < 2: return pd.DataFrame()
    return pd.DataFrame(data_mentah[1:], columns=data_mentah[0])

# =======================================================
# MAIN WEB APP TAMPILAN
# =======================================================
col_logo, col_title = st.columns([1, 15])
with col_logo:
    try: st.image("logo_v.jpeg", width=60)
    except: st.write("V") 
with col_title: st.title("Vidio EPG Checker")
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
    if not valid_tabs:
        st.error("Tidak ada tab hasil/to csv yang ditemukan!")
        st.stop()
    pilihan_tab = st.selectbox("2. Pilih Channel (Tab):", valid_tabs)

raw_df = fetch_sheet_data(target_url, pilihan_tab)
if raw_df.empty:
    st.warning("Data di dalam tab ini kosong.")
    st.stop()

cols_lower = [str(c).lower() for c in raw_df.columns]
if 'attribute:start_date' in cols_lower:
    col_date = [c for c in raw_df.columns if 'start_date' in c.lower()][0]
    col_title = [c for c in raw_df.columns if 'title' in c.lower()][0]
    col_start = [c for c in raw_df.columns if 'start_time' in c.lower()][0]
    col_end = [c for c in raw_df.columns if 'end_time' in c.lower()][0]
else:
    col_date = [c for c in raw_df.columns if 'tanggal' in c.lower() or 'date' in c.lower()][0]
    col_title = [c for c in raw_df.columns if 'nama program' in c.lower() or 'judul' in c.lower() or 'title' in c.lower()][0]
    col_start = [c for c in raw_df.columns if 'jam tayang' in c.lower() or 'start_time' in c.lower()][0]
    col_end = [c for c in raw_df.columns if 'jam selesai' in c.lower() or 'end_time' in c.lower()][0]

raw_df['parsed_date_obj'] = raw_df[col_date].apply(normalisasi_tanggal)

with col3: pilihan_tgl = st.date_input("3. Pilih Tanggal Jadwal:", value=date.today())
st.markdown("<br>", unsafe_allow_html=True)

if st.button("🚀 Jalankan Pengecekan Harian", type="primary", use_container_width=True):
    target_date_obj = pilihan_tgl
    df_filtered = raw_df[raw_df['parsed_date_obj'] == target_date_obj].copy()
    
    if df_filtered.empty:
        st.error(f"❌ Tidak ada data jadwal untuk tanggal {target_date_obj.strftime('%d-%m-%Y')}.")
        st.stop()
        
    df_epg = df_filtered[[col_title, col_start, col_end]].copy()
    df_epg.columns = ['title', 'start_time', 'end_time']
    df_epg['start_time'] = df_epg['start_time'].apply(fix_time)
    df_epg['end_time'] = df_epg['end_time'].apply(fix_time)
    
    raw_name = re.sub(r'[^\w\s]', '', pilihan_tab.upper()) 
    for kata in ['TO CSV', 'HASIL CSV', 'HASIL', 'CSV', 'JADWAL', 'WIB']:
        raw_name = raw_name.replace(kata, ' ')
    channel_name = re.sub(r'\s+', ' ', raw_name).strip()
    
    exact_aliases = {
        'PLTV': 'PREMIER LEAGUE TV', 'RMTV': 'REAL MADRID TV',
        'CGOLF 1': 'CHAMPIONS TV GOLF 1', 'CGOLF 2': 'CHAMPIONS TV GOLF 2', 'CGOLF': 'CHAMPIONS TV GOLF',
        'CTV 1': 'CHAMPIONS TV 1', 'CTV 2': 'CHAMPIONS TV 2', 'CTV 3': 'CHAMPIONS TV 3',
        'CTV 4': 'CHAMPIONS TV 4', 'CTV 5': 'CHAMPIONS TV 5', 'CTV 6': 'CHAMPIONS TV 6', 'CTV': 'CHAMPIONS TV',
        'HIP HIP HOREE': 'HIP HIP HORE', 'HOREE': 'HOREE CHANNEL', 'HORE': 'HOREE CHANNEL',           
        'ABC': 'ABC AUSTRALIA', 'NHK': 'NHK JAPAN'
    }
    if channel_name in exact_aliases: channel_name = exact_aliases[channel_name]
    
    if channel_name in KNOWN_CHANNELS: channel_id = KNOWN_CHANNELS[channel_name]
    else:
        st.error(f"Channel '{channel_name}' belum ada di database KNOWN_CHANNELS.")
        st.stop()
        
    url_vidio = f"https://www.vidio.com/live/{channel_id}"

    with st.status("Memulai Robot Scraping...", expanded=True) as status:
        st.write(f"Menghubungkan senyap ke Vidio API (ID: {channel_id})...")
        
        # --- JURUS OPERASI SENYAP (TANPA BROWSER / REQUESTS ONLY) ---
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.vidio.com/"
        }
        
        try:
            response = requests.get(url_vidio, headers=headers, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')
            web_schedules = []
            
            st.write("Mengekstrak data jadwal...")
            for element in soup.find_all(['div', 'li', 'p', 'span']):
                text_item = element.get_text(" ").strip()
                if not text_item or len(text_item) > 300: continue
                pattern = r'(\d{2}[:\.]\d{2})\s*[-–]\s*(\d{2}[:\.]\d{2})\s+(.*)'
                match = re.search(pattern, text_item)
                if match:
                    start_w, end_w, title_w = fix_time(match.group(1)), fix_time(match.group(2)), match.group(3).strip()
                    title_w = re.sub(r'\s*•\s*live.*', '', title_w, flags=re.IGNORECASE)
                    if not any(x['start'] == start_w and x['end'] == end_w for x in web_schedules):
                        web_schedules.append({'start': start_w, 'end': end_w, 'title_clean': bersihkan_teks(title_w), 'title_no_space': hancurkan_spasi(title_w)})
            
            if not web_schedules:
                clean_text = re.sub(r'\s+', ' ', soup.get_text(" "))
                fallback_matches = re.findall(r'(\d{2}[:\.]\d{2})\s*[-–]\s*(\d{2}[:\.]\d{2})\s+(.*?)(?=\s+\d{2}[:\.]\d{2}\s*[-–]|$)', clean_text)
                web_schedules = [{'start': fix_time(m[0]), 'end': fix_time(m[1]), 'title_clean': bersihkan_teks(m[2]), 'title_no_space': hancurkan_spasi(m[2])} for m in fallback_matches]
            
            status.update(label="Scraping Selesai! Melakukan Verifikasi Sinkronisasi...", state="complete", expanded=False)
        except Exception as e:
            st.error(f"Gagal mengambil data dari Vidio: {e}")
            st.stop()

    if not web_schedules:
        st.error("Jadwal tidak terbaca. Struktur halaman Vidio kosong atau Anda terblokir sistem keamanan.")
        st.stop()
        
    hasil_error = []
    
    for _, row in df_epg.iterrows():
        judul_csv_bersih = bersihkan_teks(row['title'])
        judul_csv_no_space = hancurkan_asli = hancurkan_spasi(row['title'])
        start_csv = row['start_time']
        
        try: jam_int = int(start_csv.split(":")[0]); menit_str = start_csv.split(":")[1]
        except: jam_int, menit_str = 0, "00"
            
        kemungkinan_waktu = [start_csv]
        if jam_int <= 12: kemungkinan_waktu.append(f"{str(jam_int + 12).zfill(2)}:{menit_str}")
        if jam_int > 12:  kemungkinan_waktu.append(f"{str(jam_int - 12).zfill(2)}:{menit_str}")
        try:
            t_shift = datetime.strptime(start_csv, "%H:%M") - timedelta(hours=1, minutes=5)
            kemungkinan_waktu.append(f"{str(t_shift.hour).zfill(2)}:{str(t_shift.minute).zfill(2)}")
        except: pass

        is_match = False
        for web_item in web_schedules:
            if web_item['start'] in kemungkinan_waktu:
                if (judul_csv_no_space in web_item['title_no_space']) or (web_item['title_no_space'] in judul_csv_no_space):
                    is_match = True
                    break
                abaikan = ['live', 'replay', 'delay', 'delayed', 'match', 'vs', 'versus', 'champions', 'tv', 'liga', 'league']
                words_csv = set([w for w in judul_csv_bersih.split() if len(w) >= 3 and w not in abaikan])
                words_web = set([w for w in web_item['title_clean'].split() if len(w) >= 3 and w not in abaikan])
                intersect = words_csv.intersection(words_web)
                if len(intersect) >= 2 or (len(intersect) >= 1 and any(len(w) >= 3 for w in intersect)):
                    is_match = True
                    break

        if not is_match:
            hasil_error.append({"Jam Mulai": row['start_time'], "Jam Selesai": row['end_time'], "Judul Program": row['title']})

    st.markdown("### 📊 Laporan Hasil Pengecekan")
    if len(hasil_error) == 0:
        st.success(f"🎉 SUKSES! 100% Jadwal Sinkron untuk {channel_name} (Tanggal: {pilihan_tgl.strftime('%d-%m-%Y')})")
        st.balloons()
    else:
        st.error(f"⚠️ Ditemukan {len(hasil_error)} jadwal di Spreadsheet yang BELUM ADA / BERBEDA dengan tayangan live di Vidio:")
        st.dataframe(pd.DataFrame(hasil_error), use_container_width=True)