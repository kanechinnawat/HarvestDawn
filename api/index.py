# File: app.py

from flask import Flask, render_template, request
import pandas as pd
import random
import json

# --- 1. การตั้งค่าและโหลดข้อมูล ---
app = Flask(__name__)

try:
    crop_database = pd.read_csv('crop_requirement.csv')
    print("โหลดไฟล์ crop_requirements.csv สำเร็จ")
except FileNotFoundError:
    print("ERROR: ไม่พบไฟล์ crop_requirements.csv กรุณาสร้างไฟล์ก่อนรันแอปพลิเคชัน")
    exit()

# --- 2. ฟังก์ชันจำลองการดึงข้อมูล GIS จากพิกัด ---
def get_mock_gis_data_from_coords(geojson_str):
    """
    รับข้อมูล GeoJSON ของพื้นที่ที่วาด แล้วสุ่มคุณลักษณะของพื้นที่นั้นๆ ออกมา
    """
    soil_types = ["ดินเหนียว", "ดินร่วน", "ดินร่วนปนทราย", "ดินร่วนปนดินเหนียว"]
    try:
        geojson_data = json.loads(geojson_str)
        coords = geojson_data['geometry']['coordinates'][0]
        avg_lat = sum([p[1] for p in coords]) / len(coords)
    except (json.JSONDecodeError, IndexError, TypeError):
        avg_lat = 13.75 # ค่า Default (กรุงเทพฯ)

    if avg_lat > 15: # เหนือเส้นละติจูด 15
        rainfall = random.randint(1000, 1600)
        temp = random.randint(24, 28)
    else: # ใต้เส้นละติจูด 15
        rainfall = random.randint(1500, 2200)
        temp = random.randint(26, 30)

    return {
        "soil_type": random.choice(soil_types),
        "avg_rainfall_mm": rainfall,
        "avg_temp_celsius": temp,
        "slope_degree": random.randint(1, 20)
    }

# --- 3. ฟังก์ชันตรรกะหลัก (เหมือนเดิม) ---
def get_crop_suitability_score(plot_attributes, crop_db):
    recommendations = []
    for index, crop in crop_db.iterrows():
        score = 0; reasons = []
        if plot_attributes['soil_type'] == crop['suitable_soil_type']: score += 1
        else: reasons.append(f"ชนิดดินไม่เหมาะสม (ต้องการ: {crop['suitable_soil_type']})")
        if crop['min_rainfall_mm_per_year'] <= plot_attributes['avg_rainfall_mm'] <= crop['max_rainfall_mm_per_year']: score += 1
        else: reasons.append(f"ปริมาณฝนอยู่นอกช่วงที่เหมาะสม ({crop['min_rainfall_mm_per_year']}-{crop['max_rainfall_mm_per_year']} มม./ปี)")
        if abs(plot_attributes['avg_temp_celsius'] - crop['optimal_temp_celsius']) <= 2: score += 1
        else: reasons.append(f"อุณหภูมิไม่เหมาะสม (ต้องการ: ประมาณ {crop['optimal_temp_celsius']} °C)")
        if plot_attributes['slope_degree'] <= crop['max_slope_degree']: score += 1
        else: reasons.append(f"ความลาดชันสูงเกินไป (ต้องไม่เกิน {crop['max_slope_degree']}°)")
        recommendations.append({
            'crop_name': crop['crop_name'], 'suitability_score': score, 'max_score': 4,
            'reasons_for_low_score': reasons, 'market_trend': get_mock_market_price_trend(crop['crop_name'])
        })
    return sorted(recommendations, key=lambda x: x['suitability_score'], reverse=True)

def get_mock_market_price_trend(crop_name):
    trends = ['ราคาทรงตัว ', 'ราคามีแนวโน้มสูงขึ้น ', 'ราคาปรับตัวลดลง ']
    return random.choice(trends)

# --- 4. สร้างหน้าเว็บหลัก (ปรับปรุงใหม่) ---
@app.route('/', methods=['GET', 'POST'])
def index():
    recommendations = None
    input_data = None
    
    if request.method == 'POST':
        polygon_coords_str = request.form.get('polygon_coords')
        if polygon_coords_str:
            input_data = get_mock_gis_data_from_coords(polygon_coords_str)
            recommendations = get_crop_suitability_score(input_data, crop_database)
    
    # สร้างตัวแปร boolean เพื่อส่งไปให้ JavaScript โดยเฉพาะ
    has_recommendations = True if recommendations else False

    return render_template('index.html', 
                           recommendations=recommendations, 
                           input_data=input_data, 
                           has_recommendations=has_recommendations)
