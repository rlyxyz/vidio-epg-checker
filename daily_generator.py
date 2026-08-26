import base64
import io
import os
import re
import time
import json
import requests
import unicodedata
import threading
from datetime import datetime, date, timedelta
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image
if "cms_text_data" not in st.session_state:
    st.session_state["cms_text_data"] = ""

def sync_channel_callback():
    st.session_state["active_channel"] = st.session_state["sync_channel_select"]

# =======================================================
# STREAMLIT CONFIGURATION UI
# =======================================================
try:
    favicon_img = Image.open("logo_v.jpeg")
    st.set_page_config(page_title="Vidio EPG Checker", page_icon=favicon_img, layout="wide", initial_sidebar_state="collapsed")
except:
    st.set_page_config(page_title="Vidio EPG Checker", page_icon="📺", layout="wide", initial_sidebar_state="collapsed")

def get_base64_image(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except Exception:
        return ""

bg_image_dark = get_base64_image("bg_dark.png")
bg_image_light = get_base64_image("bg_light.png")

# =======================================================
# CUSTOM CHANNELS MANAGER
# =======================================================
CUSTOM_CHANNELS_FILE = "custom_channels.json"
KNOWN_CHANNELS_BASE = {}

def load_custom_channels():
    if os.path.exists(CUSTOM_CHANNELS_FILE):
        try:
            with open(CUSTOM_CHANNELS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_custom_channels(channels_dict):
    try:
        with open(CUSTOM_CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(channels_dict, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving custom channels: {e}")
        return False

KNOWN_CHANNELS = KNOWN_CHANNELS_BASE.copy()
KNOWN_CHANNELS.update(load_custom_channels())

# =======================================================
# UTILITIES & NORMALIZATION
# =======================================================
def load_cookie_from_file():
    if os.path.exists("cookies.json"):
        try:
            with open("cookies.json", "r", encoding="utf-8") as f:
                return json.load(f).get("cookie_string", "")
        except Exception:
            return ""
    return ""

def bersihkan_teks(teks):
    if not teks: return ""
    teks = str(teks).lower()
    teks = re.sub(r'\(.*?\)', '', teks)
    teks = unicodedata.normalize('NFD', teks)
    teks = "".join([c for c in teks if unicodedata.category(c) != 'Mn'])
    teks = teks.replace('’', "'").replace('`', "'").replace('“', "").replace('”', "")
    teks = teks.replace('-', ' ').replace('_', ' ').replace(':', '').replace("'", "")
    re.sub(r'[\u2013\u2014]', ' ', teks)
    teks = teks.replace('\xa0', ' ').replace('\n', ' ').replace('\t', ' ')
    return re.sub(r'\s+', ' ', teks).strip()

def hancurkan_spasi(teks): 
    teks_content = bersihkan_teks(teks)
    return re.sub(r'[^a-z0-9]', '', teks_content)

def fix_time(t):
    if not t: return "00:00"
    t = str(t).strip().replace('.', ':')
    if ":" in t:
        parts = t.split(":")
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)[:2]}"
    return t[:5]

def normalisasi_tanggal(tgl_str):
    tgl_str = str(tgl_str).strip()
    if " " in tgl_str:
        tgl_str = tgl_str.split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try: return datetime.strptime(tgl_str, fmt).date()
        except ValueError: continue
    return None

def save_channel_callback():
    name_val = st.session_state.get("new_ch_name", "").strip()
    id_val = st.session_state.get("new_ch_id", "").strip()
    if name_val and id_val:
        custom_channels = load_custom_channels()
        clean_name = name_val.upper()
        custom_channels[clean_name] = id_val
        if save_custom_channels(custom_channels):
            st.session_state["channel_success_msg"] = f"Saved {clean_name} successfully into custom database!"
            st.session_state["expander_expanded"] = True
            st.session_state["new_ch_name"] = ""
            st.session_state["new_ch_id"] = ""
        else:
            st.session_state["channel_error_msg"] = "Failed to save channel to local storage."
    else:
        st.session_state["channel_error_msg"] = "Please fill both fields."

@st.cache_resource(show_spinner=False)
def get_scraper_lock():
    return threading.Lock()

antrean_lock = get_scraper_lock()

@st.cache_resource(show_spinner=False)
def init_gspread():
    scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
    try:
        if os.path.exists("credentials.json"):
            with open("credentials.json", "r") as f: creds_dict = json.load(f)
        else:
            creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(credentials)
    except Exception as e:
        st.error(f"Failed to authenticate GCP Google Sheets API. Error: {e}")
        st.stop()

@st.cache_data(ttl=10, show_spinner=False)
def fetch_valid_tabs(url):
    gc = init_gspread()
    sh = gc.open_by_url(url)
    valid_tabs = []
    for ws in sh.worksheets():
        t = ws.title.upper()
        if ("HASIL" in t or "TO CSV" in t) and not any(x in t for x in ["COPY", "TRIAL", "TES", "TEST"]):
            valid_tabs.append(ws.title)
    return valid_tabs

@st.cache_data(ttl=10, show_spinner=False)
def fetch_sheet_data(url, tab_name):
    gc = init_gspread()
    sh = gc.open_by_url(url)
    data_mentah = sh.worksheet(tab_name).get_all_values()
    if len(data_mentah) < 2: return pd.DataFrame()
    return pd.DataFrame(data_mentah[1:], columns=data_mentah[0])
    # =======================================================
# MODERN CSS CODE & HERO SECTION WITH COMPLETE LAYOUT ARCHITECTURE
# =======================================================
custom_css = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;700;800&display=swap');

html, body, [class*="css"] {{ font-family: 'Poppins', sans-serif !important; }}
[data-testid="stHeader"] {{ background: transparent !important; }}
.block-container {{ padding-top: 2rem !important; max-width: 1200px !important; }}

[data-testid="stAppToolbar"], .stAppToolbar {{
    display: none !important;
}}

[data-testid="stStatusWidget"], .stStatusWidget, [data-testid="stHeader"] {{
    display: none !important;
    visibility: hidden !important;
    opacity: 0 !important;
}}

[data-testid="stExpander"] {{
    border-radius: 12px !important;
    backdrop-filter: blur(12px) !important;
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1) !important;
}}

[data-testid="stExpander"] summary {{
    background-color: transparent !important;
    padding: 12px 18px !important;
}}

[data-testid="stExpander"] summary p {{
    font-weight: 700 !important;
    text-transform: uppercase !important; 
    letter-spacing: 1.5px !important; 
    font-size: 13px !important;
    transition: color 0.3s ease !important;
}}

[data-testid="stExpander"] [data-testid="stExpanderToggleIcon"],
[data-testid="stExpander"] summary svg,
[data-testid="stExpander"] summary svg *,
[data-testid="stExpander"] summary path {{
    stroke-width: 3px !important; 
    stroke-opacity: 1 !important;
    opacity: 1 !important;
    visibility: visible !important;
    transition: all 0.3s ease !important;
}}

body.dark-theme [data-testid="stExpander"] {{
    background-color: rgba(20, 20, 20, 0.55) !important;
    border: 1px solid rgba(255, 255, 255, 0.06) !important;
    border-left: 4px solid #ff5252 !important;
}}
body.dark-theme [data-testid="stExpander"] summary p {{
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}}
body.dark-theme [data-testid="stExpander"] [data-testid="stExpanderToggleIcon"],
body.dark-theme [data-testid="stExpander"] summary svg,
body.dark-theme [data-testid="stExpander"] summary svg *,
body.dark-theme [data-testid="stExpander"] summary path {{
    fill: #ffffff !important;
    color: #ffffff !important;
    stroke: #ffffff !important;
}}
body.dark-theme [data-testid="stExpander"]:hover {{
    border-color: #ff5252 !important;
    box-shadow: 0 0 35px rgba(255, 0, 0, 0.75), 0 0 15px rgba(255, 82, 82, 0.9) !important;
}}

body.light-theme [data-testid="stExpander"] {{
    background-color: #ffffff !important;
    border: 1px solid rgba(0, 0, 0, 0.08) !important;
    border-left: 4px solid #ff5252 !important;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.03) !important;
}}
body.light-theme [data-testid="stExpander"] summary p {{
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}}

body.light-theme [data-testid="stExpander"] [data-testid="stExpanderToggleIcon"],
body.light-theme [data-testid="stExpander"] summary svg,
body.light-theme [data-testid="stExpander"] summary svg *,
body.light-theme [data-testid="stExpander"] summary path {{
    fill: #000000 !important;
    color: #000000 !important;
    stroke: #000000 !important;
    stroke-width: 3.5px !important;
    opacity: 1 !important;
}}

body.light-theme [data-testid="stExpander"]:hover {{
    background-color: #ffffff !important;
    border-color: #ff5252 !important;
    box-shadow: 0 0 35px rgba(255, 0, 0, 0.65), 0 0 15px rgba(255, 82, 82, 0.8) !important;
    transform: translateY(-1px);
}}

.theme-toggle-container {{
    position: fixed; top: 20px; right: 25px; z-index: 999999; transform: scale(0.65); transform-origin: top right;
}}
.toggle-switch {{
    position: relative; width: 100px; height: 50px;
}}
.switch-label {{
    position: absolute; width: 100%; height: 50px; background-color: #141517; border-radius: 25px; cursor: pointer; border: 3px solid #2d3139; transition: all 0.3s ease;
}}
body.light-theme .switch-label {{
    background-color: #ebf0f5; border-color: #cbd5e1;
}}

.checkbox, input[type="checkbox"], #custom-theme-toggle {{
    display: none !important;
    visibility: hidden !important;
    opacity: 0 !important;
    position: absolute !important;
    width: 0 !important;
    height: 0 !important;
    appearance: none !important;
    -webkit-appearance: none !important;
}}
div[data-testid="stInputInstructions"],
small[data-testid="stWidgetInstructions"],
[data-testid="stWidgetInstructions"] {{
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
}}
.slider {{
    position: absolute; width: 34px; height: 34px; top: 5px; left: 6px; border-radius: 50%; transition: all 0.4s cubic-bezier(0.25, 0.8, 0.25, 1);
    background-color: #f6f1d5; box-shadow: 0 0 15px #f6f1d5, inset -4px -4px 0px rgba(0,0,0,0.1);
}}
.slider::before {{
    content: ""; position: absolute; width: 8px; height: 8px; top: 6px; left: 18px; border-radius: 50%; background-color: #e5dec2; opacity: 0.7; transition: all 0.3s ease;
}}
.slider::after {{
    content: ""; position: absolute; width: 30px; height: 34px; top: -5px; left: 14px; border-radius: 50%; background-color: #141517; transition: all 0.4s ease; opacity: 1;
}}
body.light-theme .slider {{
    transform: translateX(48px); background-color: #ffaa00; box-shadow: 0 0 25px #ffaa00, 0 0 10px #ffea00;
}}
body.light-theme .slider::before {{
    opacity: 0; transform: scale(0);
}}
body.light-theme .slider::after {{
    opacity: 0; transform: scale(0); background-color: #ebf0f5;
}}

body.light-theme {{ --text-color: #000000 !important; --app-bg: #ffffff !important; --hero-sub: #666666 !important; --glass-bg: rgba(255, 255, 255, 0.85) !important; --glass-border: rgba(0, 0, 0, 0.15) !important; --glass-shadow: 0 4px 15px rgba(0, 0, 0, 0.05) !important; }}
body.dark-theme {{ --text-color: #ffffff !important; --app-bg: #0e1117 !important; --hero-sub: #a0a0a0 !important; --glass-bg: rgba(30, 30, 30, 0.7) !important; --glass-border: rgba(255, 255, 255, 0.1) !important; --glass-shadow: 0 4px 15px rgba(0, 0, 0, 0.3) !important; }}

.stApp, [data-testid="stAppViewContainer"] {{ background-color: var(--app-bg) !important; transition: background-color 0.4s ease; }}
[data-testid="stAppViewContainer"]::before {{ content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-size: 80%; background-position: center; background-repeat: no-repeat; background-attachment: fixed; pointer-events: none; z-index: 0; transition: background-image 0.4s ease; }}
body.light-theme [data-testid="stAppViewContainer"]::before {{ background-image: url("data:image/png;base64,{bg_image_light}"); opacity: 0.05; }}
body.dark-theme [data-testid="stAppViewContainer"]::before {{ background-image: url("data:image/png;base64,{bg_image_dark}"); opacity: 0.05; }}

.teks-versi {{ position: fixed; bottom: 10px; left: 15px; opacity: 0.4; font-size: 12px; font-weight: normal; z-index: 100; color: var(--text-color) !important; transition: color 0.4s ease; }}

body.light-theme .stMarkdown p, 
body.light-theme .stMarkdown span:not(.hero-subtitle):not(.total-channels-label), 
body.light-theme h2, 
body.light-theme h3, 
body.light-theme h4 {{ 
    color: #000000 !important; 
}}
body.dark-theme .stMarkdown p, 
body.dark-theme .stMarkdown span:not(.hero-subtitle):not(.total-channels-label), 
body.dark-theme h2, 
body.dark-theme h3, 
body.dark-theme h4 {{ 
    color: #ffffff !important; 
}}

.hero-box {{ 
    text-align: center; 
    padding: 30px 0 20px 0; 
}}

.hero-subtitle {{ 
    font-size: 12.5px !important;
    font-weight: 700 !important;
    letter-spacing: 4px !important;
    text-transform: uppercase !important;
    color: var(--hero-sub) !important; 
    transition: color 0.4s ease;
    margin-top: -6px !important;
    display: block !important;
    opacity: 0.85 !important;
}}

body.light-theme .hero-dark-header {{ display: none !important; }}
body.light-theme .hero-light-header {{ display: block !important; }}
body.dark-theme .hero-dark-header {{ display: block !important; }}
body.dark-theme .hero-light-header {{ display: none !important; }}

@keyframes running-laser-sweep {{
    0% {{ background-position: 0% center; }}
    100% {{ background-position: -200% center; }}
}}

.hero-box::after {{
    content: "" !important;
    display: block !important;
    width: 100px !important;
    height: 3.5px !important; 
    margin: 15px auto 0 auto !important;
    border-radius: 99px !important;
}}
body.light-theme .hero-box::after {{
    background: linear-gradient(90deg, #cc0914, #ff999d, #cc0914) !important;
    background-size: 200% auto !important;
    animation: running-laser-sweep 4s linear infinite !important;
    box-shadow: 0 2px 8px rgba(255, 30, 38, 0.4) !important;
}}
body.dark-theme .hero-box::after {{
    background: linear-gradient(90deg, #b30006, #ffffff, #b30006) !important;
    background-size: 200% auto !important;
    animation: running-laser-sweep 4s linear infinite !important;
    box-shadow: 0 0 12px #ff2e35, 0 0 22px rgba(255, 46, 53, 0.5) !important;
}}

.stSelectbox > div > div, .stDateInput > div > div, .stTextInput > div > div {{ border-radius: 0.625em !important; border: none !important; background: black !important; color: white !important; font-size: 16px !important; font-weight: bold !important; position: relative !important; z-index: 1 !important; overflow: hidden !important; transition: all 0.5s !important; }}
.stSelectbox div, .stSelectbox p, .stSelectbox span, .stSelectbox input, .stDateInput div, .stDateInput p, .stDateInput span, .stDateInput input, .stTextInput div, .stTextInput p, .stTextInput span, .stTextInput input {{ color: #ffffff !important; -webkit-text-fill-color: #ffffff !important; transition: color 0.3s ease !important; }}
.stSelectbox > div > div::after, .stDateInput > div > div::after, .stTextInput > div > div::after {{ content: "" !important; background: white !important; position: absolute !important; z-index: -1 !important; left: -20% !important; right: -20% !important; top: 0 !important; bottom: 0 !important; transform: skewX(-45deg) scale(0, 1) !important; transition: all 0.5s !important; }}
.stSelectbox > div > div:hover::after, .stDateInput > div > div:hover::after, .stTextInput > div > div:hover::after {{ transform: skewX(-45deg) scale(1, 1) !important; }}
.stSelectbox > div > div:hover *, .stDateInput > div > div:hover *, .stTextInput > div > div:hover * {{ color: black !important; -webkit-text-fill-color: black !important; }}
.stSelectbox svg {{ fill: white !important; transition: fill 0.5s !important; }}
.stSelectbox > div > div:hover svg {{ fill: black !important; }}
.stSelectbox > div > div:hover, .stDateInput > div > div:hover {{ cursor: pointer !important; }}

div[data-testid="stButton"] button:not([kind="secondary"]):not([data-testid="stBaseButton-secondary"]) {{
    font-weight: 900 !important; 
    text-transform: uppercase !important; 
    border-radius: 99rem !important; 
    padding: 0.8rem 1rem !important; 
    width: 100% !important; 
    transition: all 0.3s cubic-bezier(0.3, 0.7, 0.4, 1) !important; 
    box-shadow: none !important; 
}}
div[data-testid="stButton"] button:not([kind="secondary"]):not([data-testid="stBaseButton-secondary"]) *,
div[data-testid="stButton"] button:not([kind="secondary"]):not([data-testid="stBaseButton-secondary"]) {{
    font-size: 20px !important; 
    font-weight: 900 !important; 
    text-transform: uppercase !important;
}}

body.dark-theme div[data-testid="stButton"] button:not([kind="secondary"]):not([data-testid="stBaseButton-secondary"]) {{
    background-color: #000000 !important; 
    border: 2px solid #ffffff !important; 
}}
body.dark-theme div[data-testid="stButton"] button:not([kind="secondary"]):not([data-testid="stBaseButton-secondary"]) *,
body.dark-theme div[data-testid="stButton"] button:not([kind="secondary"]):not([data-testid="stBaseButton-secondary"]) {{
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}}
body.dark-theme div[data-testid="stButton"] button:not([kind="secondary"]):not([data-testid="stBaseButton-secondary"]):hover {{
    background-color: #ffffff !important; 
    border-color: #ffffff !important; 
    cursor: pointer !important;
}}
body.dark-theme div[data-testid="stButton"] button:not([kind="secondary"]):not([data-testid="stBaseButton-secondary"]):hover *,
body.dark-theme div[data-testid="stButton"] button:not([kind="secondary"]):not([data-testid="stBaseButton-secondary"]):hover {{
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}}

body.light-theme div[data-testid="stButton"] button:not([kind="secondary"]):not([data-testid="stBaseButton-secondary"]) {{
    background-color: #ffffff !important; 
    border: 2px solid #000000 !important; 
}}
body.light-theme div[data-testid="stButton"] button:not([kind="secondary"]):not([data-testid="stBaseButton-secondary"]) *,
body.light-theme div[data-testid="stButton"] button:not([kind="secondary"]):not([data-testid="stBaseButton-secondary"]) {{
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}}
body.light-theme div[data-testid="stButton"] button:not([kind="secondary"]):not([data-testid="stBaseButton-secondary"]):hover {{
    background-color: #000000 !important; 
    border-color: #000000 !important; 
    cursor: pointer !important;
}}
body.light-theme div[data-testid="stButton"] button:not([kind="secondary"]):not([data-testid="stBaseButton-secondary"]):hover *,
body.light-theme div[data-testid="stButton"] button:not([kind="secondary"]):not([data-testid="stBaseButton-secondary"]):hover {{
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}}
div[data-testid="stButton"] button:active {{ transform: scale(0.98) !important; }}

div[data-testid="stButton"] button[kind="secondary"],
div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"] {{ background-color: transparent !important; border: 2px solid var(--text-color) !important; border-radius: 0.625em !important; padding: 0.35rem 1rem !important; width: 100% !important; transition: all 0.3s ease !important; }}
div[data-testid="stButton"] button[kind="secondary"] p,
div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"] p {{ color: var(--text-color) !important; font-size: 14px !important; font-weight: 700 !important; transition: all 0.3s ease !important; }}
div[data-testid="stButton"] button[kind="secondary"]:hover,
div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"]:hover {{ background-color: var(--text-color) !important; }}
div[data-testid="stButton"] button[kind="secondary"]:hover p,
div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"]:hover p {{ color: var(--app-bg) !important; }}

body.light-theme .stSelectbox > div > div, 
body.light-theme .stDateInput > div > div, 
body.light-theme .stTextInput > div > div {{ 
    background: #ffffff !important; 
    border: 2px solid #000000 !important; 
}}
body.light-theme .stSelectbox div, 
body.light-theme .stSelectbox p, 
body.light-theme .stSelectbox span, 
body.light-theme .stSelectbox input, 
body.light-theme .stDateInput div, 
body.light-theme .stDateInput p, 
body.light-theme .stDateInput span, 
body.light-theme .stDateInput input, 
body.light-theme .stTextInput div, 
body.light-theme .stTextInput p, 
body.light-theme .stTextInput span, 
body.light-theme .stTextInput input {{ 
    color: #000000 !important; 
    -webkit-text-fill-color: #000000 !important; 
}}
body.light-theme .stSelectbox svg {{ 
    fill: #000000 !important; 
}}
body.light-theme .stSelectbox > div > div::after, 
body.light-theme .stDateInput > div > div::after, 
body.light-theme .stTextInput > div > div::after {{ 
    background: #000000 !important; 
}}
body.light-theme .stSelectbox > div > div:hover *, 
body.light-theme .stDateInput > div > div:hover *, 
body.light-theme .stTextInput > div > div:hover * {{ 
    color: #ffffff !important; 
    -webkit-text-fill-color: #ffffff !important; 
}}
body.light-theme .stSelectbox > div > div:hover svg {{ 
    fill: #ffffff !important; 
}}

body.light-theme [data-testid="stWidgetLabel"] p,
body.light-theme label[data-testid="stWidgetLabel"] p,
body.light-theme .stSelectbox label p,
body.light-theme .stDateInput label p,
body.light-theme .total-channels-label {{
    color: #222222 !important;
    -webkit-text-fill-color: #222222 !important;
}}
body.dark-theme [data-testid="stWidgetLabel"] p,
body.dark-theme label[data-testid="stWidgetLabel"] p,
body.dark-theme .stSelectbox label p,
body.dark-theme .stDateInput label p,
body.dark-theme .total-channels-label {{
    color: #dddddd !important;
    -webkit-text-fill-color: #dddddd !important;
}}

</style>
<div class="teks-versi">Version 2.7 &copy;Arly</div>
<div class="hero-box">
    <div class="hero-dark-header">
        <svg width="100%" height="70" viewBox="0 0 800 70" style="overflow: visible;">
            <defs>
                <linearGradient id="laser-dark-glow" x1="0%" y1="0%" x2="200%" y2="0%">
                    <stop offset="0%" stop-color="#b30006" />
                    <stop offset="25%" stop-color="#ff2e35" />
                    <stop offset="50%" stop-color="#ffffff" />
                    <stop offset="75%" stop-color="#ff2e35" />
                    <stop offset="100%" stop-color="#b30006" />
                    <animate attributeName="x1" values="-100%;100%" dur="4s" repeatCount="indefinite" />
                    <animate attributeName="x2" values="0%;200%" dur="4s" repeatCount="indefinite" />
                </linearGradient>
            </defs>
            <text x="50%" y="45" dominant-baseline="middle" text-anchor="middle" font-family="'Poppins', sans-serif" font-size="50" font-weight="800" fill="url(#laser-dark-glow)" style="filter: drop-shadow(0px 0px 14px rgba(255,46,53,0.65));">Vidio EPG Checker</text>
        </svg>
    </div>
    <div class="hero-light-header">
        <svg width="100%" height="70" viewBox="0 0 800 70" style="overflow: visible;">
            <defs>
                <linearGradient id="laser-light-glow" x1="0%" y1="0%" x2="200%" y2="0%">
                    <stop offset="0%" stop-color="#cc0914" />
                    <stop offset="25%" stop-color="#ff1e26" />
                    <stop offset="50%" stop-color="#ff999d" />
                    <stop offset="75%" stop-color="#ff1e26" />
                    <stop offset="100%" stop-color="#cc0914" />
                    <animate attributeName="x1" values="-100%;100%" dur="4s" repeatCount="indefinite" />
                    <animate attributeName="x2" values="0%;200%" dur="4s" repeatCount="indefinite" />
                </linearGradient>
            </defs>
            <text x="50%" y="45" dominant-baseline="middle" text-anchor="middle" font-family="'Poppins', sans-serif" font-size="50" font-weight="800" fill="url(#laser-light-glow)" style="filter: drop-shadow(0px 2px 4px rgba(204,9,20,0.15));">Vidio EPG Checker</text>
        </svg>
    </div>
    <span class="hero-subtitle">Live Streaming Content.</span>
</div>
"""
st.markdown(custom_css, unsafe_allow_html=True)

toggle_ui = """
<div class="theme-toggle-container">
    <div class="toggle-switch">
      <label class="switch-label">
        <input type="checkbox" class="checkbox" id="custom-theme-toggle">
        <span class="slider"></span>
      </label>
    </div>
</div>
"""
st.markdown(toggle_ui, unsafe_allow_html=True)

toggle_js = """
<script>
setTimeout(function() {
    const doc = window.parent.document;
    const toggle = doc.getElementById('custom-theme-toggle');

    if (toggle && !toggle.dataset.jsAttached) {
        toggle.dataset.jsAttached = "true";

        const savedTheme = window.parent.localStorage.getItem('epg-checker-theme');
        let isLight = false;
        
        if (savedTheme === 'light') {
            isLight = true;
        } else if (savedTheme === 'dark') {
            isLight = false;
        } else {
            isLight = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
        }

        toggle.checked = isLight;

        function applyTheme(light) {
            if (light) {
                doc.body.classList.add('light-theme');
                doc.body.classList.remove('dark-theme');
            } else {
                doc.body.classList.add('dark-theme');
                doc.body.classList.remove('light-theme');
            }
        }

        applyTheme(isLight);

        toggle.addEventListener('change', function(e) {
            const isNowLight = e.target.checked;
            applyTheme(isNowLight);
            window.parent.localStorage.setItem('epg-checker-theme', isNowLight ? 'light' : 'dark');
        });
    }
}, 100);
</script>
"""
st.components.v1.html(toggle_js, height=0)

animasi_loading = """
<style>
.loading-wrapper { display: flex; justify-content: center; align-items: center; padding: 40px; }
.container-loader { width: fit-content; gap: 10px; }
.folder { width: min-content; margin: auto; animation: float 2s infinite linear; }
.folder .top { background-color: #FF8F56; width: 60px; height: 12px; border-top-right-radius: 10px; }
.folder .bottom { background-color: #FFCE63; width: 100px; height: 70px; box-shadow: 5px 5px 0 0 #283149; border-top-right-radius: 8px; }
.container-loader .title { font-size: 1em; color: var(--text-color); text-align: center; margin-top: 25px; font-weight: bold; font-family: sans-serif; transition: color 0.4s ease; }
@keyframes float { 
  0% { transform: translatey(0px); } 
  50% { transform: translatey(-25px); } 
  100% { transform: translatey(0px); } 
}
</style>
<div class="loading-wrapper">
    <div class="container-loader">
        <div class="folder">
            <div class="top"></div>
            <div class="bottom"></div>
        </div>
        <div class="title">Fetching EPG Schedules...</div>
    </div>
</div>
"""

URL_SPORT = "https://docs.google.com/spreadsheets/d/1gjT0SPz5dN36MWslyDcRGYOfzmkfTFg4LQKXZfRDhYo/edit?gid=1710292612#gid=1710292612"
URL_NON_SPORT = "https://docs.google.com/spreadsheets/d/1T9jQGWJHEwzb85tpTLdbo8nyrmnLoLanXk7TxGWEzxM/edit?gid=217062556#gid=217062556"
# =======================================================
# MAIN WEB APP TAMPILAN
# =======================================================
spacer_kiri, col_tengah, spacer_kanan = st.columns([1, 5, 1])

with col_tengah:

    if "expander_expanded" not in st.session_state:
        st.session_state["expander_expanded"] = False

    with st.expander("⚙️ Advanced: Add Custom Channel ID", expanded=st.session_state["expander_expanded"]):
        st.markdown("<br>", unsafe_allow_html=True)
        
        st.session_state["expander_expanded"] = False
        
        if "channel_success_msg" in st.session_state:
            st.success(st.session_state["channel_success_msg"])
            del st.session_state["channel_success_msg"] 
        if "channel_error_msg" in st.session_state:
            st.warning(st.session_state["channel_error_msg"])
            del st.session_state["channel_error_msg"]
            
        c_name, c_id, c_btn = st.columns([2, 2, 1])
        with c_name:
            st.text_input("Channel Name (e.g., K-Drama HD)", key="new_ch_name")
        with c_id:
            st.text_input("Live Stream ID (e.g., 20216)", key="new_ch_id")
        with c_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            st.button("Save Data", key="btn_save_channel", on_click=save_channel_callback)
        
        total_custom = len(load_custom_channels())
        st.markdown(f"<div class='total-channels-label' style='margin-top: 15px; font-size: 13px; font-weight: bold;'>📦 Total Custom Channels Added: {total_custom}</div>", unsafe_allow_html=True)

    st.markdown("<hr style='margin-top: 25px; margin-bottom: 25px; opacity: 0.08;'>", unsafe_allow_html=True)
# =======================================================
    # FITUR SYNC CMS KE TAB GOOGLE SHEET (SAFE APPEND/REPLACE)
    # =======================================================
    with st.expander("🔄 Sync CMS Data to Google Sheets", expanded=False):
        st.markdown("##### Update Spreadsheet Tab")

        sc_col1, sc_col2 = st.columns([1, 2])
        with sc_col1:
            sync_kategori = st.selectbox("Select Sheet Category:", ["⚽ Sports", "📺 Non-Sports"], key="sync_kat")
            target_url = URL_SPORT if sync_kategori == "⚽ Sports" else URL_NON_SPORT
            
            try:
                available_tabs = fetch_valid_tabs(target_url)
            except Exception as e:
                available_tabs = []
                
            if available_tabs:
                selected_tab = st.selectbox("Select Target Sheet Tab:", available_tabs, key="sync_channel_select", on_change=sync_channel_callback)
                st.caption(f"📌 Target Tab: **{selected_tab}**")
            else:
                st.error("Failed to read tabs from Google Sheets.")
                selected_tab = None

        with sc_col2:
            if st.session_state.get("clear_cms_text", False):
                st.session_state["cms_text_data"] = ""
                st.session_state["clear_cms_text"] = False

            cms_raw_input = st.text_area(
                "Paste CMS table here:",
                height=150,
                placeholder="IMPORTANT: Highlight from HEADER TITLE (TITLE, START TIME, etc.) then Copy & Paste...",
                key="cms_text_data"
            )

            # Display success notification if available
            if st.session_state.get("sync_success_msg"):
                st.success(st.session_state["sync_success_msg"])

            if st.button("🚀 Update Sheet Tab Now", key="btn_do_sync"):
                st.session_state["sync_success_msg"] = ""
                if not cms_raw_input.strip():
                    st.warning("⚠️ Please paste the CMS table first!")
                elif not selected_tab:
                    st.error("⚠️ Please select a Target Tab first!")
                else:
                    try:
                        # 1. Parse Clipboard Text (\t) from CMS
                        df_raw = pd.read_csv(io.StringIO(cms_raw_input), sep="\t")
                        df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
                        
                        col_title = next((c for c in df_raw.columns if "TITLE" in c or "JUDUL" in c), None)
                        col_start = next((c for c in df_raw.columns if "START" in c or "MULAI" in c), None)
                        col_end = next((c for c in df_raw.columns if "END" in c or "SELESAI" in c), None)
                        col_epg = next((c for c in df_raw.columns if "EPG" in c), None)
                        
                        if not col_title or not col_start or not col_end:
                            st.error("❌ Table header not detected! Make sure the header row (TITLE, START TIME) is included.")
                            st.stop()
                        
                        # 2. Format New CMS Data
                        df_new = pd.DataFrame()
                        start_dt = pd.to_datetime(df_raw[col_start], errors='coerce')
                        end_dt = pd.to_datetime(df_raw[col_end], errors='coerce')
                        
                        df_new['Title'] = df_raw[col_title]
                        df_new['UPPER TITLE'] = df_raw[col_title].astype(str).str.upper()
                        df_new['Start Date'] = start_dt.dt.strftime('%Y-%m-%d')
                        df_new['Start Time'] = start_dt.dt.strftime('%H:%M')
                        df_new['End Date'] = end_dt.dt.strftime('%Y-%m-%d')
                        df_new['End Time'] = end_dt.dt.strftime('%H:%M')
                        df_new['EPG ID'] = df_raw[col_epg] if col_epg else ""

                        target_dates = df_new['Start Date'].dropna().unique().tolist()
                        
                        if not target_dates:
                            st.error("❌ Date format in CMS data not detected!")
                            st.stop()

                        # 3. Fetch Existing Data from Google Sheets
                        gc_client = init_gspread()
                        sh_target = gc_client.open_by_url(target_url)
                        ws_target = sh_target.worksheet(selected_tab)

                        existing_data = ws_target.get_all_values()
                        
                        # 4. Filter & Protect Existing Data
                        if len(existing_data) > 1:
                            headers = existing_data[0]
                            df_existing = pd.DataFrame(existing_data[1:], columns=headers)
                            
                            col_date_name = next((c for c in df_existing.columns if "START DATE" in str(c).upper() or "DATE" in str(c).upper() or "TANGGAL" in str(c).upper()), df_existing.columns[2])
                            
                            df_filtered = df_existing[~df_existing[col_date_name].astype(str).str.strip().isin(target_dates)]
                            
                            df_new.columns = df_existing.columns[:len(df_new.columns)]
                            df_final = pd.concat([df_filtered, df_new], ignore_index=True)
                        else:
                            df_final = df_new

                        # 5. Sort & Clean NaN
                        date_col = df_final.columns[2]
                        time_col = df_final.columns[3]
                        df_final = df_final.sort_values(by=[date_col, time_col]).reset_index(drop=True)
                        df_final = df_final.fillna("")

                        # 6. Re-upload
                        ws_target.clear()
                        data_upload = [df_final.columns.values.tolist()] + df_final.values.tolist()
                        ws_target.update('A1', data_upload)
                        st.cache_data.clear()

                        st.session_state["sync_success_msg"] = f"✅ Success! Data for date **{', '.join(target_dates)}** in tab **{selected_tab}** has been updated!"
                        st.session_state["clear_cms_text"] = True
                        st.rerun()

                    except Exception as e:
                        st.error(f"❌ Sync failed: {e}")

    col1, col2, col3 = st.columns(3)
    with col1:
        kategori = st.selectbox("1. Category:", ["⚽ Sports", "📺 Non-Sports"])
        target_url = URL_SPORT if kategori == "⚽ Sports" else URL_NON_SPORT
    with col2:
        try: 
            valid_tabs = fetch_valid_tabs(target_url)
        except Exception as e:
            st.error(f"Failed connection to Google Sheets database. Error: {e}")
            st.stop()
        if not valid_tabs:
            st.error("No valid matching 'TO CSV' sheets tab found!")
            st.stop()
        pilihan_tab = st.selectbox("2. Channels:", valid_tabs, key="active_channel")

    raw_df = fetch_sheet_data(target_url, pilihan_tab)
    if raw_df.empty:
        st.warning("The target worksheet data is empty.")
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

    with col3: 
        pilihan_tgl = st.date_input("3. Date:", value=date.today())

st.markdown("<br>", unsafe_allow_html=True)

panel_info = f"""
<style>
.glass-card-fixed {{ position: fixed; z-index: 999; background-color: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: 10px; padding: 12px 15px; backdrop-filter: blur(10px); color: var(--text-color); box-shadow: var(--glass-shadow); max-width: 250px; transition: all 0.4s ease; }}
.panel-right {{ bottom: 20px; right: 20px; }}
.panel-left {{ bottom: 40px; left: 20px; border-left: 3px solid #fcf414; }}
.glass-card-fixed h4 {{ margin-top: 0; margin-bottom: 8px; font-weight: 600; font-size: 12px; }}
.status-list {{ list-style: none; padding-left: 0; margin: 0; font-size: 11px; line-height: 1.6; }}
.status-list li {{ display: flex; align-items: center; gap: 8px; }}
.disclaimer-text {{ font-size: 11px; line-height: 1.5; font-style: italic; color: var(--hero-sub); }}
</style>
<div class="glass-card-fixed panel-right">
    <h4>📊 Server Status</h4>
    <ul class="status-list">
        <li>🟢 <strong>Status:</strong> Online</li>
        <li>📺 <strong style="color: #4da8da;">DB: {len(KNOWN_CHANNELS)} Channels</strong></li>
        <li>⚡ <strong>Engine:</strong> Ultimate Engine</li>
    </ul>
</div>
<div class="glass-card-fixed panel-left">
    <h4>💡 Notes</h4>
    <div class="disclaimer-text">Ensure the Sheets data status is set to <strong>'TO CSV'</strong> before running to guarantee accuracy.</div>
</div>
"""
wadah_panel = st.empty()
wadah_panel.markdown(panel_info, unsafe_allow_html=True)

wadah_antrean = st.empty()
if antrean_lock.locked():
    wadah_antrean.warning("⏳ **Global Queue Active:** The scraping engine is currently deployed...")

if st.button("Run Program", type="primary", use_container_width=True):
    wadah_panel.empty()
    wadah_animasi = st.empty()
    wadah_animasi.markdown(animasi_loading, unsafe_allow_html=True)
    target_date_obj = pilihan_tgl

    df_filtered = raw_df[raw_df['parsed_date_obj'] == target_date_obj].copy()
    
    if df_filtered.empty:
        wadah_animasi.empty()
        st.error(f"❌ No active schedule data found for date: {target_date_obj.strftime('%d-%m-%Y')}.")
        st.stop()
        
    df_epg = df_filtered[[col_title, col_start, col_end]].copy()
    df_epg.columns = ['title', 'start_time', 'end_time']
    df_epg['start_time'] = df_epg['start_time'].apply(fix_time)
    df_epg['end_time'] = df_epg['end_time'].apply(fix_time)

    # =======================================================
    # GAP DETECTOR ENGINE
    # =======================================================
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
                diff_minutes = (t2 - t1).total_seconds() / 60.0
                if diff_minutes == 1.0: is_gap = False
            except: pass
        if is_gap:
            gap_errors.append({
                "Start Time": next_start,
                "Program Title": df_epg_seq.loc[idx+1, 'title']
            })
            
    # =======================================================
    # END-OF-DAY COVERAGE CHECK
    # =======================================================
    coverage_errors = []
    if not df_epg_seq.empty:
        akhir_hari = df_epg_seq.iloc[-1]['end_time']
        mulai_akhir_hari = df_epg_seq.iloc[-1]['start_time']
        is_aman = akhir_hari in ['00:00', '23:59', '24:00']
        if not is_aman:
            try:
                jam_mulai = int(mulai_akhir_hari.split(":")[0])
                jam_selesai = int(akhir_hari.split(":")[0])
                if jam_selesai < jam_mulai: is_aman = True
            except: pass
        if not is_aman:
            coverage_errors.append({
                "Violation Rule": "Schedule Does Not Reach Next Day",
                "Last Recorded End Time": akhir_hari,
                "Expected End Time": "23:59 or Cross Midnight (e.g. 01:30)"
            })
            
    raw_name = re.sub(r'[^\w\s]', '', pilihan_tab.upper()) 
    for kata in ['TO CSV', 'HASIL CSV', 'HASIL', 'CSV', 'JADWAL', 'WIB']:
        raw_name = raw_name.replace(kata, ' ')
    channel_name = re.sub(r'\s+', ' ', raw_name).strip()
    
    exact_aliases = {
        'PLTV': 'PREMIER LEAGUE TV', 'RMTV': 'REAL MADRID TV',
        'CGOLF 1': 'CHAMPIONS TV GOLF 1', 'CGOLF 2': 'CHAMPIONS TV GOLF 2', 'CGOLF': 'CHAMPIONS TV GOLF',
        'CTV 1': 'CHAMPIONS TV 1', 'CTV 2': 'CHAMPIONS TV 2', 'CTV 3': 'CHAMPIONS TV 3',
        'CTV 4': 'CHAMPIONS TV 4', 'CTV 5': 'CHAMPIONS TV 5', 'CTV 6': 'CHAMPIONS TV 6', 'CTV': 'CHAMPIONS TV',
        'HIP HIP HOREE': 'HIP HIP HOREE!', 'HOREE': 'HOREE CHANNEL', 'HORE': 'HOREE CHANNEL',           
        'ABC': 'ABC AUSTRALIA', 'NHK': 'NHK JAPAN', 'TTV': 'TRANS TV', 'KOMPAS': 'KOMPAS TV'
    }
    if channel_name in exact_aliases: channel_name = exact_aliases[channel_name]
    
    if channel_name in KNOWN_CHANNELS: channel_id = KNOWN_CHANNELS[channel_name]
    else:
        wadah_animasi.empty()
        st.error(f"Channel identity '{channel_name}' is missing from the system KNOWN_CHANNELS database.")
        st.stop()
        
    url_vidio = f"https://www.vidio.com/live/{channel_id}"
        
    with antrean_lock:
        wadah_antrean.empty()
        
        with st.status("Initializing Scraping Bot...", expanded=False) as status:
            pass
        
        from selenium.webdriver.firefox.options import Options as FirefoxOptions
        from selenium.webdriver.firefox.service import Service as FirefoxService
        from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
        from webdriver_manager.firefox import GeckoDriverManager

        options = FirefoxOptions()
        options.add_argument("-headless")

        profile_path = os.path.join(os.getcwd(), "firefox_cms_profile")
        if os.path.exists(profile_path):
            options.profile = FirefoxProfile(profile_path)

        try:
            service = FirefoxService(GeckoDriverManager().install())
            driver = webdriver.Firefox(service=service, options=options)
        except Exception as e:
            wadah_animasi.empty()
            st.error(f"❌ Firefox automation runtime failed to launch: {e}")
            st.stop()
            
        try:
            web_schedules = []
            for attempt in range(2):
                if attempt == 1:
                    status.update(label="Network lag detected. Initiating Smart Auto-Retry...", state="running")
                    time.sleep(3)

                driver.get(url_vidio)
                time.sleep(3)
                current_url = driver.current_url
                
                if str(channel_id) not in current_url:
                    status.update(label="Blocking Banner Alert Detected!", state="error", expanded=True)
                    wadah_animasi.empty()
                    st.stop() 
                
                for i in range(10): 
                    driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {(i+1)/10});")
                    time.sleep(0.5) 
                driver.execute_script("window.scrollTo(0, 0);") 
                time.sleep(1)
                
                selisih_hari = (target_date_obj - date.today()).days
                if selisih_hari > 0:
                    angka_tgl = str(target_date_obj.day)
                    bulan_map = {1: 'jan', 2: 'feb', 3: 'mar', 4: 'apr', 5: 'mei', 6: 'jun', 7: 'jul', 8: 'agu', 9: 'sep', 10: 'okt', 11: 'nov', 12: 'des'}
                    keyword_bulan = bulan_map[target_date_obj.month]
                    
                    time.sleep(1) 
                    elements = driver.find_elements("xpath", "//button | //span | //a")
                    elements_sorted = sorted(elements, key=lambda x: len(x.get_attribute("textContent").strip()) if x.get_attribute("textContent") else 999)
                    
                    berhasil_klik = False
                    if selisih_hari == 1:
                        for el in elements_sorted:
                            try:
                                teks = el.get_attribute("textContent").strip().lower() if el.get_attribute("textContent") else ""
                                if teks in ['besok', 'tomorrow']:
                                    driver.execute_script("arguments[0].click();", el)
                                    berhasil_klik = True
                                    time.sleep(3) 
                                    break
                            except: pass
                    
                    if not berhasil_klik:
                        for el in elements_sorted:
                            try:
                                teks = el.get_attribute("textContent").strip().lower() if el.get_attribute("textContent") else ""
                                if not teks or len(teks) > 40: continue
                                match_angka = re.search(rf"(^|\D)0?{angka_tgl}(\D|$)", teks)
                                if match_angka and keyword_bulan in teks:
                                    driver.execute_script("arguments[0].click();", el)
                                    berhasil_klik = True
                                    time.sleep(3) 
                                    break
                            except: pass

                    for i in range(8): 
                        driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {(i+1)/8});")
                        time.sleep(0.5) 
                    driver.execute_script("window.scrollTo(0, 0);") 
                    time.sleep(3.0) 
                
                try:
                    all_elements = driver.find_elements("xpath", "//button | //span | //a")
                    for btn in all_elements[::-1]:
                        try:
                            txt = btn.get_attribute("textContent").strip().lower() if btn.get_attribute("textContent") else ""
                            if txt in ['show more', 'lihat lebih banyak', 'lihat lebih', 'more', 'tampilkan lebih banyak']:
                                driver.execute_script("arguments[0].click();", btn)
                                time.sleep(2.0) 
                                break 
                        except: pass
                except Exception: pass
                
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                web_schedules = []
                all_text = re.sub(r'\s+', ' ', soup.get_text(" ")).strip()
                
                pola_jadwal = r'(\d{1,2}[:\.]\d{2})(?:\s*(?:WIB|AM|PM|am|pm))?\s*[-–—]+\s*(\d{1,2}[:\.]\d{2})(?:\s*(?:WIB|AM|PM|am|pm))?\s+(.*?)(?=\s*(?:\d{1,2}[:\.]\d{2}(?:\s*(?:WIB|AM|PM|am|pm))?\s*[-–—]+\s*\d{1,2}[:\.]\d{2})|$)'
                semua_cocok = re.findall(pola_jadwal, all_text, flags=re.IGNORECASE)
                
                for cocok in semua_cocok:
                    start_w = fix_time(cocok[0])
                    end_w = fix_time(cocok[1])
                    title_w = cocok[2].strip()
                    title_w = re.sub(r'^[Oo•-]\s*', '', title_w)
                    title_w = re.sub(r'\s*LIVE\s*$', '', title_w, flags=re.IGNORECASE).strip()
                    
                    if not any(x['start'] == start_w and x['end'] == end_w and x['title_no_space'] == hancurkan_spasi(title_w) for x in web_schedules):
                        web_schedules.append({
                            'start': start_w, 
                            'end': end_w, 
                            'title_clean': bersihkan_teks(title_w),
                            'title_no_space': hancurkan_spasi(title_w)
                        })
                if web_schedules: break

            status.update(label="Scraping Web Complete! Fetching CMS Data...", state="running")

            # 1. Buka Domain Utama & Inject Cookie dari cookies.json
            driver.get("https://www.vidio.com")
            time.sleep(1)

            cookie_str = load_cookie_from_file()
            if cookie_str:
                for item in cookie_str.split(";"):
                    item = item.strip()
                    if "=" in item:
                        k, v = item.split("=", 1)
                        try:
                            driver.add_cookie({
                                'name': k.strip(), 
                                'value': v.strip(), 
                                'domain': '.vidio.com',
                                'path': '/'
                            })
                        except Exception:
                            pass

            # 2. Buka URL CMS Admin
            cms_url = f"https://www.vidio.com/admin/livestreamings/{channel_id}/schedules?selected_date={target_date_obj.strftime('%Y-%m-%d')}"
            driver.get(cms_url)
            time.sleep(4)

            # 3. Parsing Data Tabel CMS Admin
            soup_cms = BeautifulSoup(driver.page_source, 'html.parser')
            cms_schedules = []
            for tr in soup_cms.select('table tr'):
                cols = tr.find_all('td')
                if len(cols) >= 8:
                    title = cols[3].get_text(strip=True) if len(cols) > 3 else ""
                    start_t = cols[5].get_text(strip=True) if len(cols) > 5 else ""
                    end_t = cols[7].get_text(strip=True) if len(cols) > 7 else ""
                    
                    thumb_col = cols[8].get_text(strip=True) if len(cols) > 8 else ""
                    has_thumb = "YES" in thumb_col.upper()

                    if title and start_t and "STATUS" not in title.upper():
                        cms_schedules.append({
                            'title': title, 
                            'start_time': start_t, 
                            'end_time': end_t,
                            'has_thumbnail': has_thumb
                        })

            status.update(label="Scraping Complete!", state="complete")

        finally:
            driver.quit()

    if not web_schedules:
        wadah_animasi.empty()
        st.error("EPG Schedule data could not be parsed from Vidio Live Web.")
        st.stop()

    hasil_manual_revision = []
    hasil_error = []

    for _, row in df_epg.iterrows():
        judul_csv_bersih = bersihkan_teks(row['title'])
        judul_csv_no_space = hancurkan_spasi(row['title'])
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
            def to_min(t_str):
                if not t_str: return None
                m = re.search(r'(\d{1,2}):(\d{2})', str(t_str))
                return (int(m.group(1)) * 60 + int(m.group(2))) if m else None

            # Kalkulator Overlap Lintas Malam
            def calc_overlap(s1, e1, s2, e2):
                if s1 is None or e1 is None or s2 is None or e2 is None: return 0
                if e1 <= s1: e1 += 1440
                if e2 <= s2: e2 += 1440
                
                o1 = max(0, min(e1, e2) - max(s1, s2))
                o2 = max(0, min(e1, e2+1440) - max(s1, s2+1440))
                o3 = max(0, min(e1+1440, e2) - max(s1+1440, s2))
                return max(o1, o2, o3)

            ss_s = to_min(row.get('start_time'))
            ss_e = to_min(row.get('end_time'))
            
            # Hitung durasi asli Spreadsheet
            if ss_s is not None and ss_e is not None:
                ss_duration = ss_e + 1440 - ss_s if ss_e <= ss_s else ss_e - ss_s
            else:
                ss_duration = 120

            best_cms = None
            best_match_kind = ""
            best_score = -9999

            # EVALUASI SKOR CMS DENGAN RUMUS PENALTI SELISIH DURASI
            for cms_item in cms_schedules:
                c_s = to_min(cms_item.get('start_time'))
                c_e = to_min(cms_item.get('end_time'))
                
                if c_e is None and c_s is not None:
                    c_e = c_s + ss_duration
                    if c_e >= 1440: c_e -= 1440

                overlap_duration = calc_overlap(ss_s, ss_e, c_s, c_e)

                if overlap_duration > 0:
                    c_e_calc = c_e + 1440 if c_e <= c_s else c_e
                    cms_total_duration = c_e_calc - c_s
                    
                    duration_difference = abs(ss_duration - cms_total_duration)
                    score = overlap_duration - (duration_difference * 0.6)

                    if score > best_score:
                        best_score = score
                        
                        c_title = str(cms_item.get('title', '')).strip().lower()
                        ss_title = str(row.get('title', '')).strip().lower()
                        
                        words_ss = set(re.findall(r'\w+', ss_title))
                        words_cms = set(re.findall(r'\w+', c_title))
                        abaikan = {'vs', 'and', 'or', 'eps', 'match', 'round', 'highlight', 'show', 'full', 'impact', 'wib', 'day'}
                        
                        common_brands = {'wta', 'atp', 'nfl', 'serie', 'motogp', 'f1', 'carabao', 'premier', 'sailgp'}
                        has_brand = bool(words_ss.intersection(common_brands).intersection(words_cms))
                        has_common = len(words_ss.intersection(words_cms) - abaikan) > 0

                        best_cms = cms_item
                        if has_brand or has_common:
                            best_match_kind = "adjusted"
                        else:
                            best_match_kind = "replaced"

            # OUTPUT KATEGORI HASIL
            if best_cms:
                cms_title_text = best_cms.get('title', 'Unknown Title')
                has_thumb = best_cms.get('has_thumbnail', False)
                thumb_str = " (Thumbnail: YES)" if has_thumb else ""
                
                if best_match_kind == "adjusted":
                    rev_reason = f"Schedule Adjusted in CMS{thumb_str} (CMS: {cms_title_text})"
                else:
                    rev_reason = f"Slot Replaced in CMS{thumb_str} (Replaced by: {cms_title_text})"

                hasil_manual_revision.append({
                    "Start Time": row['start_time'], 
                    "End Time": row['end_time'], 
                    "Program Title": row['title'],
                    "Status CMS": rev_reason
                })
            else:
                hasil_error.append({
                    "Start Time": row['start_time'], 
                    "End Time": row['end_time'], 
                    "Program Title": row['title']
                })

    wadah_animasi.empty()
    st.markdown("<br>", unsafe_allow_html=True)
    
    if len(coverage_errors) > 0:
        ui_cov = f"""
        <div style="background: linear-gradient(135deg, rgba(0, 188, 212, 0.15), rgba(3, 169, 244, 0.15)); border: 1px solid rgba(0, 188, 212, 0.3); border-left: 6px solid #00BCD4; border-radius: 12px; padding: 20px 25px; display: flex; align-items: center; gap: 18px; margin-bottom: 20px;">
            <div style="font-size: 28px;">🌙</div>
            <div style="color: var(--text-color); font-size: 16px;">
                <strong>INCOMPLETE DAILY COVERAGE:</strong> Schedule does not reach the next day! <strong>{len(coverage_errors)} violation(s)</strong> detected.
            </div>
        </div>
        """
        st.markdown(ui_cov, unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(coverage_errors), use_container_width=True)
        st.markdown("<br>", unsafe_allow_html=True)
        
    if len(gap_errors) > 0:
        ui_gap = f"""
        <div style="background: linear-gradient(135deg, rgba(255, 193, 7, 0.15), rgba(255, 152, 0, 0.15)); border: 1px solid rgba(255, 193, 7, 0.3); border-left: 6px solid #FFC107; border-radius: 12px; padding: 20px 25px; display: flex; align-items: center; gap: 18px; margin-bottom: 20px;">
            <div style="font-size: 28px;">⏱️</div>
            <div style="color: var(--text-color); font-size: 16px;">
                <strong>SCHEDULE GAP DETECTED:</strong> Discovered <strong>{len(gap_errors)} missing link(s)</strong> in your Spreadsheet!
            </div>
        </div>
        """
        st.markdown(ui_gap, unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(gap_errors), use_container_width=True)
        st.markdown("<br>", unsafe_allow_html=True)

    if len(hasil_manual_revision) > 0:
        ui_manual = f"""
        <div style="margin-top: 15px; margin-bottom: 20px;">
            <div style="background: linear-gradient(135deg, rgba(255, 193, 7, 0.15), rgba(255, 152, 0, 0.15)); border: 1px solid rgba(255, 193, 7, 0.3); border-left: 6px solid #FFC107; border-radius: 12px; padding: 20px 25px; display: flex; align-items: center; gap: 18px;">
                <div style="font-size: 28px;">🟡</div>
                <div style="color: var(--text-color); font-size: 16px;">
                    Discovered <strong>{len(hasil_manual_revision)} schedule(s)</strong> with <strong>Manual CMS Revisions</strong>
                </div>
            </div>
        </div>
        """
        st.markdown(ui_manual, unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(hasil_manual_revision), use_container_width=True)
        st.markdown("<br>", unsafe_allow_html=True)    
    
    if len(hasil_error) > 0:
        ui_error = f"""
        <div style="margin-top: 15px; margin-bottom: 20px;">
            <div style="color: var(--text-color); font-size: 24px; font-weight: 800; margin-bottom: 15px;">📊 Verification Report</div>
            <div style="background: linear-gradient(135deg, rgba(229, 9, 20, 0.15), rgba(255, 82, 82, 0.15)); border: 1px solid rgba(255, 82, 82, 0.3); border-left: 6px solid #ff5252; border-radius: 12px; padding: 20px 25px; display: flex; align-items: center; gap: 18px;">
                <div style="font-size: 28px;">⚠️</div>
                <div style="color: var(--text-color); font-size: 16px;">Discovered <strong>{len(hasil_error)} schedule(s)</strong> in the Spreadsheet that DO NOT MATCH / ARE MISSING from Vidio live streaming:</div>
            </div>
        </div>
        """
        st.markdown(ui_error, unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(hasil_error), use_container_width=True)

    if len(hasil_error) == 0 and len(gap_errors) == 0 and len(coverage_errors) == 0:
        ui_sukses = f"""
        <div style="margin-top: 15px;">
            <div style="color: var(--text-color); font-size: 24px; font-weight: 800; margin-bottom: 15px;">📊 Verification Report</div>
            <div style="background: linear-gradient(135deg, rgba(0, 176, 155, 0.15), rgba(150, 201, 61, 0.15)); border: 1px solid rgba(150, 201, 61, 0.3); border-left: 6px solid #96c93d; border-radius: 12px; padding: 20px 25px; display: flex; align-items: center; gap: 18px;">
                <div style="font-size: 28px;">🎉</div>
                <div style="color: var(--text-color); font-size: 16px;"><strong>SUCCESS!</strong> 100% Schedules Synced for <strong>{channel_name}</strong> (Date: {pilihan_tgl.strftime('%d-%m-%Y')})</div>
            </div>
        </div>
        """
        st.markdown(ui_sukses, unsafe_allow_html=True)
        
        st.components.v1.html(f"""
            <script>
                const existingOverlay = window.parent.document.getElementById('success-checkmark-overlay');
                if (existingOverlay) {{ existingOverlay.remove(); }}
                const overlay = window.parent.document.createElement('div');
                overlay.id = 'success-checkmark-overlay';
                overlay.style.position = 'fixed';
                overlay.style.top = '0';
                overlay.style.left = '0';
                overlay.style.width = '100vw';
                overlay.style.height = '100vh';
                overlay.style.backgroundColor = 'rgba(15, 15, 15, 0.85)';
                overlay.style.backdropFilter = 'blur(8px)';
                overlay.style.display = 'flex';
                overlay.style.flexDirection = 'column';
                overlay.style.justifyContent = 'center';
                overlay.style.alignItems = 'center';
                overlay.style.zIndex = '999999';
                overlay.style.opacity = '0';
                overlay.style.transition = 'opacity 0.4s ease';

                overlay.innerHTML = `
                    <style>@keyframes popInCheck {{ 0% {{ transform: scale(0.5); opacity: 0; }} 70% {{ transform: scale(1.1); opacity: 1; }} 100% {{ transform: scale(1); opacity: 1; }} }} @keyframes slideUpText {{ 0% {{ transform: translateY(20px); opacity: 0; }} 100% {{ transform: translateY(0); opacity: 1; }} }}</style>
                    <div style="background: linear-gradient(135deg, #00b09b, #96c93d); border-radius: 50%; width: 120px; height: 120px; display: flex; align-items: center; justify-content: center; box-shadow: 0 10px 30px rgba(150, 201, 61, 0.4); animation: popInCheck 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;">
                        <svg width="60" height="60" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                    </div>
                    <h2 style="color: white; font-family: 'Poppins', sans-serif; font-size: 36px; font-weight: 800; margin-top: 25px; animation: slideUpText 0.5s ease forwards 0.2s; opacity: 0; letter-spacing: 1px;">100% SYNCED</h2>
                `;
                window.parent.document.body.appendChild(overlay);
                setTimeout(() => {{ overlay.style.opacity = '1'; }}, 30);
                setTimeout(() => {{
                    overlay.style.opacity = '0';
                    setTimeout(() => {{ if (window.parent.document.body.contains(overlay)) {{ window.parent.document.body.removeChild(overlay); }} }}, 400); 
                }}, 3000);
            </script>
        """, height=0)
