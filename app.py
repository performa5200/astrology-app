import streamlit as st
import json
import os
import re
import math
import requests
import smtplib
import time as py_time
from email.mime.text import MIMEText
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, time, timedelta
from lunar_python import Solar, Lunar

st.set_page_config(page_title="命理全景解析", layout="wide")

# 在網頁標頭中注入 Google AdSense 中繼標籤與正式追蹤碼
st.markdown("""
<head>
    <meta name="google-adsense-account" content="ca-pub-2265722719270125">
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2265722719270125" crossorigin="anonymous"></script>
</head>
<style>
.block-container { max-width: 68% !important; padding-left: 3rem !important; padding-right: 3rem !important; }
.bazi-col { background: #1f242c; border: 1px solid #3d444d; border-radius: 6px; padding: 8px 2px; text-align: center; margin-bottom: 6px; }
.bazi-tg { font-size: 20px; font-weight: bold; color: #f0883e; }
.bazi-dz { font-size: 20px; font-weight: bold; color: #58a6ff; }
.bazi-label { font-size: 11px; color: #8b949e; margin-bottom: 2px; }
.palace-card { background: #171b22; border: 1px solid #30363d; border-radius: 6px; padding: 8px; margin-bottom: 8px; }
.palace-title { font-size: 13px; font-weight: bold; color: #7ee787; border-bottom: 1px solid #30363d; padding-bottom: 3px; margin-bottom: 4px; }
.star-major { color: #ff7b72; font-weight: bold; font-size: 13px; }
.star-minor { color: #d2a8ff; font-size: 12px; }
.native-interpret { background-color: #1c212b; border-left: 3px solid #58a6ff; padding: 10px; margin-top: 10px; font-size: 13px; color: #c9d1d9; border-radius: 0 4px 4px 0; }
</style>
""", unsafe_allow_html=True)

def load_keys_from_file(filename="api_key.txt"):
    try:
        if "GEMINI_API_KEY" in st.secrets:
            secret_key = st.secrets["GEMINI_API_KEY"]
            if secret_key:
                keys = [k.strip() for k in secret_key.split(",") if k.strip()]
                if keys: return keys
    except Exception: pass
    base_dir = os.path.dirname(os.path.abspath(__file__))
    target_path = os.path.join(base_dir, filename)
    if not os.path.exists(target_path): return []
    valid_keys = []
    with open(target_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            clean = line.strip().replace('"', '').replace("'", "")
            if clean and not clean.startswith("#"): valid_keys.append(clean)
    return valid_keys

def send_feedback_email(feedback_text):
    try:
        sender = st.secrets["EMAIL_USER"]
        password = st.secrets["EMAIL_PASS"]
        msg = MIMEText(f"收到新使用者意見回饋：\n\n{feedback_text}")
        msg["Subject"] = "命理系統意見回饋"
        msg["From"] = sender
        msg["To"] = "performa5200@gmail.com"
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, "performa5200@gmail.com", msg.as_string())
    except Exception as e:
        print(f"郵件發送失敗: {e}")

def call_gemini_api(prompt_text, keys):
    if not keys: return "【未配置 Gemini Key】"
    unique_keys = list(set(keys))
    for k in unique_keys:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={k.strip()}"
        payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
        try:
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 200:
                return "".join([p.get("text", "") for p in resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])])
        except: continue
    return "❌ 呼叫失敗"

# 初始化 State
if "gemini_report" not in st.session_state: st.session_state.gemini_report = None
if "last_exec_time" not in st.session_state: st.session_state.last_exec_time = 0.0

st.title("🌌 命理全景解析")

# 使用 Form 防止輸入時焦點亂跳
with st.form("input_form"):
    c1, c2, c3 = st.columns([1, 1, 1])
    input_gender = c1.selectbox("性別", ["坤造 (女)", "乾造 (男)"])
    input_date = c2.date_input("出生日期", value=date(2000, 1, 1))
    input_time = c3.time_input("出生時間", value=time(0, 0))
    input_location = st.text_input("出生城市")
    input_mbti = st.text_input("MBTI")
    input_focus = st.text_input("想了解的問題")
    input_feedback = st.text_area("💬 意見回饋 (選填)")
    
    cooldown = 180
    elapsed = py_time.time() - st.session_state.last_exec_time
    is_cooling = elapsed < cooldown
    btn_text = f"⏳ 冷卻中 ({math.ceil(cooldown - elapsed)}秒)" if is_cooling else "🚀 開始 Gemini 專家深度詳算"
    
    submit_btn = st.form_submit_button(btn_text, disabled=is_cooling, type="primary")

if submit_btn:
    if not input_location.strip():
        st.warning("⚠️ 請填寫出生地點")
    else:
        # 立即觸發運作，無需等待廣告
        if input_feedback.strip(): send_feedback_email(input_feedback)
        
        with st.status("📢 正在進行深度 AI 專家交叉推理...", expanded=True) as status:
            prompt = f"分析目標: {input_focus}. 生辰: {input_date} {input_time}. 地點: {input_location}. MBTI: {input_mbti}"
            st.session_state.gemini_report = call_gemini_api(prompt, load_keys_from_file())
            st.session_state.last_exec_time = py_time.time()
            status.update(label="✅ 分析完成", state="complete")
        st.rerun()

if st.session_state.gemini_report:
    st.markdown("---")
    st.markdown(st.session_state.gemini_report)
