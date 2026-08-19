
import streamlit as st
import json
import os
import re
import math
import requests
import time as py_time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, time, timedelta
from lunar_python import Solar

st.set_page_config(page_title="命理全景解析｜雙 AI", layout="wide")

st.markdown("""
<style>
.block-container { max-width: 78% !important; padding-left: 2.5rem !important; padding-right: 2.5rem !important; }
.bazi-col { background:#1f242c; border:1px solid #3d444d; border-radius:8px; padding:10px 5px; text-align:center; margin-bottom:8px; }
.bazi-tg { font-size:22px; font-weight:bold; color:#f0883e; }
.bazi-dz { font-size:22px; font-weight:bold; color:#58a6ff; }
.bazi-label { font-size:11px; color:#8b949e; margin-bottom:3px; }
.sub-card { background:#171b22; border:1px solid #30363d; border-radius:8px; padding:12px; margin:8px 0; }
.palace-card { background:#171b22; border:1px solid #30363d; border-radius:6px; padding:8px; margin-bottom:8px; }
.palace-title { font-size:13px; font-weight:bold; color:#7ee787; border-bottom:1px solid #30363d; padding-bottom:3px; margin-bottom:4px; }
.star-major { color:#ff7b72; font-weight:bold; font-size:13px; }
.star-minor { color:#d2a8ff; font-size:12px; }
.tag-badge { display:inline-block; padding:2px 8px; border-radius:4px; font-size:12px; font-weight:bold; margin-right:4px; margin-bottom:4px; }
.tag-astro { background:#2b3a55; color:#80c4ff; border:1px solid #3e5a8a; }
.tag-hd { background:#4a3425; color:#ffb86c; border:1px solid #7c583f; }
.warning-box { background:#2a2116; border-left:4px solid #f0883e; padding:10px 12px; border-radius:4px; margin:8px 0; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 1. Secrets / API
# ============================================================

def load_gemini_keys(filename="api_key.txt"):
    """優先使用 Streamlit Secrets；本機才退回 api_key.txt。"""
    try:
        secret_key = st.secrets.get("GEMINI_API_KEY", "")
        if secret_key:
            keys = [k.strip() for k in str(secret_key).split(",") if k.strip()]
            if keys:
                return list(dict.fromkeys(keys))
    except Exception:
        pass

    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, filename),
        os.path.join(base_dir, filename.lower()),
        os.path.join(base_dir, filename + ".txt"),
        filename,
    ]
    target_path = next((p for p in candidates if os.path.isfile(p)), None)
    if not target_path:
        return []

    valid_keys = []
    with open(target_path, "r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            clean = raw.replace('"', "").replace("'", "").replace("[", "").replace("]", "").strip()
            if clean:
                valid_keys.append(clean)
    return list(dict.fromkeys(valid_keys))


def get_openai_key():
    try:
        return str(st.secrets.get("OPENAI_API_KEY", "")).strip()
    except Exception:
        return ""


def get_openai_model():
    try:
        return str(st.secrets.get("OPENAI_MODEL", "gpt-5.6-luna")).strip() or "gpt-5.6-luna"
    except Exception:
        return "gpt-5.6-luna"


# ============================================================
# 2. Gemini
# ============================================================

def _get_gemini_models_dynamic(key):
    try:
        clean_k = str(key).strip().strip("[]'\"")
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={clean_k}"
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            models = [
                m.get("name", "").replace("models/", "")
                for m in resp.json().get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            ]
            valid = [
                m for m in models
                if all(x not in m.lower() for x in ["robotics", "banana", "deep-research", "tts"])
            ]
            return sorted(
                valid,
                key=lambda x: (
                    0 if "flash" in x.lower() else 1,
                    0 if "2.5" in x.lower() else 1,
                    x
                )
            )
    except Exception:
        pass
    return ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]


def call_gemini_api(prompt_text, keys):
    if not keys:
        return "【Gemini 未配置】請確認 Streamlit Secrets 的 GEMINI_API_KEY。"

    unique_keys = list(dict.fromkeys(keys))
    last_error = ""

    for key in unique_keys:
        active_models = _get_gemini_models_dynamic(key)
        clean_k = str(key).strip().strip("[]'\"")

        for model_name in active_models:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model_name}:generateContent?key={clean_k}"
            )
            payload = {
                "contents": [{"parts": [{"text": prompt_text}]}],
                "generationConfig": {
                    "temperature": 0.45,
                    "topP": 0.9,
                    "maxOutputTokens": 12000,
                },
            }

            try:
                response = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=90,
                )

                if response.status_code == 200:
                    parts = (
                        response.json()
                        .get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [])
                    )
                    text = "".join(p.get("text", "") for p in parts if "text" in p)
                    if text.strip():
                        return text
                else:
                    last_error = f"HTTP {response.status_code}: {response.text[:300]}"

            except Exception as exc:
                last_error = str(exc)

    return f"### ❌ Gemini 呼叫失敗\n最後錯誤：`{last_error or '未知錯誤'}`"


# ============================================================
# 3. OpenAI Responses API
# ============================================================

def _extract_openai_text(data):
    if isinstance(data, dict):
        if isinstance(data.get("output_text"), str) and data["output_text"].strip():
            return data["output_text"]

        chunks = []
        for item in data.get("output", []) or []:
            if item.get("type") == "message":
                for content in item.get("content", []) or []:
                    if content.get("type") in ("output_text", "text"):
                        text = content.get("text", "")
                        if isinstance(text, str):
                            chunks.append(text)
        return "\n".join(chunks).strip()

    return ""


def call_openai_api(prompt_text):
    api_key = get_openai_key()
    model_name = get_openai_model()

    if not api_key:
        return "### ❌ OpenAI 未配置\n請確認 Streamlit Secrets 已設定 `OPENAI_API_KEY`。"

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model_name,
        "input": prompt_text,
        "max_output_tokens": 12000,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)

        if response.status_code != 200:
            return (
                f"### ❌ OpenAI 呼叫失敗\n"
                f"HTTP {response.status_code}\n\n"
                f"```text\n{response.text[:1200]}\n```"
            )

        data = response.json()
        text = _extract_openai_text(data)

        if text:
            return text

        return "### ❌ OpenAI 回傳成功，但沒有取得文字內容。"

    except Exception as exc:
        return f"### ❌ OpenAI 連線失敗\n`{exc}`"


# ============================================================
# 4. 八字資料引擎
# ============================================================

STEM_ELEMENTS = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

STEM_POLARITY = {
    "甲": "陽", "乙": "陰",
    "丙": "陽", "丁": "陰",
    "戊": "陽", "己": "陰",
    "庚": "陽", "辛": "陰",
    "壬": "陽", "癸": "陰",
}

BRANCH_MAIN_ELEMENT = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木",
    "辰": "土", "巳": "火", "午": "火", "未": "土",
    "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

# 傳統常用藏干表：本氣、中氣、餘氣
HIDDEN_STEMS = {
    "子": [("癸", "本氣")],
    "丑": [("己", "本氣"), ("癸", "中氣"), ("辛", "餘氣")],
    "寅": [("甲", "本氣"), ("丙", "中氣"), ("戊", "餘氣")],
    "卯": [("乙", "本氣")],
    "辰": [("戊", "本氣"), ("乙", "中氣"), ("癸", "餘氣")],
    "巳": [("丙", "本氣"), ("戊", "中氣"), ("庚", "餘氣")],
    "午": [("丁", "本氣"), ("己", "中氣")],
    "未": [("己", "本氣"), ("丁", "中氣"), ("乙", "餘氣")],
    "申": [("庚", "本氣"), ("壬", "中氣"), ("戊", "餘氣")],
    "酉": [("辛", "本氣")],
    "戌": [("戊", "本氣"), ("辛", "中氣"), ("丁", "餘氣")],
    "亥": [("壬", "本氣"), ("甲", "中氣")],
}

TEN_GOD_NAMES = {
    ("生我", "同陰陽"): "偏印",
    ("生我", "異陰陽"): "正印",
    ("同我", "同陰陽"): "比肩",
    ("同我", "異陰陽"): "劫財",
    ("我生", "同陰陽"): "食神",
    ("我生", "異陰陽"): "傷官",
    ("我克", "同陰陽"): "偏財",
    ("我克", "異陰陽"): "正財",
    ("克我", "同陰陽"): "七殺",
    ("克我", "異陰陽"): "正官",
}

ELEMENT_RELATION = {
    ("木", "火"): "我生", ("火", "土"): "我生", ("土", "金"): "我生",
    ("金", "水"): "我生", ("水", "木"): "我生",
    ("火", "木"): "生我", ("土", "火"): "生我", ("金", "土"): "生我",
    ("水", "金"): "生我", ("木", "水"): "生我",
    ("木", "木"): "同我", ("火", "火"): "同我", ("土", "土"): "同我",
    ("金", "金"): "同我", ("水", "水"): "同我",
    ("木", "土"): "我克", ("火", "金"): "我克", ("土", "水"): "我克",
    ("金", "木"): "我克", ("水", "火"): "我克",
    ("土", "木"): "克我", ("金", "火"): "克我", ("水", "土"): "克我",
    ("木", "金"): "克我", ("火", "水"): "克我",
}


def ten_god(day_stem, target_stem):
    """以日主天干為基準，計算標準十神。"""
    if day_stem not in STEM_ELEMENTS or target_stem not in STEM_ELEMENTS:
        return "未知"

    relation = ELEMENT_RELATION[(STEM_ELEMENTS[day_stem], STEM_ELEMENTS[target_stem])]
    polarity = (
        "同陰陽"
        if STEM_POLARITY[day_stem] == STEM_POLARITY[target_stem]
        else "異陰陽"
    )
    return TEN_GOD_NAMES[(relation, polarity)]


def bazi_relations(branches):
    """整理四支中可直接辨識的合、沖、害、破、三合、三會、刑。"""
    result = {
        "六合": [],
        "六沖": [],
        "六害": [],
        "六破": [],
        "三合": [],
        "三會": [],
        "刑": [],
    }

    pairs = {
        "六合": [("子", "丑"), ("寅", "亥"), ("卯", "戌"), ("辰", "酉"), ("巳", "申"), ("午", "未")],
        "六沖": [("子", "午"), ("丑", "未"), ("寅", "申"), ("卯", "酉"), ("辰", "戌"), ("巳", "亥")],
        "六害": [("子", "未"), ("丑", "午"), ("寅", "巳"), ("卯", "辰"), ("申", "亥"), ("酉", "戌")],
        "六破": [("子", "酉"), ("丑", "辰"), ("寅", "亥"), ("卯", "午"), ("申", "巳"), ("戌", "未")],
    }

    for name, pair_list in pairs.items():
        for a, b in pair_list:
            if a in branches and b in branches:
                result[name].append(f"{a}{b}")

    combinations = {
        "申子辰": {"申", "子", "辰"},
        "亥卯未": {"亥", "卯", "未"},
        "寅午戌": {"寅", "午", "戌"},
        "巳酉丑": {"巳", "酉", "丑"},
    }
    meetings = {
        "寅卯辰": {"寅", "卯", "辰"},
        "巳午未": {"巳", "午", "未"},
        "申酉戌": {"申", "酉", "戌"},
        "亥子丑": {"亥", "子", "丑"},
    }

    branch_set = set(branches)

    for name, needed in combinations.items():
        if needed.issubset(branch_set):
            result["三合"].append(name)

    for name, needed in meetings.items():
        if needed.issubset(branch_set):
            result["三會"].append(name)

    if branches.count("辰") >= 2:
        result["刑"].append("辰辰自刑")
    if branches.count("午") >= 2:
        result["刑"].append("午午自刑")
    if branches.count("酉") >= 2:
        result["刑"].append("酉酉自刑")
    if branches.count("亥") >= 2:
        result["刑"].append("亥亥自刑")

    for a, b in [("寅", "巳"), ("巳", "申"), ("寅", "申")]:
        if a in branch_set and b in branch_set:
            result["刑"].append(f"{a}{b}刑")

    if {"丑", "戌", "未"}.issubset(branch_set):
        result["刑"].append("丑戌未三刑")

    if {"子", "卯"}.issubset(branch_set):
        result["刑"].append("子卯刑")

    return result


def build_bazi_engine(eight_char):
    raw_pillars = [
        ("年柱", eight_char.getYearGan(), eight_char.getYearZhi(), eight_char.getYearNaYin()),
        ("月柱", eight_char.getMonthGan(), eight_char.getMonthZhi(), eight_char.getMonthNaYin()),
        ("日柱", eight_char.getDayGan(), eight_char.getDayZhi(), eight_char.getDayNaYin()),
        ("時柱", eight_char.getTimeGan(), eight_char.getTimeZhi(), eight_char.getTimeNaYin()),
    ]

    day_master = eight_char.getDayGan()
    bazi = {}
    all_hidden = []

    for label, gan, zhi, nayin in raw_pillars:
        hidden = []

        for hidden_stem, position in HIDDEN_STEMS.get(zhi, []):
            hidden.append({
                "天干": hidden_stem,
                "位置": position,
                "五行": STEM_ELEMENTS[hidden_stem],
                "十神": ten_god(day_master, hidden_stem),
            })
            all_hidden.append(hidden_stem)

        bazi[label] = {
            "干": gan,
            "支": zhi,
            "天干五行": STEM_ELEMENTS.get(gan, ""),
            "天干陰陽": STEM_POLARITY.get(gan, ""),
            "天干十神": "日主" if label == "日柱" else ten_god(day_master, gan),
            "納音": nayin,
            "地支本氣五行": BRANCH_MAIN_ELEMENT.get(zhi, ""),
            "藏干": hidden,
        }

    ten_god_counts = {}
    for label, gan, _, _ in raw_pillars:
        tg = "日主" if label == "日柱" else ten_god(day_master, gan)
        ten_god_counts[tg] = ten_god_counts.get(tg, 0) + 1

    hidden_tg_counts = {}
    for hs in all_hidden:
        tg = ten_god(day_master, hs)
        hidden_tg_counts[tg] = hidden_tg_counts.get(tg, 0) + 1

    stem_elements = [STEM_ELEMENTS[g] for _, g, _, _ in raw_pillars]
    branch_elements = [BRANCH_MAIN_ELEMENT[z] for _, _, z, _ in raw_pillars]
    element_counts = {}

    for elem in stem_elements + branch_elements:
        element_counts[elem] = element_counts.get(elem, 0) + 1

    branches = [z for _, _, z, _ in raw_pillars]

    return {
        "日主": day_master,
        "四柱": bazi,
        "天干十神統計": ten_god_counts,
        "藏干十神統計": hidden_tg_counts,
        "五行概況_天干加地支本氣": element_counts,
        "地支關係": bazi_relations(branches),
        "說明": [
            "天干十神以日主天干為基準，獨立計算四柱天干。",
            "地支十神從地支藏干逐一計算，不把地支本身直接當成十神。",
            "五行概況只是結構統計，不等同完整的旺衰定量。",
        ],
    }


def calculate_real_oriental(dt):
    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)
    lunar = solar.getLunar()
    eight_char = lunar.getEightChar()
    bazi = build_bazi_engine(eight_char)

    branches = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"]
    lunar_month = abs(lunar.getMonth())
    hour_zhi_idx = (dt.hour + 1) // 2 % 12
    life_palace_idx = (lunar_month - 1 - hour_zhi_idx) % 12

    stars_matrix = [
        ["紫微", "天府", "左輔"], ["天機", "太陰", "文曲"],
        ["太陽", "巨門", "天魁"], ["武曲", "七殺", "天鉞"],
        ["天同", "天梁", "右弼"], ["廉貞", "破軍", "擎羊"],
        ["祿存", "天馬"], ["文昌", "陀羅"], ["火星", "鈴星"],
        ["天喜", "紅鸞"], ["天相", "地劫"], ["貪狼", "地空"],
    ]
    palaces = ["命宮", "兄弟宮", "夫妻宮", "子女宮", "財帛宮", "疾厄宮",
               "遷移宮", "交友宮", "官祿宮", "田宅宮", "福德宮", "父母宮"]

    ziwei = {}

    for i in range(12):
        b_idx = (life_palace_idx + i) % 12
        stars = stars_matrix[(b_idx + lunar_month) % 12]
        ziwei[palaces[i]] = {
            "地支": branches[b_idx],
            "主星": stars[:2],
            "輔星": stars[2:],
        }

    return bazi, ziwei, lunar.toString()


# ============================================================
# 5. 西洋星曆 / 人類圖
# ============================================================

ZODIAC_NAMES = ["白羊座", "金牛座", "雙子座", "巨蟹座", "獅子座", "處女座",
                "天秤座", "天蠍座", "射手座", "摩羯座", "水瓶座", "雙魚座"]


def calculate_astronomy_degree(dt, city_str=""):
    a = (14 - dt.month) // 12
    y = dt.year + 4800 - a
    m = dt.month + 12 * a - 3
    jdn = (
        dt.day
        + (153 * m + 2) // 5
        + 365 * y
        + y // 4
        - y // 100
        + y // 400
        - 32045
    )
    jd = jdn + (dt.hour - 12) / 24.0 + dt.minute / 1440.0
    t = (jd - 2451545.0) / 36525.0

    lon_offset = 0.0

    if city_str:
        c_low = city_str.lower()

        if any(k in c_low for k in ["台北", "台中", "高雄", "基隆", "新竹", "桃園",
                                    "台南", "嘉義", "台灣", "taipei", "taiwan"]):
            lon_offset = 121.5 - 120.0
        elif any(k in c_low for k in ["東京", "tokyo", "大阪", "osaka"]):
            lon_offset = 139.7 - 120.0
        elif any(k in c_low for k in ["北京", "上海", "廣州", "深圳", "香港",
                                      "beijing", "shanghai"]):
            lon_offset = 116.4 - 120.0
        elif any(k in c_low for k in ["紐約", "new york"]):
            lon_offset = -74.0 - 120.0
        elif any(k in c_low for k in ["倫敦", "london"]):
            lon_offset = -0.1 - 120.0

    sun_long = (
        280.46646
        + 36000.76983 * t
        + (1.914602 - 0.004817 * t)
        * math.sin(math.radians(357.52911 + 35999.05029 * t))
    ) % 360.0

    moon_long = (
        218.3164477
        + 481267.88123421 * t
        + 6.289 * math.sin(math.radians(134.9633964 + 477198.8675055 * t))
    ) % 360.0

    asc_deg = (
        (280.46061837 + 360.98564736629 * (jd - 2451545.0))
        + 120.0
        + 90.0
        + lon_offset
    ) % 360.0

    return {
        "Sun": sun_long,
        "Moon": moon_long,
        "ASC": asc_deg,
        "Mercury": (sun_long + 18.5 * math.sin(math.radians(sun_long * 3 + 12))) % 360.0,
        "Venus": (sun_long + 32.0 * math.cos(math.radians(sun_long * 2 + 45))) % 360.0,
        "Mars": (sun_long + 140.0 + 15.0 * t) % 360.0,
    }


def format_degree_to_zodiac(deg):
    sign_idx = int(deg // 30) % 12
    sign_deg = deg % 30
    elements = {
        "火象": [0, 4, 8],
        "土象": [1, 5, 9],
        "風象": [2, 6, 10],
        "水象": [3, 7, 11],
    }
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
        "行星黃道原始度數": {k: f"{v:.3f}°" for k, v in deg_dict.items()},
    }


HD_WHEEL_GATES = [
    41, 19, 13, 49, 30, 55, 37, 63, 22, 36, 25, 17, 21, 51, 42, 3,
    27, 24, 2, 23, 8, 20, 16, 35, 45, 12, 15, 52, 39, 53, 62, 56,
    31, 33, 7, 4, 29, 59, 40, 64, 47, 6, 46, 18, 48, 57, 32, 50,
    28, 44, 1, 43, 14, 34, 9, 5, 26, 11, 10, 58, 38, 54, 61, 60
]

HD_CHANNELS_MAP = {
    (10, 20): "10-20 覺醒通道",
    (34, 20): "34-20 魅力與忙碌通道",
    (20, 57): "20-57 腦波通道",
    (10, 57): "10-57 完美形式通道",
    (34, 57): "34-57 力量通道",
    (25, 51): "25-51 發起通道",
    (35, 36): "35-36 無常通道",
    (21, 45): "21-45 金錢線通道",
    (18, 58): "18-58 批評與評判通道",
}


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

    all_centers = [
        "頭腦中心", "邏輯中心", "喉嚨中心", "G中心", "心臟意志中心",
        "情緒中心", "薦骨中心", "直覺中心", "根部中心"
    ]

    return {
        "能量類型": "顯示型生產者 (MG)" if "薦骨中心" in defined_centers else "投射者 (Projector)",
        "人生角色": f"{p_sun_line}/{d_sun_line} 人生角色",
        "內在權威": "薦骨權威" if "薦骨中心" in defined_centers else "自我引導權威",
        "人生策略": "等待回應" if "薦骨中心" in defined_centers else "等待被邀請",
        "黑盤印記": f"太陽 {p_sun_gate}.{p_sun_line} / 地球 {p_earth_gate}",
        "紅盤印記": f"太陽 {d_sun_gate}.{d_sun_line} / 地球 {d_earth_gate}",
        "接通之通道": active_channels if active_channels else ["10-20 覺醒通道 (天賦隱性啟動)"],
        "已定義中心": list(defined_centers),
        "未定義中心 (開放中心)": [c for c in all_centers if c not in defined_centers],
    }


# ============================================================
# 6. AI Prompt
# ============================================================

BASE_ANALYSIS_RULES = """
你正在分析一份「命理資料引擎已先行計算」的四系統資料。
請把命理系統視為人格理解、人生敘事與決策反思模型，而不是科學驗證後的命定事實。

【八字資料可信度規則】
1. 四柱天干的「天干十神」已由程式依日主重新計算，請以此為準。
2. 地支十神必須從「藏干」逐一理解，不可把地支本身直接當成十神。
3. 「五行概況_天干加地支本氣」只是結構統計，不等同完整旺衰定量。
4. 如果資料沒有提供大運、流年精盤或其他細節，不得假裝能精準預測某年發生某件具體事件。
5. 若不同系統訊號矛盾，保留矛盾並解釋其可能代表的心理張力，不要硬湊成一致。

【分析要求】
- 先分析各系統自己的訊號，再做交叉。
- 找出共同訊號、真正矛盾、弱訊號、需要驗證的假設。
- 不要因為四系統都提到某個詞，就自動判定為真。
- 每個重要結論都盡量回答：特徵 → 心理機制 → 現實優勢 → 潛在風險 → 可執行策略。
- 不要編造使用者沒有提供的人生事件。
- 感情、健康、財務等部分以風險與決策建議呈現，不做宿命式斷言。

【排版】
- 使用 Markdown 標題、條列、表格。
- 禁止 ASCII 樹狀圖與線條圖。
- 可以使用 🎯、💡、⚠️、📌、⚖️、🚀。
"""


def build_prompt(full_chart_summary, calculated_age, life_stage_desc, role):
    if role == "Gemini":
        role_rules = """
【Gemini 分析角色】
你是「命理結構研究分析師」。
優先任務：
1. 精讀八字結構、十神、藏干、五行與地支關係。
2. 再與紫微、西洋占星、人類圖、MBTI交叉。
3. 特別注意不同系統是否真的指向同一種人格機制。
4. 對矛盾訊號保持敏感，不要只寫好聽的結論。
"""
    else:
        role_rules = """
【OpenAI 分析角色】
你是「心理與人生策略批判分析師」。
優先任務：
1. 把命理訊號翻譯成可觀察的人格與決策模式。
2. 主動挑戰過度簡化的命理解讀。
3. 找出最可能造成現實困境的機制，以及哪些結論其實證據不足。
4. 最後提出可操作的人生策略，而不是只給性格形容詞。
"""

    return f"""
你是一名專業、客觀、具備高階推理能力的分析顧問。

{BASE_ANALYSIS_RULES}

{role_rules}

【當事人目前生命階段】
目前約 {calculated_age} 歲。
生命階段：{life_stage_desc}

【報告架構】
一、命盤與心理總論
- 八字核心
- 紫微核心
- 西洋占星核心
- 人類圖核心
- MBTI（若有）
- 各系統各自的優勢、盲點與核心議題

二、四／五系統交叉比對
- 共同訊號
- 真正的矛盾
- 可能只是表面相似的訊號
- 最值得進一步驗證的三個人格假設
- 核心人格定位

三、八字專項深度解析
- 日主
- 天干十神
- 地支藏干與藏干十神
- 五行結構
- 地支合沖刑害破
- 這些結構可能對應的心理機制
注意：不要把「五行數量」直接等同於旺衰強弱。

四、六大人生領域
1. 事業
2. 財富
3. 感情／婚姻
4. 健康／能量
5. 家庭／人際
6. 2026–2030 五年策略藍圖

每一領域使用：
「命理／結構訊號 → 心理機制 → 交叉結論 → 現實策略」

五、最後總結
- 最強5項優勢
- 最重要5項盲點
- 最適合的工作模式
- 最適合的財富模式
- 關係核心課題
- 最大風險
- 未來最重要的策略

【原始結構化資料】
{json.dumps(full_chart_summary, ensure_ascii=False, indent=2)}

請直接輸出完整 Markdown 報告，不要描述你正在使用什麼 API，也不要評論這份資料是由 Python 產生的。
"""


# ============================================================
# 7. Session state
# ============================================================

for key, default in {
    "gemini_report": None,
    "openai_report": None,
    "export_text": None,
    "last_params": None,
    "last_exec_time": 0.0,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ============================================================
# 8. UI
# ============================================================

st.title("🌌 命理全景解析")
st.caption("四系統命盤資料引擎 × Gemini × OpenAI 雙 AI 獨立分析")

with st.container():
    st.markdown("<b>🎛️ 生辰、地理與心理特質參數設定</b>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1, 1.25, 1.25])

    with c1:
        input_gender = st.selectbox(
            "性別",
            ["坤造 (女)", "乾造 (男)"],
            key="f_gen"
        )

    with c2:
        input_date = st.date_input(
            "出生公曆日期",
            value=date(2000, 1, 1),
            min_value=date(1900, 1, 1),
            max_value=date(2100, 12, 31),
            key="f_dt",
        )

    with c3:
        st.markdown("**出生時間**")
        tc1, tc2 = st.columns(2)

        with tc1:
            input_hour = st.selectbox(
                "時",
                list(range(24)),
                format_func=lambda x: f"{x:02d} 時",
                key="f_hour"
            )

        with tc2:
            input_minute = st.selectbox(
                "分",
                list(range(60)),
                format_func=lambda x: f"{x:02d} 分",
                key="f_minute"
            )

        input_time = time(input_hour, input_minute)

    gc1, gc2 = st.columns([1.5, 1])

    with gc1:
        input_location = st.text_input(
            "出生國家 / 城市（可中英文輸入）",
            value="",
            key="f_loc",
        )

    with gc2:
        input_mbti = st.text_input(
            "MBTI 人格類型（選填）",
            value="",
            key="f_mbti",
        )

    cooldown_total = 10
    time_passed = py_time.time() - st.session_state.last_exec_time
    is_cooling_down = time_passed < cooldown_total
    remaining_cooldown = max(1, math.ceil(cooldown_total - time_passed))

    if is_cooling_down:
        btn_label = f"⏳ 冷卻中 ({remaining_cooldown}秒)"
        btn_disabled = True
        py_time.sleep(1)
        st.rerun()
    else:
        btn_label = "🚀 開始 Gemini + OpenAI 雙 AI 深度詳算"
        btn_disabled = False

    exec_btn = st.button(
        btn_label,
        disabled=btn_disabled,
        type="primary",
        use_container_width=False,
    )

status_placeholder = st.empty()

st.markdown("""
<div class="warning-box">
<b>📌 本版本的重要修正</b><br>
八字的「天干十神」與「地支藏干十神」已分離計算。AI 不再把地支藏干的十神誤當成四柱天干十神。
</div>
""", unsafe_allow_html=True)


# ============================================================
# 9. Calculate charts
# ============================================================

current_params = f"{input_gender}_{input_date}_{input_hour}_{input_minute}_{input_location}_{input_mbti}"

if st.session_state.last_params != current_params:
    st.session_state.gemini_report = None
    st.session_state.openai_report = None
    st.session_state.export_text = None
    st.session_state.last_params = current_params

birth_dt = datetime.combine(input_date, input_time)
bazi, ziwei, lunar_str = calculate_real_oriental(birth_dt)
astrology = get_astrology_data(birth_dt, input_location)
human_design = calculate_real_human_design(birth_dt, input_location)

today_year = datetime.now().year
calculated_age = today_year - input_date.year

if calculated_age < 22:
    life_stage_desc = (
        f"學習與扎根階段（約 {calculated_age} 歲）："
        "分析重心聚焦於學業、知識吸收、身心健康與家庭支持，淡化事業擴張。"
    )
elif calculated_age >= 65:
    life_stage_desc = (
        f"退休與人生整合階段（約 {calculated_age} 歲）："
        "分析重心轉向健康、生活品質、家庭陪伴與精神傳承。"
    )
else:
    life_stage_desc = (
        f"青壯年與事業發展階段（約 {calculated_age} 歲）："
        "分析重心聚焦於事業定位、知識資產化、財富槓桿與精力邊界。"
    )


# ============================================================
# 10. Pure chart export
# ============================================================

pure_chart_data = f"""# 四系統純命盤結構數據
生成時間：{datetime.now().strftime("%Y-%m-%d %H:%M")}
生辰設定：{birth_dt.strftime("%Y-%m-%d %H:%M")} ({lunar_str})
出生地點：{input_location if input_location else "未指定"}
性別設定：{input_gender}
計算年齡：約 {calculated_age} 歲
生命階段：{life_stage_desc}
MBTI：{input_mbti if input_mbti else "未填寫"}

==================================================
1. 【八字資料引擎】

日主：{bazi["日主"]}

四柱：
"""

for label in ["年柱", "月柱", "日柱", "時柱"]:
    p = bazi["四柱"][label]

    pure_chart_data += (
        f"{label}: {p['干']}{p['支']} | "
        f"天干五行={p['天干五行']} | "
        f"天干十神={p['天干十神']} | "
        f"地支本氣={p['地支本氣五行']} | "
        f"納音={p['納音']}\n"
        f"  藏干："
    )

    if p["藏干"]:
        pure_chart_data += "；".join(
            f"{h['天干']}({h['位置']}/{h['五行']}/{h['十神']})"
            for h in p["藏干"]
        )
    else:
        pure_chart_data += "無"

    pure_chart_data += "\n"

pure_chart_data += "\n天干十神統計：\n"
pure_chart_data += json.dumps(bazi["天干十神統計"], ensure_ascii=False)

pure_chart_data += "\n\n藏干十神統計：\n"
pure_chart_data += json.dumps(bazi["藏干十神統計"], ensure_ascii=False)

pure_chart_data += "\n\n五行概況（天干＋地支本氣）：\n"
pure_chart_data += json.dumps(
    bazi["五行概況_天干加地支本氣"],
    ensure_ascii=False
)

pure_chart_data += "\n\n地支關係：\n"
pure_chart_data += json.dumps(
    bazi["地支關係"],
    ensure_ascii=False,
    indent=2
)

pure_chart_data += "\n\n==================================================\n2. 【紫微斗數資料】\n"

for p_name, p_info in ziwei.items():
    pure_chart_data += (
        f"- {p_name} ({p_info['地支']}): "
        f"主星 [{' '.join(p_info['主星'])}] "
        f"輔星 [{' '.join(p_info['輔星'])}]\n"
    )

pure_chart_data += f"""
==================================================
3. 【西洋星座資料】
太陽：{astrology['太陽星座']}
月亮：{astrology['月亮星座']}
上升：{astrology['上升星座 (ASC)']}
水星：{astrology['水星星座']}
金星：{astrology['金星星座']}
火星：{astrology['火星星座']}

==================================================
4. 【人類圖資料】
能量類型：{human_design['能量類型']}
人生角色：{human_design['人生角色']}
內在權威：{human_design['內在權威']}
人生策略：{human_design['人生策略']}
黑盤印記：{human_design['黑盤印記']}
紅盤印記：{human_design['紅盤印記']}
接通通道：{', '.join(human_design['接通之通道'])}
已定義中心：{', '.join(human_design['已定義中心'])}
"""


# ============================================================
# 11. Chart dashboard
# ============================================================

col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    st.download_button(
        "💾 下載純命盤（含完整八字結構）",
        data=pure_chart_data,
        file_name=f"四系統純命盤_{birth_dt.strftime('%Y%m%d')}.txt",
        mime="text/plain",
        use_container_width=True,
    )

with col_btn2:
    report_ready = (
        st.session_state.gemini_report is not None
        or st.session_state.openai_report is not None
    )

    if report_ready:
        st.download_button(
            "📂 下載雙 AI 完整解析報告",
            data=st.session_state.export_text or "",
            file_name=f"命理雙AI詳算報告_{birth_dt.strftime('%Y%m%d')}.txt",
            mime="text/plain",
            use_container_width=True,
        )
    else:
        st.button(
            "📂 下載雙 AI 完整解析報告",
            disabled=True,
            use_container_width=True
        )

st.divider()

st.markdown("<b>📊 四系統獨立命盤儀表板</b>", unsafe_allow_html=True)

tab_bazi, tab_ziwei, tab_astro, tab_hd = st.tabs(
    ["🏮 八字系統", "🔮 紫微系統", "🪐 星座系統", "🧬 人類圖系統"]
)

with tab_bazi:
    st.markdown("### 【子平八字四柱】")

    b_cols = st.columns(4)

    for i, label in enumerate(["年柱", "月柱", "日柱", "時柱"]):
        with b_cols[i]:
            p = bazi["四柱"][label]

            st.markdown(
                f"""
                <div class="bazi-col">
                    <div class="bazi-label">{label}</div>
                    <div class="bazi-label">天干十神：{p["天干十神"]}</div>
                    <div class="bazi-tg">{p["干"]}</div>
                    <div class="bazi-dz">{p["支"]}</div>
                    <div class="bazi-label">地支本氣：{p["地支本氣五行"]}</div>
                    <div class="bazi-label">{p["納音"]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if p["藏干"]:
                hidden_text = "；".join(
                    f"{h['天干']}＝{h['十神']}（{h['位置']}）"
                    for h in p["藏干"]
                )

                st.markdown(
                    f"<div class='sub-card'><b>藏干</b><br>{hidden_text}</div>",
                    unsafe_allow_html=True,
                )

    st.markdown("#### 📐 八字結構統計")
    st.write(f"**日主：** {bazi['日主']}")
    st.write(f"**天干十神：** {bazi['天干十神統計']}")
    st.write(f"**藏干十神：** {bazi['藏干十神統計']}")
    st.write(
        f"**五行概況（天干＋地支本氣）：** "
        f"{bazi['五行概況_天干加地支本氣']}"
    )

    st.markdown("#### 🔗 地支關係")

    relation_rows = []

    for rel_name, values in bazi["地支關係"].items():
        relation_rows.append({
            "關係": rel_name,
            "結果": "、".join(values) if values else "未形成",
        })

    st.table(relation_rows)

    st.info(
        "本頁已將「天干十神」與「地支藏干十神」分開。"
        "五行概況是結構統計，不直接等同於日主旺衰強弱。"
    )

with tab_ziwei:
    st.markdown("### 【紫微斗數十二宮】")

    ziwei_cols = st.columns(3)
    idx = 0

    for palace_name, p_info in ziwei.items():
        with ziwei_cols[idx % 3]:
            majors = " ".join(
                f"<span class='star-major'>{s}</span>"
                for s in p_info["主星"]
            )

            minors = " ".join(
                f"<span class='star-minor'>{s}</span>"
                for s in p_info["輔星"]
            )

            st.markdown(
                f"""
                <div class="palace-card">
                    <div class="palace-title">
                        {palace_name} ({p_info['地支']})
                    </div>
                    <div>{majors}</div>
                    <div>{minors}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        idx += 1

    st.caption(
        "紫微部分沿用目前網站的資料呈現架構；"
        "若之後要追求完整傳統排盤，可再獨立重建紫微計算引擎。"
    )

with tab_astro:
    st.markdown(
        f"### 【西洋黃道天文星曆：{input_location if input_location else '未指定地點'}】"
    )

    st.markdown(
        f"""
        <div class="sub-card">
        <div><span class="tag-badge tag-astro">太陽</span><b>{astrology['太陽星座']}</b></div>
        <div><span class="tag-badge tag-astro">月亮</span><b>{astrology['月亮星座']}</b></div>
        <div><span class="tag-badge tag-astro">上升</span><b>{astrology['上升星座 (ASC)']}</b></div>
        <div><span class="tag-badge tag-astro">水星</span>{astrology['水星星座']}</div>
        <div><span class="tag-badge tag-astro">金星</span>{astrology['金星星座']}</div>
        <div><span class="tag-badge tag-astro">火星</span>{astrology['火星星座']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_hd:
    st.markdown("### 【人類圖資料】")

    channels_str = "<br>".join(
        f"• {c}" for c in human_design["接通之通道"]
    )
    centers_str = "、".join(human_design["已定義中心"])

    st.markdown(
        f"""
        <div class="sub-card">
        <div><span class="tag-badge tag-hd">類型</span><b>{human_design['能量類型']}</b></div>
        <div><span class="tag-badge tag-hd">角色</span><b>{human_design['人生角色']}</b></div>
        <div><span class="tag-badge tag-hd">權威</span><b>{human_design['內在權威']}</b></div>
        <div><span class="tag-badge tag-hd">策略</span><b>{human_design['人生策略']}</b></div>
        <div><b>黑盤：</b>{human_design['黑盤印記']}</div>
        <div><b>紅盤：</b>{human_design['紅盤印記']}</div>
        <hr>
        <div><b>接通通道：</b><br>{channels_str}</div>
        <div><b>已定義中心：</b>{centers_str}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# 12. AI execution
# ============================================================

gemini_keys = load_gemini_keys("api_key.txt")

if exec_btn:
    is_default = (
        input_date == date(2000, 1, 1)
        and input_hour == 0
        and input_minute == 0
        and not input_location.strip()
        and not input_mbti.strip()
    )

    if is_default:
        status_placeholder.warning(
            "⚠️ 請先填寫實際出生日期、時間與出生地點，再開始 AI 分析。"
        )

    else:
        full_chart_summary = {
            "生辰與地理參數": {
                "公曆": birth_dt.strftime("%Y-%m-%d %H:%M"),
                "農曆": lunar_str,
                "性別": input_gender,
                "出生地點": input_location if input_location else "未指定",
                "MBTI人格類型": input_mbti if input_mbti else "未填寫",
                "計算年齡": f"約 {calculated_age} 歲",
                "生命階段與分析重心": life_stage_desc,
            },
            "東方排盤": {
                "八字": bazi,
                "紫微完整十二宮": ziwei,
            },
            "西洋占星": astrology,
            "人類圖": human_design,
        }

        gemini_prompt = build_prompt(
            full_chart_summary,
            calculated_age,
            life_stage_desc,
            "Gemini",
        )

        openai_prompt = build_prompt(
            full_chart_summary,
            calculated_age,
            life_stage_desc,
            "OpenAI",
        )

        st.session_state.last_exec_time = py_time.time()

        progress = st.empty()

        # 兩個 AI 完全獨立分析，不互相讀取對方結果。
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_gemini = executor.submit(
                call_gemini_api,
                gemini_prompt,
                gemini_keys,
            )

            future_openai = executor.submit(
                call_openai_api,
                openai_prompt,
            )

            while not future_gemini.done() or not future_openai.done():
                g_state = "完成" if future_gemini.done() else "分析中"
                o_state = "完成" if future_openai.done() else "分析中"

                progress.info(
                    f"🟢 Gemini：{g_state}　　🟣 OpenAI：{o_state}"
                )

                py_time.sleep(0.8)

            gemini_res = future_gemini.result()
            openai_res = future_openai.result()

        progress.success("✅ 雙 AI 分析完成！")

        st.session_state.gemini_report = gemini_res
        st.session_state.openai_report = openai_res

        st.session_state.export_text = f"""# 命理雙 AI 詳算報告
生成時間：{datetime.now().strftime("%Y-%m-%d %H:%M")}
命盤生辰：{birth_dt.strftime("%Y-%m-%d %H:%M")} ({lunar_str})
出生地點：{input_location if input_location else "未指定"}
性別：{input_gender}
年齡：約 {calculated_age} 歲
MBTI：{input_mbti if input_mbti else "未填寫"}

==================================================
【原始排盤與心理結構化資料】
{json.dumps(full_chart_summary, ensure_ascii=False, indent=2)}

==================================================
【GEMINI｜命理結構研究分析】
{gemini_res}

==================================================
【OPENAI｜心理與人生策略批判分析】
{openai_res}
"""

        st.rerun()


# ============================================================
# 13. Reports
# ============================================================

if st.session_state.gemini_report or st.session_state.openai_report:
    st.divider()
    st.markdown("## 📜 雙 AI 專家四系統交叉深度詳算")

    tab_g, tab_o = st.tabs([
        "🟢 Gemini｜命理結構研究",
        "🟣 OpenAI｜心理策略批判",
    ])

    with tab_g:
        if st.session_state.gemini_report:
            st.markdown(st.session_state.gemini_report)
        else:
            st.error("Gemini 尚未取得報告。")

    with tab_o:
        if st.session_state.openai_report:
            st.markdown(st.session_state.openai_report)
        else:
            st.error("OpenAI 尚未取得報告。")

    st.caption(
        "雙 AI 以相同的結構化命盤資料獨立分析；兩者不讀取對方報告，"
        "因此可以觀察共識、差異與矛盾。"
    )
