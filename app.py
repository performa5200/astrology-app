import streamlit as st
import json
import os
import math
import requests
import smtplib
from email.mime.text import MIMEText
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, time, timedelta
from lunar_python import Solar, Lunar
import time as py_time

st.set_page_config(page_title="命理全景解析", layout="wide")

# 嵌入 Google AdSense (不影響頁面結構)
st.markdown("""
<head>
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-2265722719270125" crossorigin="anonymous"></script>
</head>
""", unsafe_allow_html=True)

# 郵件發送函數 (請在 Secrets 設定 EMAIL_USER 與 EMAIL_PASS)
def send_feedback_email(feedback_text):
    try:
        sender = st.secrets["EMAIL_USER"]
        password = st.secrets["EMAIL_PASS"]
        msg = MIMEText(f"收到新的使用者回饋：\n\n{feedback_text}")
        msg["Subject"] = "命理系統意見回饋"
        msg["From"] = sender
        msg["To"] = "performa5200@gmail.com"
        
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, "performa5200@gmail.com", msg.as_string())
        return True
    except Exception as e:
        return False

# ... (其餘工具函數 load_keys_from_file, call_gemini_api, 曆法計算等保持不變) ...
# (為了篇幅，此處省略重複的繁瑣計算邏輯，請沿用之前的版本)

# --- UI 介面修正：使用 key 參數防止焦點亂跳 ---
st.title("🌌 命理全景解析")

with st.form("input_form"):
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c1:
        input_gender = st.selectbox("性別", ["坤造 (女)", "乾造 (男)"], key="gen")
    with c2:
        input_date = st.date_input("出生公曆日期", value=date(2000, 1, 1), key="dt")
    with c3:
        input_time = st.time_input("出生時間 (24h)", value=time(0, 0), key="tm")

    input_location = st.text_input("出生國家 / 城市", value="", key="loc")
    input_mbti = st.text_input("MBTI 人格類型", value="", key="mbti")
    input_focus_custom = st.text_input("💡 我想多了解哪部分", value="", key="focus")
    input_feedback = st.text_area("💬 意見回饋 (選填)", value="", height=70, key="feed")

    # 改為在表單內按鈕，防止頻繁重跑
    submit_btn = st.form_submit_button("🚀 開始 Gemini 專家深度詳算", type="primary")

# 邏輯處理
if submit_btn:
    if not input_location.strip() and not input_mbti.strip() and not input_focus_custom.strip():
        st.warning("⚠️ 請填寫相關參數後再進行運算")
    else:
        # 寄送回饋
        if input_feedback.strip():
            send_feedback_email(input_feedback)
        
        # 運算邏輯 (同前版本)
        st.info("處理中...")
