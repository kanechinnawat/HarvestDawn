# File: api/index.py
from __future__ import annotations

import os
import json
import math
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

# --- Helpers ---
def mock_env_from_polygon(geojson_str: str | None) -> Dict[str, Any]:
    random.seed(len(geojson_str or ""))
    soil_types = ["ดินร่วน", "ดินร่วนปนทราย", "ดินเหนียว", "ดินทราย"]
    return {
        "soil_type": random.choice(soil_types),
        "avg_rainfall_mm": 900 + random.random() * 1600,
        "avg_temp_celsius": 22 + random.random() * 12,
        "slope_degree": random.random() * 15,
    }

def score_row(row: pd.Series, env: Dict[str, Any]) -> Dict[str, Any]:
    name = row.get("crop_name") or row.get("name") or row.get("พืช") or "Unknown Crop"
    trend = row.get("market_trend") or row.get("trend") or row.get("แนวโน้มราคา") or "คงที่"
    wanted_soil = row.get("soil_type") or row.get("ชนิดดิน") or ""
    min_rain = row.get("min_rain_mm") or row.get("ฝนต่ำสุด") or None
    max_rain = row.get("max_rain_mm") or row.get("ฝนสูงสุด") or None
    min_temp = row.get("min_temp_c") or row.get("อุณหภูมิต่ำสุด") or None
    max_temp = row.get("max_temp_c") or row.get("อุณหภูมิสูงสุด") or None
    slope_max = row.get("slope_max_deg") or row.get("ความลาดสูงสุด") or None

    score = 0
    max_score = 5
    reasons: List[str] = []

    if wanted_soil:
        if str(env["soil_type"]).strip() == str(wanted_soil).strip():
            score += 1
        else:
            reasons.append(f"ชนิดดิน ({env['soil_type']}) ต่างจากที่แนะนำ ({wanted_soil})")
    else:
        score += 1

    rain = env["avg_rainfall_mm"]
    if pd.notna(min_rain) and pd.notna(max_rain):
        if float(min_rain) <= rain <= float(max_rain):
            score += 2
        else:
            reasons.append(f"ปริมาณฝน {rain:.0f} มม./ปี อยู่นอกช่วง ({min_rain}-{max_rain})")
    else:
        score += 2

    temp = env["avg_temp_celsius"]
    if pd.notna(min_temp) and pd.notna(max_temp):
        if float(min_temp) <= temp <= float(max_temp):
            score += 1
        else:
            reasons.append(f"อุณหภูมิ {temp:.0f}°C อยู่นอกช่วง ({min_temp}-{max_temp})")
    else:
        score += 1

    slope = env["slope_degree"]
    if pd.notna(slope_max):
        if slope <= float(slope_max):
            score += 1
        else:
            reasons.append(f"ความลาดชัน {slope:.0f}° สูงกว่า {slope_max}°")
    else:
        score += 1

    return {
        "crop_name": str(name),
        "market_trend": str(trend),
        "suitability_score": int(score),
        "max_score": max_score,
        "reasons_for_low_score": reasons,
    }

def build_recommendations(env: Dict[str, Any]) -> List[Dict[str, Any]]:
    if CROP_DB.empty:
        fallback = pd.DataFrame([
            {"crop_name": "ข้าว", "soil_type": "ดินร่วน", "min_rain_mm": 1200, "max_rain_mm": 2000, "min_temp_c": 20, "max_temp_c": 35, "slope_max_deg": 5, "market_trend": "คงที่"},
            {"crop_name": "มันสำปะหลัง", "soil_type": "ดินร่วนปนทราย", "min_rain_mm": 1000, "max_rain_mm": 1500, "min_temp_c": 22, "max_temp_c": 35, "slope_max_deg": 12, "market_trend": "เพิ่มขึ้นเล็กน้อย"},
            {"crop_name": "อ้อย", "soil_type": "ดินร่วน", "min_rain_mm": 1100, "max_rain_mm": 1800, "min_temp_c": 23, "max_temp_c": 34, "slope_max_deg": 10, "market_trend": "คงที่"},
        ])
        rows = fallback.to_dict(orient="records")
    else:
        rows = CROP_DB.to_dict(orient="records")

    scored = [score_row(pd.Series(r), env) for r in rows]
    random.shuffle(scored)
    scored.sort(key=lambda d: d["suitability_score"], reverse=True)
    return scored[:8]

@app.get("/health")
def health():
    return jsonify({"ok": True})

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        polygon = request.form.get("polygon_coords")
        env = mock_env_from_polygon(polygon)
        recs = build_recommendations(env)
        return render_template("index.html", recommendations=recs, input_data=env, has_recommendations=True)
    return render_template(
        "index.html",
        recommendations=None,
        input_data={"soil_type": "", "avg_rainfall_mm": 0, "avg_temp_celsius": 0, "slope_degree": 0},
        has_recommendations=False,
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
