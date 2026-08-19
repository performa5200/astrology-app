import streamlit as st
import json
import os
import re
import math
import requests
import time as py_time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, time, timedelta
from lunar_python import Solar, Lunar

st.set_page_config(page_title="命理全景解析", layout="wide")

# Streamlit Secrets 需要設定：
# GEMINI_API_KEY = "Gemini_API_Key_1,Gemini_API_Key_2,..."
# OPENAI_API_KEY = "你的 OpenAI API Key"
#
# 注意：真正的 API Key 不要寫進 GitHub 的 app.py。

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
    return ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

def call_gemini_api_dynamic(prompt_text, keys, status_box=None):
    if not keys:
        return "【未配置 Gemini Key】請確認已在本機設定 api_key.txt 或在雲端後台設定 Secrets。"
    
    unique_keys = list(set(keys))
    for i, k in enumerate(unique_keys):
        if status_box is not None:
            status_box.info(f"⏳ **AI 處理狀態：正在調用第 {i+1} 組金鑰中，請稍候...**")
        active_models = _get_gemini_models_dynamic(k)
        clean_k = str(key).strip().strip("[]'\"") if (key := k) else ""
        
        for model_name in active_models:
            if status_box is not None:
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
                    if status_box is not None:
                        status_box.warning(f"⚠️ **金鑰額度異常或超限 (狀態碼 {response.status_code})，正在切換金鑰...**")
            except Exception:
                if status_box is not None:
                    status_box.warning("⚠️ **連線逾時或發生例外，正在更換金鑰中...**")
    
    return "### ❌ 所有 Gemini 金鑰均呼叫失敗或額度已滿，請更換有效 API Key。"



def load_openai_key():
    """從 Streamlit Secrets 讀取 OpenAI API Key；本機也可使用環境變數。"""
    try:
        key = st.secrets.get("OPENAI_API_KEY", "")
        if key:
            return str(key).strip()
    except Exception:
        pass
    return os.environ.get("OPENAI_API_KEY", "").strip()


def call_openai_api(prompt_text):
    """使用 OpenAI Responses API 進行獨立分析。"""
    api_key = load_openai_key()
    if not api_key:
        return "### ❌ 未配置 OpenAI API Key\n請在 Streamlit Secrets 設定 `OPENAI_API_KEY`。"

    model_name = "gpt-5.6-luna"
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model_name,
        "input": prompt_text,
        "max_output_tokens": 8192,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=90)

        if response.status_code != 200:
            try:
                err = response.json()
                err_msg = err.get("error", {}).get("message", response.text)
            except Exception:
                err_msg = response.text
            return f"### ❌ OpenAI 呼叫失敗\n狀態碼：`{response.status_code}`\n\n{err_msg}"

        data = response.json()

        if isinstance(data.get("output_text"), str) and data["output_text"].strip():
            return data["output_text"].strip()

        texts = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    texts.append(content["text"])

        full_text = "\n".join(texts).strip()
        if full_text:
            return full_text

        return "### ❌ OpenAI 未返回可讀取的分析內容"

    except requests.exceptions.Timeout:
        return "### ❌ OpenAI 連線逾時\n請稍後重新執行。"
    except Exception as e:
        return f"### ❌ OpenAI 呼叫發生例外\n{e}"

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
if "openai_report" not in st.session_state:
    st.session_state.openai_report = None
if "export_text" not in st.session_state:
    st.session_state.export_text = None
if "last_params" not in st.session_state:
    st.session_state.last_params = None
if "last_exec_time" not in st.session_state:
    st.session_state.last_exec_time = 0.0

# 出生時間拆成「時」與「分」兩個下拉選單，方便單獨調整
hour_options = list(range(24))
minute_options = list(range(60))

# UI 介面
st.title("🌌 命理全景解析")

# 一般容器，不使用 st.form，避免 Enter 鍵誤觸送出
with st.container():
    st.markdown("<b>🎛️ 生辰、地理與心理特質參數設定</b>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c1:
        input_gender = st.selectbox("性別", ["坤造 (女)", "乾造 (男)"], key="f_gen")
    with c2:
        input_date = st.date_input("出生公曆日期", value=date(2000, 1, 1), min_value=date(1900, 1, 1), max_value=date(2100, 12, 31), key="f_dt")
    with c3:
        time_c1, time_c2 = st.columns(2)
        with time_c1:
            selected_hour = st.selectbox(
                "出生時",
                hour_options,
                index=0,
                format_func=lambda x: f"{x:02d} 時",
                key="f_hour_select",
            )
        with time_c2:
            selected_minute = st.selectbox(
                "出生分",
                minute_options,
                index=0,
                format_func=lambda x: f"{x:02d} 分",
                key="f_minute_select",
            )
        input_time = time(selected_hour, selected_minute)

    gc1, gc2 = st.columns([1.5, 1])
    with gc1:
        input_location = st.text_input(
            "出生國家 / 城市 (可中英文自由輸入，自動校正上升星座)",
            value="",
            key="f_loc",
        )
    with gc2:
        input_mbti = st.text_input(
            "MBTI 人格類型 (選填，供交叉比對)",
            value="",
            key="f_mbti",
        )

    # 計算 10 秒冷卻倒數與自動解鎖機制
    cooldown_total = 10
    time_passed = py_time.time() - st.session_state.last_exec_time
    is_cooling_down = time_passed < cooldown_total
    remaining_cooldown = math.ceil(cooldown_total - time_passed)

    if is_cooling_down:
        btn_label = f"⏳ 冷卻中 ({remaining_cooldown}秒)"
        btn_disabled = True
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
1. 本版本會同時交由 Gemini 與 OpenAI 各自獨立分析，兩份報告不互相影響。
2. 「命理詳算報告.txt」可自行上傳至其他 AI 介面，獲取不同的解析方向。
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
current_params = f"{input_gender}_{input_date}_{input_time}_{input_location}_{input_mbti}"
if st.session_state.last_params != current_params:
    st.session_state.gemini_report = None
    st.session_state.openai_report = None
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
    report_ready = (
        st.session_state.gemini_report is not None
        or st.session_state.openai_report is not None
    )
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
    is_default_params = (
        input_date == date(2000, 1, 1)
        and selected_hour == 0
        and selected_minute == 0
        and not input_location.strip()
        and not input_mbti.strip()
    )
    
    if is_default_params:
        status_placeholder.warning("⚠️ **請先修改或填寫您的生辰與出生地點等個人參數，才能進行 AI 專家深度詳算！**")
    else:
        full_chart_summary = {
            "生辰與地理參數": {"公曆": birth_dt.strftime("%Y-%m-%d %H:%M"), "農曆": lunar_str, "性別": input_gender, "出生地點": input_location if input_location else "未指定", "MBTI人格類型": input_mbti if input_mbti else "未填寫", "計算年齡": f"約 {calculated_age} 歲", "生命階段與分析重心": life_stage_desc},
            "東方排盤": {"八字": bazi, "紫微完整十二宮": ziwei},
            "西洋占星": astrology,
            "人類圖印記": human_design
        }
        
        mbti_instruction = (
            f"當事人的 MBTI 心理類型為：**{input_mbti}**。"
            if input_mbti.strip()
            else "當事人未填寫 MBTI，請只依據提供的四系統命盤資料進行心理特質推導，並清楚標示這屬於模型推論。"
        )

        prompt = f"""
你是一位專業、客觀且具備深厚洞察力的資深戰略顧問與人生教練。
這是一份「四系統命理 × 心理模型」的深度分析任務。

【重要：獨立分析】
你現在是獨立工作的 AI 分析師。
不要假設另一個 AI 會得出什麼結論，也不要刻意迎合常見命理解讀。
請從你自己的推理角度找出資料中的「主要訊號、矛盾訊號、弱訊號與不確定性」。
如果不同系統互相矛盾，請明確指出，而不是硬湊成一致答案。
命理不是科學事實，請將其定位為人格理解與決策參考模型。

{mbti_instruction}

【動態生命階段適配】
當事人的生辰計算出其目前大約為 **{calculated_age} 歲**，
其生命階段屬於：**{life_stage_desc}**。
請依此調整分析重心：
- 學習階段：降低事業與財富擴張比重，增加學業、知識吸收、同儕人際與家庭支持。
- 退休與養老階段：降低職場衝刺，增加健康、家庭陪伴、生活品質與精神傳承。
- 青壯年衝刺期：聚焦事業定位、知識資產化、財富槓桿與精力邊界。

【分析深度要求】
不要只把命盤資料逐項翻譯成性格形容詞。
請進行真正的「交叉推理」，尤其尋找：
1. 多個系統反覆出現的共同人格訊號。
2. 不同系統互相矛盾、但可能形成複合人格的地方。
3. 天賦與弱點其實來自同一個核心特質的情況。
4. 命理描述與 MBTI 若一致，說明為何一致；若不一致，分析差異。
5. 哪些結論資料支持較強，哪些只能視為低信度推論。
6. 把抽象命理訊號翻譯成現實中的行為模式、決策模式、人際模式與風險。

【排版要求】
1. 嚴禁 ASCII 藝術樹狀圖或線條圖。
2. 使用 Markdown 標題、條列、表格與引用區塊。
3. 可以使用 🎯、💡、⚠️、📌、⚖️、🚀 等圖示。
4. 不要過度使用空泛的正面形容詞。
5. 對重要結論請給出「為什麼」與「現實上怎麼做」。

【報告架構】
一、【命盤與心理總論】
分別抓出八字、紫微、西洋占星、人類圖與 MBTI（若有）的核心訊號。

二、【四系統交叉比對】
請用表格整理：
- 共同天賦
- 共同盲點
- 共同風險
- 系統之間的矛盾
- 最值得重視的核心人格結論

三、【六大人生領域】
依序分析：
1. 事業
2. 財富
3. 感情／婚姻
4. 健康／能量
5. 家庭／人際
6. 2026–2030 五年人生策略

每一個領域都使用：
「命理訊號 → 心理機制 → 四系統交叉結論 → 現實策略」

四、【命理翻譯成現實】
對最重要的訊號逐項說明：
「特徵／機制 → 人格傾向 → 現實優勢 → 潛在風險 → 實際做法」

五、【2026–2030 五年戰略藍圖】
因目前資料沒有完整大運與流年細節，
不要假裝精準預測某一年一定發生某件事。
請以階段性策略、可能的主題與應對原則呈現。

六、【最終決策摘要】
最後明確列出：
- 最強 5 項優勢
- 最重要 5 項盲點
- 最適合的事業模式
- 最適合的財富模式
- 感情核心課題
- 最大人生風險
- 未來最重要的 5 個策略
- 一句最值得當事人記住的核心結論

【嚴格資料原則】
- 以提供的排盤資料為主要依據，不自行補充不存在的資料。
- 不把命理當成科學事實。
- 不為了讓四個系統「看起來一致」而強行解釋。
- 如果資料不足，直接說「資料不足」。
- 語調溫暖、專業、客觀、一針見血。
- 嚴禁裝熟、稱兄道弟或人工嗨口吻。

【結構化模型特徵資料】
{json.dumps(full_chart_summary, ensure_ascii=False, indent=2)}

請以 Markdown 格式輸出完整、深度、可實際使用的分析報告。
"""

        status_placeholder.info("⏳ **雙 AI 正在同時進行獨立分析，請稍候……**")

        # 同時呼叫 Gemini + OpenAI，縮短整體等待時間
        with ThreadPoolExecutor(max_workers=2) as executor:
            gemini_future = executor.submit(
                call_gemini_api_dynamic, prompt, gemini_keys, None
            )
            openai_future = executor.submit(call_openai_api, prompt)

            gemini_res = gemini_future.result()
            openai_res = openai_future.result()

        st.session_state.last_exec_time = py_time.time()

        gemini_ok = bool(gemini_res and not gemini_res.startswith("### ❌"))
        openai_ok = bool(openai_res and not openai_res.startswith("### ❌"))

        if gemini_ok and openai_ok:
            status_placeholder.success(
                "✅ **雙 AI 分析完成！Gemini 與 OpenAI 均已返回結果。**"
            )
        elif gemini_ok or openai_ok:
            status_placeholder.warning(
                "⚠️ **部分完成：其中一個 AI 已完成，另一個 AI 呼叫失敗。**"
            )
        else:
            status_placeholder.error(
                "❌ **雙 AI 均未能完成分析，請檢查 Secrets 與 API 額度。**"
            )

        st.session_state.gemini_report = gemini_res
        st.session_state.openai_report = openai_res

        st.session_state.export_text = f"""# 命理雙 AI 詳算報告
生成時間：{datetime.now().strftime("%Y-%m-%d %H:%M")}
命盤生辰設定：{birth_dt.strftime("%Y-%m-%d %H:%M")} ({lunar_str})
出生地點：{input_location if input_location else "未指定"}
性別設定：{input_gender}
計算年齡：約 {calculated_age} 歲 ({life_stage_desc})
MBTI 類型：{input_mbti if input_mbti else "未填寫"}

==================================================
【原始排盤與心理結構化數據】
{json.dumps(full_chart_summary, ensure_ascii=False, indent=2)}

==================================================
【GEMINI 獨立深度分析】
{gemini_res}

==================================================
【OPENAI 獨立深度分析】
{openai_res}
"""
        st.rerun()

if st.session_state.gemini_report or st.session_state.openai_report:
    st.markdown("### 📜 雙 AI 專家四系統交叉深度詳算報告")

    report_tab_gemini, report_tab_openai = st.tabs(
        ["🟢 Gemini 分析", "🟣 OpenAI 分析"]
    )

    with report_tab_gemini:
        if st.session_state.gemini_report:
            st.markdown(st.session_state.gemini_report)
        else:
            st.error("Gemini 本次沒有取得有效結果。")

    with report_tab_openai:
        if st.session_state.openai_report:
            st.markdown(st.session_state.openai_report)
        else:
            st.error("OpenAI 本次沒有取得有效結果。")

    st.divider()
    st.markdown("### 🔎 雙 AI 使用方式")
    st.info(
        "Gemini 與 OpenAI 會使用相同的命盤資料，但各自獨立推理。"
        "不要把兩份結果視為誰一定正確；比較兩者的共識、分歧與不同推理角度，"
        "通常比只看單一 AI 更有價值。"
    )
