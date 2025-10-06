# File: api/index.py
from __future__ import annotations

import os
import random
from typing import Dict, Any, List

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

# --- Helpers for prototype diversity ---
PRICE_TRENDS = [
    "เพิ่มขึ้น", "เพิ่มขึ้นเล็กน้อย", "คงที่", "ลดลงเล็กน้อย"
]

POSITIVE_TEMPLATES = [
    "สภาพปริมาณน้ำฝนเหมาะแก่การเพาะปลูก (≈ {rain:.0f} มม./ปี)",
    "อุณหภูมิเฉลี่ยสอดคล้องกับความต้องการพืช (≈ {temp:.0f}°C)",
    "ความลาดชันพื้นที่อยู่ในเกณฑ์เหมาะสม (≈ {slope:.0f}°)",
    "ชนิดดิน ({soil}) เหมาะกับพืชชนิดนี้",
]
CAUTION_TEMPLATES = [
    "อาจต้องปรับการระบายน้ำหากเกิดฝนสูงกว่าค่าเฉลี่ย (≈ {rain:.0f} มม./ปี)",
    "ควรวางแผนคลุมดินหรือให้น้ำเสริมในช่วงอากาศร้อน (≈ {temp:.0f}°C)",
    "พื้นที่ค่อนข้างลาดชัน (≈ {slope:.0f}°) ควรจัดแถวปลูกตามแนวชัน",
    "ชนิดดิน ({soil}) อาจต้องเสริมอินทรียวัตถุเพื่อเพิ่มความอุ้มน้ำ",
]

def mock_env_from_polygon(geojson_str: str | None) -> Dict[str, Any]:
    """Simulate environmental features from a polygon geojson string."""
    random.seed(len(geojson_str or ""))  # ทำให้สุ่มคงที่ต่อ polygon
    soil_types = ["ดินร่วน", "ดินร่วนปนทราย", "ดินเหนียว", "ดินทราย"]
    return {
        "soil_type": random.choice(soil_types),
        "avg_rainfall_mm": 900 + random.random() * 1600,   # 900-2500
        "avg_temp_celsius": 22 + random.random() * 12,     # 22-34
        "slope_degree": random.random() * 15,              # 0-15
    }

def _pick_trend() -> str:
    # ให้ความน่าจะเป็นของ “คงที่/เพิ่มขึ้นเล็กน้อย” สูงกว่าเล็กน้อย
    weights = [0.25, 0.35, 0.3, 0.1]
    return random.choices(PRICE_TRENDS, weights=weights, k=1)[0]

def _make_advice(env: Dict[str, Any], soil_ok: bool, rain_ok: bool, temp_ok: bool, slope_ok: bool) -> str:
    """สุ่มคำแนะนำเชิงบวก + เชิงข้อควรระวัง"""
    pos_pool = []
    if soil_ok: pos_pool.append(POSITIVE_TEMPLATES[3])
    if rain_ok: pos_pool.append(POSITIVE_TEMPLATES[0])
    if temp_ok: pos_pool.append(POSITIVE_TEMPLATES[1])
    if slope_ok: pos_pool.append(POSITIVE_TEMPLATES[2])
    if not pos_pool:
        pos_pool = POSITIVE_TEMPLATES[:]  # เผื่อทุกอย่างไม่ ok ก็สุ่มคำชมทั่วไป

    cau_pool = []
    if not rain_ok: cau_pool.append(CAUTION_TEMPLATES[0])
    if not temp_ok: cau_pool.append(CAUTION_TEMPLATES[1])
    if not slope_ok: cau_pool.append(CAUTION_TEMPLATES[2])
    if not soil_ok: cau_pool.append(CAUTION_TEMPLATES[3])
    # ถ้าทุกอย่าง ok ให้สุ่มคำแนะนำทั่วไป 1 ข้อ
    if not cau_pool:
        cau_pool = [CAUTION_TEMPLATES[1], CAUTION_TEMPLATES[0]]

    positive = random.choice(pos_pool)
    caution  = random.choice(cau_pool)

    return f"{positive.format(rain=env['avg_rainfall_mm'], temp=env['avg_temp_celsius'], slope=env['slope_degree'], soil=env['soil_type'])} — {caution.format(rain=env['avg_rainfall_mm'], temp=env['avg_temp_celsius'], slope=env['slope_degree'], soil=env['soil_type'])}"

def score_row(row: pd.Series, env: Dict[str, Any]) -> Dict[str, Any]:
    """คำนวณคะแนน + เติมความหลากหลายแบบ prototype"""
    name = row.get("crop_name") or row.get("name") or row.get("พืช") or "Unknown Crop"
    wanted_soil = row.get("soil_type") or row.get("ชนิดดิน") or ""
    min_rain = row.get("min_rain_mm") or row.get("ฝนต่ำสุด") or None
    max_rain = row.get("max_rain_mm") or row.get("ฝนสูงสุด") or None
    min_temp = row.get("min_temp_c") or row.get("อุณหภูมิต่ำสุด") or None
    max_temp = row.get("max_temp_c") or row.get("อุณหภูมิสูงสุด") or None
    slope_max = row.get("slope_max_deg") or row.get("ความลาดสูงสุด") or None

    # ฐานคะแนน
    score = 0
    max_score = 5
    reasons: List[str] = []

    # เช็คเงื่อนไขทีละด้าน
    soil_ok = True
    if wanted_soil:
        soil_ok = (str(env["soil_type"]).strip() == str(wanted_soil).strip())
        if soil_ok:
            score += 1
        else:
            reasons.append(f"ชนิดดิน ({env['soil_type']}) ต่างจากที่แนะนำ ({wanted_soil})")
    else:
        score += 1  # unknown -> neutral pass

    rain_ok = True
    rain = env["avg_rainfall_mm"]
    if pd.notna(min_rain) and pd.notna(max_rain):
        rain_ok = float(min_rain) <= rain <= float(max_rain)
        if rain_ok:
            score += 2
        else:
            reasons.append(f"ปริมาณฝน {rain:.0f} มม./ปี อยู่นอกช่วง ({min_rain}-{max_rain})")
    else:
        score += 2

    temp_ok = True
    temp = env["avg_temp_celsius"]
    if pd.notna(min_temp) and pd.notna(max_temp):
        temp_ok = float(min_temp) <= temp <= float(max_temp)
        if temp_ok:
            score += 1
        else:
            reasons.append(f"อุณหภูมิ {temp:.0f}°C อยู่นอกช่วง ({min_temp}-{max_temp})")
    else:
        score += 1

    slope_ok = True
    slope = env["slope_degree"]
    if pd.notna(slope_max):
        slope_ok = slope <= float(slope_max)
        if slope_ok:
            score += 1
        else:
            reasons.append(f"ความลาดชัน {slope:.0f}° สูงกว่า {slope_max}°")
    else:
        score += 1

    # เติมความหลากหลาย: ปรับคะแนนเล็กน้อยแบบ clamp 0..5
    jitter = random.choice([0, 0, 1, -1])  # โอกาสขยับไม่มาก
    score = max(0, min(max_score, score + jitter))

    advice = _make_advice(env, soil_ok, rain_ok, temp_ok, slope_ok)

    return {
        "crop_name": str(name),
        "market_trend": _pick_trend(),
        "suitability_score": int(score),
        "max_score": max_score,
        "reasons_for_low_score": reasons,
        "advice": advice,
        # ใส่ค่าที่ใช้ประกอบ เพื่อโชว์ในคำแนะนำได้ถ้าต้องการ
        "context": {
            "rain": rain, "temp": temp, "slope": slope, "soil": env["soil_type"]
        }
    }

def build_recommendations(env: Dict[str, Any]) -> List[Dict[str, Any]]:
    if CROP_DB.empty:
        fallback = pd.DataFrame([
            {"crop_name": "ข้าว", "soil_type": "ดินร่วน", "min_rain_mm": 1200, "max_rain_mm": 2000, "min_temp_c": 20, "max_temp_c": 35, "slope_max_deg": 5},
            {"crop_name": "มันสำปะหลัง", "soil_type": "ดินร่วนปนทราย", "min_rain_mm": 1000, "max_rain_mm": 1500, "min_temp_c": 22, "max_temp_c": 35, "slope_max_deg": 12},
            {"crop_name": "อ้อย", "soil_type": "ดินร่วน", "min_rain_mm": 1100, "max_rain_mm": 1800, "min_temp_c": 23, "max_temp_c": 34, "slope_max_deg": 10},
            {"crop_name": "ข้าวโพดเลี้ยงสัตว์", "soil_type": "ดินร่วนปนทราย", "min_rain_mm": 1000, "max_rain_mm": 1500, "min_temp_c": 20, "max_temp_c": 35, "slope_max_deg": 10},
            {"crop_name": "ยางพารา", "soil_type": "ดินร่วน", "min_rain_mm": 1500, "max_rain_mm": 2500, "min_temp_c": 24, "max_temp_c": 34, "slope_max_deg": 12},
        ])
        rows = fallback.to_dict(orient="records")
    else:
        rows = CROP_DB.to_dict(orient="records")

    scored = [score_row(pd.Series(r), env) for r in rows]
    random.shuffle(scored)
    scored.sort(key=lambda d: d["suitability_score"], reverse=True)
    # จำกัดจำนวนและให้ความหลากหลายของ trend/คำแนะนำอยู่แล้ว
    return scored[:8]

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
    return render_template(
        "index.html",
        recommendations=None,
        input_data={"soil_type": "", "avg_rainfall_mm": 0, "avg_temp_celsius": 0, "slope_degree": 0},
        has_recommendations=False,
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
