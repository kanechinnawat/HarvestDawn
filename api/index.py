# File: api/index.py
from __future__ import annotations

import os
import random
from typing import Dict, Any, List, Tuple

import pandas as pd
from flask import Flask, render_template, request, jsonify

# --- App & paths ---
SCRIPT_DIR = os.path.dirname(__file__)
TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "..", "templates")
CSV_PATH = os.path.join(SCRIPT_DIR, "..", "crop_requirement.csv")

app = Flask(__name__, template_folder=TEMPLATE_DIR)

# --- Load crop database ---
def _load_crop_database(csv_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(csv_path)
        df.columns = [c.strip().lower() for c in df.columns]
        return df
    except FileNotFoundError:
        print(f"[ERROR] CSV not found at: {csv_path}")
        return pd.DataFrame()
    except Exception as e:
        print(f"[ERROR] Failed loading CSV: {e}")
        return pd.DataFrame()

CROP_DB = _load_crop_database(CSV_PATH)

# --- Prototype helpers ---
MARKET_TRENDS = [
    "คงที่",
    "เพิ่มขึ้น",
    "เพิ่มขึ้นเล็กน้อย",
    "ผันผวน",
    "ปรับตัวลดลงเล็กน้อย",
]

POSITIVE_TIPS = [
    "ปริมาณน้ำฝนสอดคล้องกับความต้องการ เหมาะต่อการงอกและระยะเจริญเติบโต",
    "อุณหภูมิเฉลี่ยอยู่ในช่วงที่พืชปรับตัวได้ดี ลดความเสี่ยงต่อโรค",
    "ลาดชันไม่มาก เหมาะต่อการระบายน้ำและการเข้าถึงด้วยเครื่องจักร",
    "ชนิดดินเอื้อต่อการระบายน้ำและการอุ้มน้ำที่สมดุล",
    "วางแผนปลูกช่วงต้นฤดูฝนเพื่อลดต้นทุนการให้น้ำ",
]

IMPROVEMENT_TIPS = [
    "ปรับปรุงดินด้วยปุ๋ยคอก/ปุ๋ยหมักเพื่อเพิ่มอินทรียวัตถุ",
    "จัดร่องระบายน้ำหรือคลุมดิน ลดการชะล้างหน้าดิน",
    "เลือกพันธุ์ทนแล้ง/ทนน้ำตามสภาพพื้นที่",
    "ปรับตารางให้น้ำแบบสั้นถี่ในระยะสำคัญ",
    "ปลูกพืชคลุมดินเพื่อรักษาความชื้น",
]

def mock_env_from_polygon(geojson_str: str | None) -> Dict[str, Any]:
    """จำลองสภาพแวดล้อมจาก polygon; มี seed เพื่อให้สุ่มคงที่ในแต่ละพื้นที่"""
    seed = hash(geojson_str or "") & 0xFFFFFFFF
    rng = random.Random(seed)
    soil_types = ["ดินร่วน", "ดินร่วนปนทราย", "ดินเหนียว", "ดินทราย"]
    return {
        "soil_type": rng.choice(soil_types),
        "avg_rainfall_mm": 900 + rng.random() * 1600,   # 900-2500 mm/ปี
        "avg_temp_celsius": 22 + rng.random() * 12,     # 22-34 °C
        "slope_degree": rng.random() * 15,              # 0-15 °
        "seed": seed,
    }

def _choose_trend(existing: str | None, rng: random.Random) -> str:
    """สุ่มแนวโน้มราคา (ให้ 'เพิ่มขึ้น' โผล่บ่อยขึ้นเล็กน้อย)"""
    pool = ["คงที่"]*2 + ["เพิ่มขึ้น"]*3 + ["เพิ่มขึ้นเล็กน้อย"]*2 + ["ผันผวน"]*2 + ["ปรับตัวลดลงเล็กน้อย"]
    if not existing or existing.strip() == "" or rng.random() < 0.6:
        return rng.choice(pool)
    return str(existing)

def _gen_advice_by_band(env: Dict[str, Any], reasons: List[str], score: int, rng: random.Random) -> str:
    """คำแนะนำให้สัมพันธ์กับย่านคะแนน"""
    rain = env["avg_rainfall_mm"]
    temp = env["avg_temp_celsius"]
    slope = env["slope_degree"]
    soil = env["soil_type"]

    if score >= 5:
        base = rng.choice(POSITIVE_TIPS)
        extra = rng.choice([
            f"จากปริมาณน้ำฝน ~{rain:.0f} มม./ปี",
            f"อุณหภูมิเฉลี่ย ~{temp:.0f}°C",
            f"ลาดชันเฉลี่ย ~{slope:.0f}°",
            f"ชนิดดิน: {soil}",
        ])
        return f"{base} | {extra}"

    if 3 <= score <= 4:
        seg1 = "โดยรวมเหมาะสม แต่ยังมีประเด็นที่ควรเฝ้าระวังเล็กน้อย"
        seg2 = rng.choice(POSITIVE_TIPS)
        return f"{seg1} | {seg2}"

    # 0-2 คะแนน: เน้นข้อควรปรับปรุง
    picked = reasons[:]
    if not picked:
        picked = [rng.choice(IMPROVEMENT_TIPS)]
    improve = rng.choice(IMPROVEMENT_TIPS)
    return "ข้อควรปรับปรุง: " + " ; ".join(picked) + f" | แนวทาง: {improve}"

def _deterministic_score(row: pd.Series, env: Dict[str, Any]) -> Tuple[int, List[str]]:
    """คำนวณคะแนนพื้นฐาน 0–5 + เหตุผลที่ทำให้ลดคะแนน (ยืดหยุ่นตาม schema)"""
    wanted_soil = row.get("soil_type") or row.get("ชนิดดิน") or ""
    min_rain = row.get("min_rain_mm") or row.get("ฝนต่ำสุด") or None
    max_rain = row.get("max_rain_mm") or row.get("ฝนสูงสุด") or None
    min_temp = row.get("min_temp_c") or row.get("อุณหภูมิต่ำสุด") or None
    max_temp = row.get("max_temp_c") or row.get("อุณหภูมิสูงสุด") or None
    slope_max = row.get("slope_max_deg") or row.get("ความลาดสูงสุด") or None

    score = 0
    reasons: List[str] = []

    # Soil
    if wanted_soil:
        if str(env["soil_type"]).strip() == str(wanted_soil).strip():
            score += 1
        else:
            reasons.append(f"ชนิดดิน ({env['soil_type']}) ต่างจากที่แนะนำ ({wanted_soil})")
    else:
        score += 1

    # Rain
    rain = env["avg_rainfall_mm"]
    if pd.notna(min_rain) and pd.notna(max_rain):
        if float(min_rain) <= rain <= float(max_rain):
            score += 2
        else:
            reasons.append(f"ปริมาณฝน {rain:.0f} มม./ปี อยู่นอกช่วง ({min_rain}-{max_rain})")
    else:
        score += 2

    # Temperature
    temp = env["avg_temp_celsius"]
    if pd.notna(min_temp) and pd.notna(max_temp):
        if float(min_temp) <= temp <= float(max_temp):
            score += 1
        else:
            reasons.append(f"อุณหภูมิ {temp:.0f}°C อยู่นอกช่วง ({min_temp}-{max_temp})")
    else:
        score += 1

    # Slope
    slope = env["slope_degree"]
    if pd.notna(slope_max):
        if slope <= float(slope_max):
            score += 1
        else:
            reasons.append(f"ความลาดชัน {slope:.0f}° สูงกว่า {slope_max}°")
    else:
        score += 1

    return score, reasons

def score_row(row: pd.Series, env: Dict[str, Any]) -> Dict[str, Any]:
    """สรุปผลคะแนน + สุ่มปรับ (jitter) + คำแนะนำที่สอดคล้องคะแนน"""
    name = row.get("crop_name") or row.get("name") or row.get("พืช") or "Unknown Crop"

    # rng ที่ผูกกับพื้นที่ + ชื่อพืช เพื่อให้สุ่มคงที่ตาม polygon
    local_seed = (env.get("seed", 0) ^ (hash(str(name)) & 0xFFFFFFFF)) & 0xFFFFFFFF
    rng = random.Random(local_seed)

    base_score, reasons = _deterministic_score(row, env)

    # Jitter: ปรับคะแนนรอบ ๆ base ให้มีความหลากหลาย แต่ยังสมเหตุผล
    candidates = [
        max(0, base_score - 2),
        max(0, base_score - 1),
        base_score,
        min(5, base_score + 1),
    ]
    weights = [1, 3, 4, 2]  # โอกาสได้ใกล้ base มากที่สุด
    final_score = rng.choices(candidates, weights=weights, k=1)[0]

    # แนวโน้มราคา (สุ่มแบบมีน้ำหนัก)
    trend_raw = row.get("market_trend") or row.get("trend") or row.get("แนวโน้มราคา") or None
    trend = _choose_trend(trend_raw, rng)

    advice = _gen_advice_by_band(env, reasons, final_score, rng)

    return {
        "crop_name": str(name),
        "market_trend": str(trend),
        "suitability_score": int(final_score),
        "max_score": 5,
        "reasons_for_low_score": reasons,
        "advice": advice,
    }

def build_recommendations(env: Dict[str, Any]) -> List[Dict[str, Any]]:
    if CROP_DB.empty:
        rows = pd.DataFrame([
            {"crop_name": "ข้าว", "soil_type": "ดินร่วน", "min_rain_mm": 1200, "max_rain_mm": 2000, "min_temp_c": 20, "max_temp_c": 35, "slope_max_deg": 5},
            {"crop_name": "มันสำปะหลัง", "soil_type": "ดินร่วนปนทราย", "min_rain_mm": 1000, "max_rain_mm": 1500, "min_temp_c": 22, "max_temp_c": 35, "slope_max_deg": 12},
            {"crop_name": "อ้อย", "soil_type": "ดินร่วน", "min_rain_mm": 1100, "max_rain_mm": 1800, "min_temp_c": 23, "max_temp_c": 34, "slope_max_deg": 10},
            {"crop_name": "ข้าวโพดเลี้ยงสัตว์", "soil_type": "ดินร่วนปนทราย", "min_rain_mm": 1000, "max_rain_mm": 1800, "min_temp_c": 20, "max_temp_c": 35, "slope_max_deg": 10},
            {"crop_name": "ยางพารา", "soil_type": "ดินร่วน", "min_rain_mm": 1600, "max_rain_mm": 2500, "min_temp_c": 23, "max_temp_c": 34, "slope_max_deg": 12},
        ]).to_dict(orient="records")
    else:
        rows = CROP_DB.to_dict(orient="records")

    scored = [score_row(pd.Series(r), env) for r in rows]
    scored.sort(key=lambda d: d["suitability_score"], reverse=True)
    return scored

# --- Routes ---
@app.get("/health")
def health():
    return jsonify({"ok": True})

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        polygon = request.form.get("polygon_coords")
        env = mock_env_from_polygon(polygon)
        recs = build_recommendations(env)
        return render_template(
            "index.html",
            recommendations=recs,
            input_data=env,
            has_recommendations=True,
        )
    # GET
    return render_template(
        "index.html",
        recommendations=None,
        input_data={"soil_type": "", "avg_rainfall_mm": 0, "avg_temp_celsius": 0, "slope_degree": 0},
        has_recommendations=False,
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
