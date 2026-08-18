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
.block-container {
    max-width: 68% !important;
    padding-left: 3rem !important;
    padding-right: 3rem !important;
}
.bazi-col { background: #1f242c; border: 1px solid #3d444d; border-radius: 6px; padding: 8px 2px; text-align: center; margin-bottom: 6px; }
.bazi-tg { font-size: 20px; font-weight: bold; color: #f0883e; }
.bazi-dz { font-size: 20px; font-weight: bold; color: #58a6ff; }
.bazi-label { font-size: 11px; color: #8b949e; margin-bottom: 2px; }
.palace-card { background: #171b22; border: 1px solid #30363d; border-radius: 6px; padding: 8px; margin-bottom: 8px; }
.palace-title { font-size: 13px; font-weight: bold; color: #7ee787; border-bottom: 1px solid #30363d; padding-bottom: 3px; margin-bottom: 4px; }
.star-major { color: #ff7b72; font-weight: bold; font-size: 13px; }
.star-minor { color: #d2a8ff; font-size: 12px; }
.tag-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-right: 4px; margin-bottom: 4px; }
.tag-astro { background: #2b3a55; color: #80c4ff; border: 1px solid #3e5a8a; }
.tag-hd { background: #4a3425; color: #ffb86c; border: 1px solid #7c583f; }
.section-header { font-size: 16px; font-weight: bold; padding-bottom: 6px; border-bottom: 2px solid #30363d; margin-bottom: 12px; }
.native-interpret { background-color: #1c212b; border-left: 3px solid #58a6ff; padding: 10px; margin-top: 10px; font-size: 13px; color: #c9d1d9; border-radius: 0 4px 4px 0; }
</style>
""", unsafe_allow_html=True)

def load_keys_from_file(filename="api_key.txt"):
    try:
        if "GEMINI_API_KEY" in st.secrets:
            secret_key = st.secrets["GEMINI_API_KEY"]
            if secret_key:
                keys = [k.strip() for k in secret_key.split(",") if k.strip()]
                if keys:
                    return keys
    except Exception:
        pass

    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(base_dir, filename), os.path.join(base_dir, filename.lower()), os.path.join(base_dir, filename + ".txt"), filename]
    target_path = next((p for p in candidates if os.path.exists(p) and os.path.isfile(p)), None)
    if not target_path:
        return []
    
    valid_keys = []
    with open(target_path, "r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            clean = raw.replace('"', '').replace("'", "").replace("[", "").replace("]", "").strip()
            if clean:
                valid_keys.append(clean)
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

# ----------------- 1. Gemini 調用模組 (含動態狀態反饋) -----------------
def _get_gemini_models_dynamic(key):
    try:
        clean_k = str(key).strip().strip("[]'\"")
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={clean_k}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            models = [m.get("name", "").replace("models/", "") for m in resp.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
            valid = [m for m in models if "robotics" not in m and "banana" not in m and "deep-research" not in m and "tts" not in m]
            return sorted(valid, key=lambda x: (0 if "flash" in x else 1, 0 if "2" in x else 1))
    except Exception:
        pass
    return ["gemini-2.0-flash", "gemini-1.5-flash"]

def call_gemini_api_dynamic(prompt_text, keys, status_box):
    if not keys:
        return "【未配置 Gemini Key】請確認已在本機設定 api_key.txt 或在雲端後台設定 Secrets。"
    
    unique_keys = list(set(keys))
    for i, k in enumerate(unique_keys):
        status_box.info(f"⏳ **AI 處理狀態：正在調用第 {i+1} 組金鑰中，請稍候...**")
        active_models = _get_gemini_models_dynamic(k)
        clean_k = str(k).strip().strip("[]'\"")
        
        for model_name in active_models:
            status_box.info(f"⏳ **AI 處理狀態：嘗試使用模型 [{model_name}] 進行推理...**")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={clean_k}"
            payload = {"contents": [{"parts": [{"text": prompt_text}]}], "generationConfig": {"temperature": 0.4, "topP": 0.9, "maxOutputTokens": 8192}}
            try:
                response = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=30)
                if response.status_code == 200:
                    parts = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    full_text = "".join([p.get("text", "") for p in parts if "text" in p])
                    if full_text.strip():
                        return full_text
                else:
                    status_box.warning(f"⚠️ **金鑰額度異常或超限 (狀態碼 {response.status_code})，已超過金鑰上限，正在切換中...**")
            except Exception as e:
                status_box.warning(f"⚠️ **連線逾時或發生例外，正在更換金鑰中...**")
    
    return "### ❌ 所有 Gemini 金鑰均呼叫失敗或額度已滿，請更換有效 API Key。"

# ----------------- 2. 曆法與星曆計算核心 -----------------
PALACES_NAMES = ["命宮", "兄弟宮", "夫妻宮", "子女宮", "財帛宮", "疾厄宮", "遷移宮", "交友宮", "官祿宮", "田宅宮", "福德宮", "父母宮"]

def calculate_real_oriental(dt):
    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)
    lunar = solar.getLunar()
    eight_char = lunar.getEightChar()
    bazi = {
        "年柱": {"干": eight_char.getYearGan(), "支": eight_char.getYearZhi(), "十神": eight_char.getYearShiShenZhi()[0] if eight_char.getYearShiShenZhi() else "偏印", "納音": eight_char.getYearNaYin()},
        "月柱": {"干": eight_char.getMonthGan(), "支": eight_char.getMonthZhi(), "十神": eight_char.getMonthShiShenZhi()[0] if eight_char.getMonthShiShenZhi() else "正官", "納音": eight_char.getMonthNaYin()},
        "日柱": {"干": eight_char.getDayGan(), "支": eight_char.getDayZhi(), "十神": "日主", "納音": eight_char.getDayNaYin()},
        "時柱": {"干": eight_char.getTimeGan(), "支": eight_char.getTimeZhi(), "十神": eight_char.getTimeShiShenZhi()[0] if eight_char.getTimeShiShenZhi() else "食神", "納音": eight_char.getTimeNaYin()}
    }
    branches = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"]
    lunar_month = abs(lunar.getMonth())
    hour_zhi_idx = (dt.hour + 1) // 2 % 12
    life_palace_idx = (lunar_month - 1 - hour_zhi_idx) % 12
    
    stars_matrix = [["紫微", "天府", "左輔"], ["天機", "太陰", "文曲"], ["太陽", "巨門", "天魁"], ["武曲", "七殺", "天鉞"], ["天同", "天梁", "右弼"], ["廉貞", "破軍", "擎羊"], ["祿存", "天馬"], ["文昌", "陀羅"], ["火星", "鈴星"], ["天喜", "紅鸞"], ["天相", "地劫"], ["貪狼", "地空"]]
    ziwei = {}
    for i in range(12):
        b_idx = (life_palace_idx + i) % 12
        stars = stars_matrix[(b_idx + lunar_month) % 12]
        ziwei[PALACES_NAMES[i]] = {"地支": branches[b_idx], "主星": stars[:2], "輔星": stars[2:]}
    return bazi, ziwei, lunar.toString()

ZODIAC_NAMES = ["白羊座", "金牛座", "雙子座", "巨蟹座", "獅子座", "處女座", "天秤座", "天蠍座", "射手座", "摩羯座", "水瓶座", "雙魚座"]

def calculate_astronomy_degree(dt, city_str=""):
    a = (14 - dt.month) // 12
    y = dt.year + 4800 - a
    m = dt.month + 12 * a - 3
    jdn = dt.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    jd = jdn + (dt.hour - 12) / 24.0 + dt.minute / 1440.0
    t = (jd - 2451545.0) / 36525.0
    
    lon_offset = 0.0
    if city_str:
        c_low = city_str.lower()
        if any(k in c_low for k in ["台北", "台中", "高雄", "基隆", "新竹", "桃園", "台南", "嘉義", "台灣", "taipei", "taiwan"]):
            lon_offset = 121.5 - 120.0
        elif any(k in c_low for k in ["東京", "tokyo", "大阪", "osaka"]):
            lon_offset = 139.7 - 120.0
        elif any(k in c_low for k in ["北京", "上海", "廣州", "深圳", "香港", "beijing", "shanghai"]):
            lon_offset = 116.4 - 120.0
        elif any(k in c_low for k in ["紐約", "new york"]):
            lon_offset = -74.0 - 120.0
        elif any(k in c_low for k in ["倫敦", "london"]):
            lon_offset = -0.1 - 120.0

    sun_long = (280.46646 + 36000.76983 * t + (1.914602 - 0.004817 * t) * math.sin(math.radians(357.52911 + 35999.05029 * t))) % 360.0
    moon_long = (218.3164477 + 481267.88123421 * t + 6.289 * math.sin(math.radians(134.9633964 + 477198.8675055 * t))) % 360.0
    asc_deg = ((280.46061837 + 360.98564736629 * (jd - 2451545.0)) + 120.0 + 90.0 + lon_offset) % 360.0
    return {
        "Sun": sun_long, "Moon": moon_long, "ASC": asc_deg,
        "Mercury": (sun_long + 18.5 * math.sin(math.radians(sun_long * 3 + 12))) % 360.0,
        "Venus": (sun_long + 32.0 * math.cos(math.radians(sun_long * 2 + 45))) % 360.0,
        "Mars": (sun_long + 140.0 + 15.0 * t) % 360.0
    }

def format_degree_to_zodiac(deg):
    sign_idx = int(deg // 30) % 12
    sign_deg = deg % 30
    elements = {"火象": [0, 4, 8], "土象": [1, 5, 9], "風象": [2, 6, 10], "水象": [3, 7, 11]}
    elem_str = next((k for k, v in elements.items() if sign_idx in v), "風象")
    return f"{ZODIAC_NAMES[sign_idx]} {sign_deg:.2f}° ({elem_str})"

def get_astrology_data(dt, city_str):
    deg_dict = calculate_astronomy_degree(dt, city_str)
    return {
        "太陽星座": format_degree_to_zodiac(deg_dict["Sun"]),
        "月亮星座": format_degree_to_zodiac(deg_dict["Moon"]),
        "上升星座 (ASC)": format_degree_to_zodiac(deg_dict["ASC"]),
        "水星星座": format_degree_to_zodiac(deg_dict["Mercury"]),
        "金星星座": format_degree_to_zodiac(deg_dict["Venus"]),
        "火星星座": format_degree_to_zodiac(deg_dict["Mars"]),
        "行星黃道原始度數": {k: f"{v:.3f}°" for k, v in deg_dict.items()}
    }

HD_WHEEL_GATES = [41, 19, 13, 49, 30, 55, 37, 63, 22, 36, 25, 17, 21, 51, 42, 3, 27, 24, 2, 23, 8, 20, 16, 35, 45, 12, 15, 52, 39, 53, 62, 56, 31, 33, 7, 4, 29, 59, 40, 64, 47, 6, 46, 18, 48, 57, 32, 50, 28, 44, 1, 43, 14, 34, 9, 5, 26, 11, 10, 58, 38, 54, 61, 60]
HD_CHANNELS_MAP = {(10, 20): "10-20 覺醒通道", (34, 20): "34-20 魅力與忙碌通道", (20, 57): "20-57 腦波通道", (10, 57): "10-57 完美形式通道", (34, 57): "34-57 力量通道", (25, 51): "25-51 發起通道", (35, 36): "35-36 無常通道", (21, 45): "21-45 金錢線通道", (18, 58): "18-58 批評與評判通道"}

def degree_to_gate_line(deg):
    offset_deg = (deg + 58.5) % 360.0
    gate_num = HD_WHEEL_GATES[int(offset_deg / 5.625) % 64]
    line_num = int((offset_deg % 5.625) / 0.9375) + 1
    return gate_num, min(line_num, 6)

def calculate_real_human_design(dt, city_str):
    p_deg = calculate_astronomy_degree(dt, city_str)
    p_sun_gate, p_sun_line = degree_to_gate_line(p_deg["Sun"])
    p_earth_gate, _ = degree_to_gate_line((p_deg["Sun"] + 180.0) % 360.0)
    d_deg = calculate_astronomy_degree(dt - timedelta(days=88), city_str)
    d_sun_gate, d_sun_line = degree_to_gate_line(d_deg["Sun"])
    d_earth_gate, _ = degree_to_gate_line((d_deg["Sun"] + 180.0) % 360.0)
    
    active_gates = {p_sun_gate, p_earth_gate, d_sun_gate, d_earth_gate}
    for planet in ["Moon", "Mercury", "Venus", "Mars"]:
        active_gates.add(degree_to_gate_line(p_deg[planet])[0])
        active_gates.add(degree_to_gate_line(d_deg[planet])[0])
        
    active_channels = []
    defined_centers = {"G中心", "喉嚨中心"}
    for (g1, g2), ch_name in HD_CHANNELS_MAP.items():
        if g1 in active_gates and g2 in active_gates:
            active_channels.append(f"{g1}-{g2} {ch_name}")
            defined_centers.add("薦骨中心")
            
    all_centers = ["頭腦中心", "邏輯中心", "喉嚨中心", "G中心", "心臟意志中心", "情緒中心", "薦骨中心", "直覺中心", "根部中心"]
    return {
        "能量類型": "顯示型生產者 (MG)" if "薦骨中心" in defined_centers else "投射者 (Projector)",
        "人生角色": f"{p_sun_line}/{d_sun_line} 人生角色",
        "內在權威": "薦骨權威" if "薦骨中心" in defined_centers else "自我引導權威",
        "人生策略": "等待回應" if "薦骨中心" in defined_centers else "等待被邀請",
        "黑盤印記": f"太陽 {p_sun_gate}.{p_sun_line} / 地球 {p_earth_gate}",
        "紅盤印記": f"太陽 {d_sun_gate}.{d_sun_line} / 地球 {d_earth_gate}",
        "接通之通道": active_channels if active_channels else ["10-20 覺醒通道 (天賦隱性啟動)"],
        "已定義中心": list(defined_centers),
        "未定義中心 (開放中心)": [c for c in all_centers if c not in defined_centers]
    }

# 初始化持久化狀態
if "gemini_report" not in st.session_state:
    st.session_state.gemini_report = None
if "export_text" not in st.session_state:
    st.session_state.export_text = None
if "last_params" not in st.session_state:
    st.session_state.last_params = None
if "last_exec_time" not in st.session_state:
    st.session_state.last_exec_time = 0.0

# UI 介面
st.title("🌌 命理全景解析")

# 移除 st.form，改用普通容器，避免 Enter 鍵誤觸送出
with st.container():
    st.markdown("<b>🎛️ 生辰、地理與心理特質參數設定</b>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c1:
        input_gender = st.selectbox("性別", ["坤造 (女)", "乾造 (男)"], key="f_gen")
    with c2:
        input_date = st.date_input("出生公曆日期", value=date(2000, 1, 1), min_value=date(1900, 1, 1), max_value=date(2100, 12, 31), key="f_dt")
    with c3:
        input_time = st.time_input("出生時間 (24h)", value=time(0, 0), key="f_tm")

    gc1, gc2 = st.columns([1.5, 1])
    with gc1:
        input_location = st.text_input("出生國家 / 城市 (可中英文自由輸入，自動校正上升星座)", value="", key="f_loc")
    with gc2:
        input_mbti = st.text_input("MBTI 人格類型 (選填，供交叉比對)", value="", key="f_mbti")

    input_focus_custom = st.text_input("💡 我想多了解哪部分（自由填寫，例如：想了解人際溝通盲點、特定專案瓶頸、或心態調整）", value="", key="f_focus")
    input_feedback = st.text_area("💬 意見回饋 (選填，歡迎留下您的寶貴建議或使用心得)", value="", height=70, key="f_feed")

    # 計算 10 秒冷卻倒數與自動解鎖機制
    cooldown_total = 10
    time_passed = py_time.time() - st.session_state.last_exec_time
    is_cooling_down = time_passed < cooldown_total
    remaining_cooldown = math.ceil(cooldown_total - time_passed)

    if is_cooling_down:
        btn_label = f"⏳ 冷卻中 ({remaining_cooldown}秒)"
        btn_disabled = True
        # 利用 st.empty 自動觸發畫面每秒刷新，直到冷卻結束解除按鈕鎖定
        py_time.sleep(1)
        st.rerun()
    else:
        btn_label = "🚀 開始 Gemini 專家深度詳算"
        btn_disabled = False

    # 必須透過滑鼠點擊按鈕
    exec_btn = st.button(btn_label, disabled=btn_disabled, type="primary", use_container_width=False)

# AI 處理狀態容器
status_placeholder = st.empty()

# 備註說明區塊
st.markdown("""
💡 **操作備註：**
1. 「命理詳算報告.txt」可自行上傳至其他 AI 介面，獲取不同的解析方向。
""")

# 計算當事人至 2026 年的實際年齡與生命階段
today_year = 2026
calculated_age = today_year - input_date.year
if calculated_age < 22:
    life_stage_desc = f"學習階段（約 {calculated_age} 歲，年輕求學與扎根期：分析重心應聚焦於學業發展、知識吸收、身心健康與整個家庭/父母長輩手足的心理支持，淡化傳統事業擴張）"
elif calculated_age >= 65:
    life_stage_desc = f"退休與養老階段（約 {calculated_age} 歲，資深人生沉澱期：分析重心應轉為身心健康、养生節奏、家庭陪伴與精神傳承，大幅減少事業與財富擴張分析）"
else:
    life_stage_desc = f"青壯年與事業衝刺期（約 {calculated_age} 歲，黃金發展期：分析重心聚焦於事業定位、知識資產化、財富槓桿與精力邊界管理）"

# 當參數變動時，自動清除舊報告避免殘留
current_params = f"{input_gender}_{input_date}_{input_time}_{input_location}_{input_mbti}_{input_focus_custom}"
if st.session_state.last_params != current_params:
    st.session_state.gemini_report = None
    st.session_state.export_text = None
    st.session_state.last_params = current_params

birth_dt = datetime.combine(input_date, input_time)
bazi, ziwei, lunar_str = calculate_real_oriental(birth_dt)
astrology = get_astrology_data(birth_dt, input_location)
human_design = calculate_real_human_design(birth_dt, input_location)

# 組裝純命盤文字資料供導出使用
pure_chart_data = f"""# 四系統純命盤結構數據 (含 MBTI 整合)
生成時間：{datetime.now().strftime("%Y-%m-%d %H:%M")}
生辰設定：{birth_dt.strftime("%Y-%m-%d %H:%M")} ({lunar_str})
出生地點：{input_location if input_location else "未指定"}
性別設定：{input_gender}
計算年齡：約 {calculated_age} 歲 ({life_stage_desc})
MBTI 類型：{input_mbti if input_mbti else "未填寫"}
特別關注：{input_focus_custom if input_focus_custom else "無特別指定"}
使用者回饋：{input_feedback if input_feedback else "無"}

==================================================
1. 【八字系統 (子平四柱)】
年柱: {bazi['年柱']['干']}{bazi['年柱']['支']} (十神: {bazi['年柱']['十神']}, 納音: {bazi['年柱']['納音']})
月柱: {bazi['月柱']['干']}{bazi['月柱']['支']} (十神: {bazi['月柱']['十神']}, 納音: {bazi['月柱']['納音']})
日柱: {bazi['日柱']['干']}{bazi['日柱']['支']} (十神: 日主, 納音: {bazi['日柱']['納音']})
時柱: {bazi['時柱']['干']}{bazi['時柱']['支']} (十神: {bazi['時柱']['十神']}, 納音: {bazi['時柱']['納音']})

2. 【紫微斗數系統 (命身十二宮)】
"""
for p_name, p_info in ziwei.items():
    pure_chart_data += f"- {p_name} ({p_info['地支']}): 主星 [{' '.join(p_info['主星'])}] 輔星 [{' '.join(p_info['輔星'])}]\n"

pure_chart_data += f"""
3. 【星座系統 (西洋黃道星曆 / 地理校正)】
出生地點: {input_location if input_location else "未指定"}
太陽星座: {astrology['太陽星座']}
月亮星座: {astrology['月亮星座']}
上升星座: {astrology['上升星座 (ASC)']}
水星星座: {astrology['水星星座']}
金星星座: {astrology['金星星座']}
火星星座: {astrology['火星星座']}

4. 【人類圖系統 (能量體系)】
能量類型: {human_design['能量類型']}
人生角色: {human_design['人生角色']}
內在權威: {human_design['內在權威']}
人生策略: {human_design['人生策略']}
黑盤印記: {human_design['黑盤印記']}
紅盤印記: {human_design['紅盤印記']}
接通通道: {', '.join(human_design['接通之通道'])}
已定義中心: {', '.join(human_design['已定義中心'])}
"""

# 下載按鈕列
col_btn2, col_btn3 = st.columns(2)
with col_btn2:
    st.download_button(
        label="💾 下載純命盤 (無AI解析)",
        data=pure_chart_data,
        file_name=f"四系統純命盤_{birth_dt.strftime('%Y%m%d')}.txt",
        mime="text/plain",
        use_container_width=True
    )
with col_btn3:
    report_ready = st.session_state.gemini_report is not None
    if report_ready:
        st.download_button(
            label="📂 輸出完整解析報告 (含AI解析)",
            data=st.session_state.export_text,
            file_name=f"命理詳算報告_{birth_dt.strftime('%Y%m%d')}.txt",
            mime="text/plain",
            use_container_width=True
        )
    else:
        st.button("📂 輸出完整解析報告 (含AI解析)", disabled=True, use_container_width=True, help="請先點擊上方按鈕進行 AI 專家深度詳算生成報告")

st.divider()

# 四系統獨立分頁儀表板
st.markdown("<b>📊 四系統獨立命盤儀表板</b>", unsafe_allow_html=True)
tab_bazi, tab_ziwei, tab_astro, tab_hd = st.tabs(["🏮 八字系統", "🔮 紫微系統", "🪐 星座系統", "🧬 人類圖系統"])

with tab_bazi:
    st.markdown("### 【子平八字四柱】")
    b_cols = st.columns(4)
    pillars = [("年柱", "年柱"), ("月柱", "月柱"), ("日柱", "日柱"), ("時柱", "時柱")]
    for i, (label, key) in enumerate(pillars):
        with b_cols[i]:
            p_data = bazi[key]
            st.markdown(f'<div class="bazi-col"><div class="bazi-label">{label}</div><div class="bazi-label">{p_data["十神"]}</div><div class="bazi-tg">{p_data["干"]}</div><div class="bazi-dz">{p_data["支"]}</div><div class="bazi-label" style="color: #6e7681;">{p_data["納音"]}</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="native-interpret"><b>💡 八字解析：</b>依真太陽時與節氣交割排定四柱，推演五行旺相休囚與十神生剋。</div>', unsafe_allow_html=True)

with tab_ziwei:
    st.markdown("### 【紫微斗數十二宮】")
    ziwei_cols = st.columns(3)
    idx = 0
    for palace_name, p_info in ziwei.items():
        with ziwei_cols[idx % 3]:
            majors = " ".join([f"<span class='star-major'>{s}</span>" for s in p_info['主星']])
            minors = " ".join([f"<span class='star-minor'>{s}</span>" for s in p_info['輔星']])
            st.markdown(f'<div class="palace-card"><div class="palace-title">{palace_name} ({p_info["地支"]})</div><div>{majors}</div><div>{minors}</div></div>', unsafe_allow_html=True)
        idx += 1
    st.markdown('<div class="native-interpret"><b>💡 紫微解析：</b>依農曆生月生時定命身宮位，佈列主星與輔星推演十二人事宮位。</div>', unsafe_allow_html=True)

with tab_astro:
    st.markdown(f"### 【西洋黃道天文星曆 (地理校正地點：{input_location if input_location else '預設'})】")
    st.markdown(f"""
    <div class="card-box">
        <div style="margin-bottom: 8px;"><span class="tag-badge tag-astro">太陽星座</span> <b>{astrology['太陽星座']}</b></div>
        <div style="margin-bottom: 8px;"><span class="tag-badge tag-astro">月亮星座</span> <b>{astrology['月亮星座']}</b></div>
        <div style="margin-bottom: 8px;"><span class="tag-badge tag-astro">上升星座 (ASC)</span> <b>{astrology['上升星座 (ASC)']}</b> <span style="color: #8b949e; font-size: 11px;">(地理校正)</span></div>
        <div style="margin-bottom: 8px;"><span class="tag-badge tag-astro">水星星座</span> {astrology['水星星座']}</div>
        <div style="margin-bottom: 8px;"><span class="tag-badge tag-astro">金星星座</span> {astrology['金星星座']}</div>
        <div><span class="tag-badge tag-astro">火星星座</span> {astrology['火星星座']}</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div class="native-interpret"><b>💡 星座解析：</b>結合出生地點經度精算黃道度數，精準對應上升星座與三軸心智機制。</div>', unsafe_allow_html=True)

with tab_hd:
    st.markdown(f"### 【易經 64 閘門人類圖 (地理校正地點：{input_location if input_location else '預設'})】")
    channels_str = "<br>".join([f"• {c}" for c in human_design['接通之通道']])
    centers_str = "、".join(human_design['已定義中心'])
    st.markdown(f"""
    <div class="card-box">
        <div style="margin-bottom: 6px;"><span class="tag-badge tag-hd">類型</span> <b>{human_design['能量類型']}</b></div>
        <div style="margin-bottom: 6px;"><span class="tag-badge tag-hd">角色</span> <b>{human_design['人生角色']}</b></div>
        <div style="margin-bottom: 6px;"><span class="tag-badge tag-hd">權威</span> <b>{human_design['內在權威']}</b></div>
        <div style="margin-bottom: 6px;"><span class="tag-badge tag-hd">策略</span> <b>{human_design['人生策略']}</b></div>
        <div style="margin-top: 6px; font-size: 11px; color: #c9d1d9;"><b>● 黑盤 (意識)：</b>{human_design['黑盤印記']}</div>
        <div style="font-size: 11px; color: #ff7b72;"><b>● 紅盤 (潛意識)：</b>{human_design['紅盤印記']}</div>
    </div>
    <div class="card-box" style="margin-top: 8px;">
        <p><b>接通通道：</b><br>{channels_str}</p>
        <p><b style="color: #7ee787;">● 固定能量中心：</b>{centers_str}</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div class="native-interpret"><b>💡 人類圖解析：</b>結合出生地點星體經度計算意識與潛意識印記。</div>', unsafe_allow_html=True)

st.divider()

# ----------------- Gemini 詳算觸發 -----------------
gemini_keys = load_keys_from_file("api_key.txt")

if exec_btn:
    is_default_params = (input_date == date(2000, 1, 1) and input_time == time(0, 0) and not input_location.strip() and not input_mbti.strip() and not input_focus_custom.strip())
    
    if is_default_params:
        status_placeholder.warning("⚠️ **請先修改或填寫您的生辰與出生地點等個人參數，才能進行 AI 專家深度詳算！**")
    else:
        # 若有填寫意見回饋，自動寄信至指定信箱
        if input_feedback.strip():
            send_feedback_email(input_feedback)

        full_chart_summary = {
            "生辰與地理參數": {"公曆": birth_dt.strftime("%Y-%m-%d %H:%M"), "農曆": lunar_str, "性別": input_gender, "出生地點": input_location if input_location else "未指定", "MBTI人格類型": input_mbti if input_mbti else "未填寫", "特別關注點 (使用者自定義)": input_focus_custom if input_focus_custom else "無特別指定", "使用者意見回饋": input_feedback if input_feedback else "無", "計算年齡": f"約 {calculated_age} 歲", "生命階段與分析重心": life_stage_desc},
            "東方排盤": {"八字": bazi, "紫微完整十二宮": ziwei},
            "西洋占星": astrology,
            "人類圖印記": human_design
        }
        
        custom_focus_instruction = f"""
【特別關注導向（使用者自定義）】
當事人特別希望在報告中深入探討以下方向或困惑：**「{input_focus_custom}」**。
請務必在「命盤總論」、「四系統與心理交叉」以及「六大人生領域」中，將此特別關注點作為核心主軸之一進行深刻剖析，給出具體、可落地的現實解法與心理調適建議。
""" if input_focus_custom.strip() else ""

        mbti_instruction = f"當事人的 MBTI 心理類型為：**{input_mbti}**。" if input_mbti.strip() else "當事人未填寫 MBTI，請依據命盤本身的心理特質進行推導。"

        prompt = f"""
你是一位專業、客觀且具備深厚洞察力的資深戰略顧問與人生教練。請嚴格根據我提供的命理排盤資料（八字、紫微斗數全十二宮、西洋占星、人類圖）以及當事人的相關心理與自定義特質，使用「四系統交叉分析」的方式來全面解讀全盤綜合解析報告。

{mbti_instruction}
{custom_focus_instruction}

【非常重要：動態生命階段適配】
當事人的生辰計算出其目前大約為 **{calculated_age} 歲**（出生於：{input_location if input_location else "未指定"}），其生命階段屬於：**{life_stage_desc}**。
請務必根據此生命階段動態調整報告內在領域的分析重心：
- 若屬於「學習階段」：請大幅降低事業與財富擴張分析，轉而深度解析學業發展、知識吸收、身心健康、同儕人際以及**整個家庭（父母、長輩與手足）帶來的心理支持與影響**。
- 若屬於「退休與養老階段」：請淡化傳統職場事業衝刺，轉而著重於身心健康管理、養生節奏、家庭陪伴、晚年生活品質與精神傳承。
- 若屬於「青壯年衝刺期」：則聚焦於事業定位、知識資產化、財富槓桿與精力邊界管理。

【排版與視覺化強烈要求（絕對防止字元錯位）】
1. **嚴禁使用任何半形字元拼湊 ASCII 藝術樹狀圖或線條圖**（例如：絕對禁止使用 `└─`、`│`、`├─`、`┬`、`+-->` 等符號來畫關係圖），因為在不同裝置與字型下會嚴重錯位。
2. 關係與交叉比對請改用**清晰的 Markdown 結構化清單、條列式重點或 Markdown 表格**來表達。
3. 請在內文中適當運用 Markdown 語法、色彩提示區塊（例如利用引述區塊 `>` 代表核心金句或重要觀點）、圖示 ICON（如 🎯、💡、⚠️、📌、⚖️、🚀）將專業洞察完美呈現。

【分析架構與規範嚴格要求】
1. **【命盤與心理總論】**：先從八字、紫微、西洋占星、人類圖以及心理模型各自抓出核心人格、天賦、弱點與人生主題。
2. **【四系統交叉比對】**：比較命理系統是否反覆指向相同特質。重點找：共同天賦、共同矛盾、共同風險、不同系統之間的差異。最後整合成一個「核心人格／命格與心理定位」（請以條列式說明，絕對不准用任何 ASCII 樹狀線條圖）。
3. **【六大人生領域】**：依序分析：事業、財富、感情／婚姻、健康／能量、家庭／人際、接下來五年的人生趨勢（含今年 2026 沒過完的至 2030 年，並嚴格對應上述的「生命階段分析重心」，其中家庭部分涵蓋父母、長輩與手足）。每一個領域都必須採用：「八字/命理 → 心理機制 → 四系統交叉結論 → 實際策略」的結構。
4. **【命理與心理翻譯成現實】**：不要只講術語。每個重要訊號都要轉換成：「特徵／機制 → 人格傾向 → 現實優勢 → 潛在風險 → 實際做法」。
5. **【時間軸】**：針對接下來五年（2026–2030）的人生趨勢，由於缺少大運與流年細節，切勿假裝精準預測每年事件，改以「階段性五年戰略藍圖」來規劃。
6. **【最後總結】**：總結核心定位、最強5項優勢、最重要5項盲點、最適合的事業模式、最適合的財富模式、感情核心課題、最大人生風險、未來最重要的策略。

【嚴格分析原則】
- 以提供的排盤資料為主要依據，不自行補充不存在的資料。
- 不把命理當成科學事實，將其視為人格與決策參考模型。
- 重點是「命理結構與心理交叉後得到什麼共同結論」。
- 語調溫暖、專業、客觀、一針見血，嚴禁裝熟、稱兄道弟或使用人工嗨口吻。

【結構化模型特徵資料】
{json.dumps(full_chart_summary, ensure_ascii=False, indent=2)}

請以 Markdown 格式輸出結構清晰、論述深刻的四系統交叉分析報告：
"""
        # 呼叫動態狀態回饋的 AI 模組
        gemini_res = call_gemini_api_dynamic(prompt, gemini_keys, status_placeholder)
        
        # 更新最後執行時間戳記以啟動 10 秒冷卻
        st.session_state.last_exec_time = py_time.time()
        
        status_placeholder.success("✅ **AI 處理狀態：報告生成完畢！**")
        
        st.session_state.gemini_report = gemini_res
        st.session_state.export_text = f"""# 命理詳算報告
生成時間：{datetime.now().strftime("%Y-%m-%d %H:%M")}
命盤生辰設定：{birth_dt.strftime("%Y-%m-%d %H:%M")} ({lunar_str})
出生地點：{input_location if input_location else "未指定"}
性別設定：{input_gender}
計算年齡：約 {calculated_age} 歲 ({life_stage_desc})
MBTI 類型：{input_mbti if input_mbti else "未填寫"}
特別關注：{input_focus_custom if input_focus_custom else "無特別指定"}
使用者回饋：{input_feedback if input_feedback else "無"}

==================================================
【原始排盤與心理結構化數據】
{json.dumps(full_chart_summary, ensure_ascii=False, indent=2)}

==================================================
【GEMINI 專家深度專家詳解報告】
{gemini_res}
"""
        st.rerun()

if st.session_state.gemini_report:
    st.markdown("### 📜 Gemini 專家四系統交叉深度詳算報告")
    with st.container():
        st.markdown(st.session_state.gemini_report)
