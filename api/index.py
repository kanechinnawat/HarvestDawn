# File: api/index.py

from flask import Flask, render_template, request
import pandas as pd
import random
import json
import os # <-- 1. เพิ่มการ import os

# --- 1. การตั้งค่าและโหลดข้อมูล (แก้ไขใหม่) ---
app = Flask(__name__)

# --- สร้าง Path ไปยังไฟล์ CSV ให้ถูกต้อง ---
# __file__ คือ path ของไฟล์นี้ (api/index.py)
# os.path.dirname(__file__) คือ path ของโฟลเดอร์ที่ไฟล์นี้อยู่ (api/)
# os.path.join(..., '..') คือการเดินถอยหลังขึ้นไป 1 ระดับ (ไปที่โฟลเดอร์หลัก)
script_dir = os.path.dirname(__file__)
csv_path = os.path.join(script_dir, '..', 'crop_requirement.csv')

try:
    # อ่านไฟล์จาก path ที่ถูกต้อง
    crop_database = pd.read_csv(csv_path)
    print(f"โหลดไฟล์ {csv_path} สำเร็จ")
except FileNotFoundError:
    print(f"ERROR: ไม่พบไฟล์ CSV ที่ path: {csv_path}")
    exit()

# --- ส่วนที่ 2, 3, 4, 5... โค้ดที่เหลือทั้งหมดเหมือนเดิม ไม่ต้องแก้ไข ---
# def get_mock_gis_data_from_coords(...):
# ...