# =============================================================================
# 需要先安裝：python-telegram-bot==20.x, Flask, requests, python-dotenv
# 建議建立一個 .env 檔案來存放您的機敏資訊
# .env 檔案內容範例:
# BOT_TOKEN="7418064668:AAF99T0N3OBvc6m7sxDteESkuc2k6XAjVUA"
# MAPS_API_KEY="AIzaSyBSUtty0NcVe80M_f2D_rg3Lu83kw9PqbE"
# WEBHOOK_URL="http://iremote.ryanisyyds.xyz"
# GROUP_CHAT_ID="-4971098913"
# =============================================================================

import threading
from flask import Flask, request, render_template_string
from datetime import datetime, timedelta, time
import os
import csv
import random
import string
import requests
from math import radians, cos, sin, asin, sqrt
import asyncio
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler
)

# ========== 配置區 ==========
# FIX: 使用 dotenv 讀取環境變數，避免機敏資訊寫死在程式碼中
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
Maps_API_KEY = os.getenv("MAPS_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

WORK_HOURS = {"start": "09:30", "end": "17:30"}
USERS_CSV_FILE = "users.csv"
ATTENDANCE_CSV = "attendance_log.csv"
LEAVE_CSV = "leave_requests.csv"

# ========== 全域變數 ==========
users = {}              # 從 users.csv 載入的使用者資料
gps_sessions = {}       # 暫存 GPS 定位資料 (session_id -> {lat, lon, timestamp, done})
pending_leave = {}      # 暫存請假申請 (待審核)
active_session = {}     # 暫存打卡流程中的 session_id info
forwarding_users = {}   # 用來判斷誰的筆記要轉發

# ========== 檔案初始化 ==========

def ensure_csv_header(file_path, header):
    """通用函數：確保 CSV 檔案存在且有正確的表頭"""
    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)

def ensure_attendance_csv():
    """如果 attendance_log.csv 不存在，則建立並寫入表頭。"""
    header = ["username", "name", "date", "type", "timestamp", "address", "distance_m", "status"]
    ensure_csv_header(ATTENDANCE_CSV, header)

def ensure_leave_csv():
    """如果 leave_requests.csv 不存在，則建立並寫入表頭。"""
    header = [
        "request_id", "username", "name", "reason", "request_time",
        "status", "approver", "decision_time", "deny_reason", "attachments"
    ]
    ensure_csv_header(LEAVE_CSV, header)


# ======== Flask 部分：呈現 GPS 定位頁面 ==========
flask_app = Flask(__name__)

# FIX: HTML_TEMPLATE 保持不變，是正確的。

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>打卡定位授權</title>
    <style>
        /* 省略樣式，沿用原範例 */
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            color: #333;
        }
        .container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 40px 30px;
            text-align: center;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.1);
            max-width: 400px;
            width: 100%;
            transform: translateY(0);
            transition: transform 0.3s ease;
        }
        .container:hover {
            transform: translateY(-5px);
        }
        .icon {
            font-size: 4rem;
            margin-bottom: 20px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        h1 {
            font-size: 1.8rem;
            font-weight: 700;
            margin-bottom: 10px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .subtitle {
            color: #666;
            font-size: 1rem;
            margin-bottom: 30px;
            line-height: 1.5;
        }
        .location-btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 16px 32px;
            font-size: 1.1rem;
            font-weight: 600;
            border-radius: 50px;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.3);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            width: 100%;
            margin-bottom: 20px;
        }
        .location-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 35px rgba(102, 126, 234, 0.4);
        }
        .location-btn:active {
            transform: translateY(0);
        }
        .location-btn:disabled {
            opacity: 0.7;
            cursor: not-allowed;
            transform: none;
        }
        .spinner {
            width: 20px;
            height: 20px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .info-text {
            font-size: 0.9rem;
            color: #888;
            margin-top: 20px;
            padding: 15px;
            background: rgba(102, 126, 234, 0.1);
            border-radius: 10px;
            border-left: 4px solid #667eea;
        }
        .success {
            background: linear-gradient(135deg, #11998e, #38ef7d);
            color: white;
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
            display: none;
        }
        .error {
            background: linear-gradient(135deg, #fc466b, #3f5efb);
            color: white;
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
            display: none;
        }
        @media (max-width: 480px) {
            .container {
                padding: 30px 20px;
                margin: 10px;
            }
            h1 {
                font-size: 1.5rem;
            }
            .icon {
                font-size: 3rem;
            }
        }
        @media (prefers-color-scheme: dark) {
            .container {
                background: rgba(30, 30, 30, 0.95);
                color: #f0f0f0;
            }
            .subtitle {
                color: #ccc;
            }
            .info-text {
                color: #bbb;
                background: rgba(102, 126, 234, 0.2);
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">📍</div>
        <h1>打卡定位授權</h1>
        <p class="subtitle">為了完成打卡流程，我們需要取得您的位置資訊</p>

        <button class="location-btn" onclick="getLocation()" id="locationBtn">
            <span id="btnText">📍 傳送定位</span>
            <div class="spinner" id="spinner" style="display: none;"></div>
        </button>

        <div class="info-text">
            🔒 您的位置資訊將安全傳送並僅用於打卡驗證
        </div>

        <div class="success" id="successMsg">
            ✅ 定位已成功傳送！您可以返回 Telegram 了
        </div>

        <div class="error" id="errorMsg"></div>
    </div>

    <script>
        let isProcessing = false;

        function getLocation() {
            if (isProcessing) return;

            const btn = document.getElementById('locationBtn');
            const btnText = document.getElementById('btnText');
            const spinner = document.getElementById('spinner');
            const successMsg = document.getElementById('successMsg');
            const errorMsg = document.getElementById('errorMsg');

            // Reset messages
            successMsg.style.display = 'none';
            errorMsg.style.display = 'none';

            if (navigator.geolocation) {
                isProcessing = true;
                btn.disabled = true;
                btnText.textContent = '正在取得位置...';
                spinner.style.display = 'inline-block';

                navigator.geolocation.getCurrentPosition(sendPosition, showError, {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 300000
                });
            } else {
                showMessage("瀏覽器不支援定位功能", 'error');
            }
        }

        function sendPosition(position) {
            fetch('/submit', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    session_id: '{{ sid }}',
                    lat: position.coords.latitude,
                    lon: position.coords.longitude
                })
            }).then(response => {
                if (response.ok) {
                    showMessage("定位已成功傳送！您可以返回 Telegram 了", 'success');
                    setTimeout(() => {
                        window.close();
                    }, 2000);
                } else {
                    throw new Error('服務器回應錯誤');
                }
            }).catch(err => {
                showMessage("傳送定位失敗: " + err.message, 'error');
            }).finally(() => {
                resetButton();
            });
        }

        function showError(error) {
            let message = "定位失敗，請確認開啟 GPS 權限";

            switch(error.code) {
                case error.PERMISSION_DENIED:
                    message = "❌ 使用者拒絕了定位請求，請在瀏覽器設定中允許位置存取。 若您正在使用Telegram內部瀏覽器，請嘗試在外部瀏覽器中打開此頁面。";
                    break;
                case error.POSITION_UNAVAILABLE:
                    message = "❌ 位置資訊無法取得，請確認 GPS 已開啟";
                    break;
                case error.TIMEOUT:
                    message = "⏱️ 定位請求逾時，請重新嘗試";
                    break;
                case error.UNKNOWN_ERROR:
                    message = "❌ 發生未知錯誤，請重新嘗試";
                    break;
            }

            showMessage(message, 'error');
            resetButton();
        }

        function showMessage(message, type) {
            const successMsg = document.getElementById('successMsg');
            const errorMsg = document.getElementById('errorMsg');

            if (type === 'success') {
                successMsg.textContent = message;
                successMsg.style.display = 'block';
                errorMsg.style.display = 'none';
            } else {
                errorMsg.textContent = message;
                errorMsg.style.display = 'block';
                successMsg.style.display = 'none';
            }
        }

        function resetButton() {
            const btn = document.getElementById('locationBtn');
            const btnText = document.getElementById('btnText');
            const spinner = document.getElementById('spinner');

            isProcessing = false;
            btn.disabled = false;
            btnText.textContent = '📍 傳送定位';
            spinner.style.display = 'none';
        }

        // Add some interactivity on page load
        window.addEventListener('load', function() {
            document.querySelector('.container').style.opacity = '0';
            document.querySelector('.container').style.transform = 'translateY(20px)';

            setTimeout(() => {
                document.querySelector('.container').style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                document.querySelector('.container').style.opacity = '1';
                document.querySelector('.container').style.transform = 'translateY(0)';
            }, 100);
        });
    </script>
</body>
</html>
'''


@flask_app.route("/gps/<sid>")
def gps_page(sid):
    return render_template_string(HTML_TEMPLATE, sid=sid)

@flask_app.route("/submit", methods=["POST"])
def gps_submit():
    try:
        data = request.get_json()
        if not all(k in data for k in ["session_id", "lat", "lon"]):
            return "Invalid data", 400

        gps_sessions[data["session_id"]] = {
            "lat": data["lat"],
            "lon": data["lon"],
            "timestamp": datetime.now(),
            "done": True
        }
        return "ok"
    except Exception as e:
        print(f"[Flask Error] /submit failed: {e}")
        return "Internal server error", 500


def run_flask():
    # FIX: 關閉 Flask 的除錯模式，在生產環境中更安全
    flask_app.run(host="0.0.0.0", port=5005, debug=False)

# 啟動 Flask 在背景執行
threading.Thread(target=run_flask, daemon=True).start()


# ========== Telegram 機器人部分 ==========

def load_users():
    """從 users.csv 讀取使用者資料，若不存在就建立。"""
    global users
    users = {}
    if not os.path.exists(USERS_CSV_FILE):
        header = ["username", "name", "lat", "lon", "address", "role", "user_id"]
        ensure_csv_header(USERS_CSV_FILE, header)
        return

    try:
        with open(USERS_CSV_FILE, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uname = row["username"].strip().lower()
                if not uname:
                    continue
                try:
                    lat = float(row.get("lat", 0))
                    lon = float(row.get("lon", 0))
                except (ValueError, TypeError):
                    lat, lon = 0.0, 0.0

                user_id = int(row["user_id"]) if row.get("user_id", "").isdigit() else None

                users[uname] = {
                    "name": row.get("name", ""), "lat": lat, "lon": lon,
                    "address": row.get("address", "未知"),
                    "role": row.get("role", "employee").strip().lower(),
                    "user_id": user_id,
                    "checkin_full": None, "checkout_full": None # FIX: 移除 checkin/checkout，只用 full datetime 物件
                }
    except Exception as e:
        print(f"[Error] Failed to load users.csv: {e}")


def save_users_to_csv():
    """將 users dict 回寫到 users.csv。"""
    global users
    fieldnames = ["username", "name", "lat", "lon", "address", "role", "user_id"]
    try:
        with open(USERS_CSV_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for uname, udata in users.items():
                writer.writerow({
                    "username": uname,
                    "name": udata.get("name", ""),
                    "lat": udata.get("lat", ""),
                    "lon": udata.get("lon", ""),
                    "address": udata.get("address", ""),
                    "role": udata.get("role", "employee"),
                    "user_id": udata.get("user_id", "")
                })
    except Exception as e:
        print(f"[Error] Failed to save users.csv: {e}")

# FIX: 新增函式，在啟動時從 log 檔恢復今日打卡狀態
def restore_today_status():
    """從 attendance_log.csv 讀取今日紀錄，恢復 users dict 中的狀態。"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(ATTENDANCE_CSV):
        return
    try:
        with open(ATTENDANCE_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["date"] == today_str:
                    uname = row["username"]
                    if uname in users:
                        timestamp = datetime.fromisoformat(row["timestamp"])
                        if row["type"] == "in":
                            users[uname]["checkin_full"] = timestamp
                        elif row["type"] == "out":
                            users[uname]["checkout_full"] = timestamp
        print("[Info] Today's attendance status restored from log.")
    except Exception as e:
        print(f"[Error] Failed to restore today's status: {e}")

def haversine(lat1, lon1, lat2, lon2):
    """計算兩點之間的距離（公尺）。"""
    R = 6371000
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    return 2 * R * asin(sqrt(a))

def get_address(lat, lon):
    if not Maps_API_KEY or "YOUR_Maps_API_KEY" in Maps_API_KEY:
        return "無法取得地址 (API金鑰未設定)"

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "latlng": f"{lat},{lon}",
        "key": Maps_API_KEY,
        "language": "zh-TW"
    }
    try:
        res = requests.get(url, params=params, timeout=10)    # ← 這裡加上 params
        res.raise_for_status()
        data = res.json()
        if data["status"] == "OK" and data["results"]:
            return data["results"][0]["formatted_address"]
        else:
            return f"無法取得地址 (API錯誤: {data.get('status', 'Unknown')})"
    except requests.RequestException as e:
        print(f"[API Error] Geocoding request failed: {e}")
        return "無法取得地址 (請求失敗)"



# ==== Telegram /start 指令 ====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not user.username:
        await update.message.reply_text("⚠️ 請先在 Telegram 設定您的 @username。")
        return

    uname = user.username.lower()
    if uname not in users:
        await update.message.reply_text(f"⚠️ @{user.username} 未被授權使用此機器人，請聯繫管理員。")
        return

    # 若 user_id 尚未寫入，就寫一次回 CSV
    if users[uname].get("user_id") != user.id:
        users[uname]["user_id"] = user.id
        save_users_to_csv()

    keyboard = [["🟢 上班打卡", "🔴 下班打卡"], ["📝 申請休假"]]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text(f"你好，{users[uname]['name']}！請選擇操作：", reply_markup=markup)


# ==== 定時工作 ====
async def reset_daily_status(context: ContextTypes.DEFAULT_TYPE):
    """每日凌晨重置所有使用者的打卡狀態"""
    for uname in users:
        users[uname]["checkin_full"] = None
        users[uname]["checkout_full"] = None
    print("[Job] Daily user status has been reset.")

async def send_late_checkout_reminder(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().date()
    for uname, udata in users.items():
        if udata.get("role") not in ["employee", "supervisor"]:
            continue
        emp_id = udata.get("user_id")
        if not emp_id:
            continue

        # FIX: 使用 checkin_full 和 checkout_full 進行判斷
        if udata.get("checkin_full") and not udata.get("checkout_full"):
            if udata["checkin_full"].date() == today:
                try:
                    await context.bot.send_message(chat_id=emp_id, text="🕒 提醒：您今天似乎還沒下班打卡喔！請記得打卡。😊")
                except Exception as e:
                    print(f"[Reminder Error] Failed to send reminder to {uname}: {e}")

async def check_overnight_checkout_and_notify(context: ContextTypes.DEFAULT_TYPE):
    yesterday = (datetime.now() - timedelta(days=1)).date()
    for uname, udata in users.items():
        if udata.get("role") not in ["employee", "supervisor"]:
            continue
        emp_id = udata.get("user_id")
        if not emp_id:
            continue

        if udata.get("checkin_full") and udata["checkin_full"].date() == yesterday and not udata.get("checkout_full"):
            text_emp = f"⚠️ 您昨日 ({yesterday.strftime('%Y-%m-%d')}) 似乎忘記下班打卡。請盡快聯繫您的直屬主管說明情況。😔"
            text_grp = f"📢 通知：員工 {udata.get('name')} (@{uname}) 昨日 ({yesterday.strftime('%Y-%m-%d')}) 未下班打卡。請群組處理。"
            try:
                await context.bot.send_message(chat_id=emp_id, text=text_emp)
                await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=text_grp)
            except Exception as e:
                print(f"[Overnight Check Error] Failed to send notification for {uname}: {e}")

# ==== 處理打卡按鈕 ====
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not user.username:
        await update.message.reply_text("⚠️ 您的帳號未被授權或尚未設定 @username。")
        return

    uname = user.username.lower()
    if uname not in users:
        await update.message.reply_text("⚠️ 您尚未在系統中註冊，請聯絡管理員。")
        return

    # --- 假日檢查 ---
    today = datetime.now()
    holiday_url = f"https://api.pin-yi.me/taiwan-calendar/{today.year}/{today.month}/{today.day}"
    try:
        res = requests.get(holiday_url, timeout=5)
        res.raise_for_status()
        data = res.json()
        entry = data[0] if isinstance(data, list) and data else data
        if entry.get("isHoliday"):
            await update.message.reply_text("❌ 今天是假日，無需打卡。")
            #return # FIX: 嚴格執行，假日直接返回
    except requests.RequestException as e:
        print(f"[Warning] Holiday API call failed: {e}. Proceeding with clock-in.")

    action = update.message.text.strip()
    profile = users[uname]

    if "上班" in action:
        if profile.get("checkin_full"):
            await update.message.reply_text("❌ 您今天已經完成「上班打卡」，不可重複操作。")
            return


    elif "下班" in action:
        if not profile.get("checkin_full"):
            await update.message.reply_text("❌ 您尚未完成「上班打卡」，無法執行下班打卡。")
            return
        if profile.get("checkout_full"):
            await update.message.reply_text("❌ 您今天已經完成「下班打卡」，不可重複操作。")
            return

    session_id = ''.join(random.choices(string.ascii_letters + string.digits, k=20))
    check_type = "in" if "上班" in action else "out"
    active_session[session_id] = {"uname": uname, "type": check_type, "chat_id": update.effective_chat.id}

    url = f"{WEBHOOK_URL}/gps/{session_id}"
    await update.message.reply_text(
        f"📛 員工姓名：{users[uname]['name']}\n"
        f"請點擊以下連結授權 GPS 定位：\n{url}\n\n"
        f"📍 成功後將自動回報打卡。"
    )

    async def wait_for_gps_then_report():
        for _ in range(60): # 等待 60 秒
            if gps_sessions.get(session_id, {}).get("done"):
                session_data = gps_sessions.pop(session_id)
                await report_checkin(uname, session_data, check_type, context)
                active_session.pop(session_id, None)
                return
            await asyncio.sleep(1)

        orig_chat_id = active_session.pop(session_id, {}).get("chat_id")
        if orig_chat_id:
            await context.bot.send_message(chat_id=orig_chat_id, text="⏰ 定位逾時，請重新嘗試打卡。")
        gps_sessions.pop(session_id, None)

    asyncio.create_task(wait_for_gps_then_report())


async def report_checkin(uname, session_details, mode, context: ContextTypes.DEFAULT_TYPE):
    """當收到 GPS 後，執行實際的打卡報告與檔案寫入。"""
    user_profile = users[uname]
    lat, lon = session_details["lat"], session_details["lon"]
    now = session_details["timestamp"]
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    dist = int(haversine(lat, lon, user_profile["lat"], user_profile["lon"]))
    actual_addr = get_address(lat, lon)

    t_now = now.time()
    t_start = time.fromisoformat(WORK_HOURS["start"])
    t_end = time.fromisoformat(WORK_HOURS["end"])

    msg_lines = [
        f"✅ 打卡成功！",
        f"👤 使用者：@{uname} ({user_profile['name']})",
        f"📍 打卡位置：{actual_addr}",
        f"📏 與登記距離差距：約 {dist} 公尺",
        f"🕒 打卡時間：{now_str}"
    ]

    status = ""
    if mode == "in":
        user_profile["checkin_full"] = now
        status = "✔️ 正常上班" if t_now <= t_start else f"❗遲到 (應於 {WORK_HOURS['start']})"
        msg_lines.append(f"☑️ 上班狀態：{status}")
        forwarding_users[uname] = True
    else: # mode == "out"
        user_profile["checkout_full"] = now
        status = "✔️ 正常下班" if t_now >= t_end else f"❗早退 (應於 {WORK_HOURS['end']})"
        msg_lines.append(f"☑️ 下班狀態：{status}")

        if user_profile.get("checkin_full"):
            checkin_time = user_profile["checkin_full"].time()
            is_late = checkin_time > t_start
            is_early_leave = t_now < t_end

            summary = "✔️ 正常出勤"
            if is_late and is_early_leave: summary = "❌ 遲到且早退"
            elif is_late: summary = "⚠️ 遲到但正常下班"
            elif is_early_leave: summary = "⚠️ 正常上班但早退"

            msg_lines.append(f"📉 本日統計：{summary}")
            msg_lines.append(f"🕘 上班：{user_profile['checkin_full'].strftime('%H:%M:%S')}")
            msg_lines.append(f"🕕 下班：{now.strftime('%H:%M:%S')}")
        else:
            msg_lines.append("⚠️ 今日無上班打卡記錄")

        forwarding_users.pop(uname, None)

    final_msg = "\n".join(msg_lines)

    try:
        #if GROUP_CHAT_ID:
            #await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"【打卡通知】\n{final_msg}")
        if user_profile.get("user_id"):
            await context.bot.send_message(chat_id=user_profile["user_id"], text=final_msg)
    except Exception as e:
        print(f"[Report Error] Failed to send check-in message for {uname}: {e}")

    # 寫入 attendance_log.csv
    ensure_attendance_csv()
    try:
        with open(ATTENDANCE_CSV, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                uname, user_profile["name"], now.strftime("%Y-%m-%d"),
                mode, now_str, actual_addr, dist, status
            ])
    except Exception as e:
        print(f"[CSV Error] Failed to write to attendance_log.csv: {e}")


# ==== 處理員工筆記轉發 ====
async def handle_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not user.username: return

    uname = user.username.lower()
    # 只有在 forwarding_users 列表中的使用者才轉發
    if uname in forwarding_users and GROUP_CHAT_ID:
        try:
            await context.bot.forward_message(
                chat_id=GROUP_CHAT_ID,
                from_chat_id=update.message.chat_id,
                message_id=update.message.message_id
            )
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"✉️ 來自 {users[uname]['name']} 的筆記"
            )
        except Exception as e:
            print(f"[Forward Error] Failed to forward note from {uname}: {e}")


# ==== 請假申請流程 ====
async def start_leave_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not user.username:
        await update.message.reply_text("⚠️ 請先在 Telegram 設定您的 @username。")
        return

    uname = user.username.lower()
    if uname not in users:
        await update.message.reply_text("⚠️ 您尚未註冊。")
        return

    if context.user_data.get("await_leave_reason"):
        await update.message.reply_text("您已有一則請假申請正在處理中。")
        return

    await update.message.reply_text(
        "📝 請輸入請假原因 (例如：事假，2025/06/10 全天)。\n"
        "您稍後可以補充附件(照片/檔案)。"
    )
    context.user_data["await_leave_reason"] = True

async def handle_leave_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("await_leave_reason"): return
    if not update.message or not update.message.text or update.message.text.startswith("/"): return

    context.user_data["await_leave_reason"] = False
    leave_reason = update.message.text
    user = update.effective_user
    uname = user.username.lower()

    leave_request_id = f"leave_{uname}_{int(datetime.now().timestamp())}"
    pending_leave[leave_request_id] = {
        "employee_uname": uname, "employee_name": users[uname]["name"],
        "employee_user_id": user.id, "reason": leave_reason,
        "attachments": [], "group_message_id": None, "status": "pending"
    }
    context.user_data["current_leave_request_id"] = leave_request_id

    # 寫入 CSV
    ensure_leave_csv()
    try:
        with open(LEAVE_CSV, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                leave_request_id, uname, users[uname]["name"], leave_reason,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "pending",
                "", "", "", ""
            ])
    except Exception as e:
        print(f"[CSV Error] Failed to write initial leave request: {e}")

    keyboard = [[
        InlineKeyboardButton("✅ 同意", callback_data=f"approve_{leave_request_id}"),
        InlineKeyboardButton("❌ 否決", callback_data=f"deny_{leave_request_id}")
    ]]
    markup = InlineKeyboardMarkup(keyboard)

    if GROUP_CHAT_ID:
        try:
            group_msg = await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=(
                    f"📢 休假申請通知 📢\n\n"
                    f"👤 員工：{users[uname]['name']} (@{uname})\n"
                    f"📝 事由：{leave_reason}\n\n"
                    f"請審核："
                ),
                reply_markup=markup
            )
            pending_leave[leave_request_id]["group_message_id"] = group_msg.message_id
            await update.message.reply_text("✅ 您的請假申請已送出，等待審核。若需補充證明，請直接傳送照片或檔案。")
        except Exception as e:
            await update.message.reply_text("⚠️ 您的請假申請無法送出，請聯絡管理員。")
            print(f"[Leave Error] Failed to send leave request to group: {e}")
            pending_leave.pop(leave_request_id, None)
            context.user_data.pop("current_leave_request_id", None)

async def handle_attachments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("current_leave_request_id"): return
    leave_request_id = context.user_data["current_leave_request_id"]
    if leave_request_id not in pending_leave: return

    file_id, attach_type = None, None
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        attach_type = "照片"
    elif update.message.document:
        file_id = update.message.document.file_id
        attach_type = "文件"

    if not file_id: return

    # 轉發附件到群組
    leave_info = pending_leave[leave_request_id]
    caption = f"📎 附件更新：來自 {leave_info['employee_name']} 的請假申請 (事由: {leave_info['reason'][:30]}...)"
    try:
        if attach_type == "照片":
            await context.bot.send_photo(chat_id=GROUP_CHAT_ID, photo=file_id, caption=caption)
        else:
            await context.bot.send_document(chat_id=GROUP_CHAT_ID, document=file_id, caption=caption)
        await update.message.reply_text(f"📎 {attach_type}附件已補充給審核群組。")
    except Exception as e:
        await update.message.reply_text(f"⚠️ 附件無法傳送給群組。")
        print(f"[Attachment Error] Failed to forward attachment: {e}")

# FIX: 重構並簡化 CSV 更新邏輯
def update_leave_csv_record(request_id, updates):
    """通用函式：讀取、更新、並寫回 leave_requests.csv 的特定紀錄"""
    try:
        with open(LEAVE_CSV, "r", encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))

        header = rows[0]
        col_map = {name: i for i, name in enumerate(header)}

        # 找到要更新的行
        for i, row in enumerate(rows):
            if i > 0 and row[col_map["request_id"]] == request_id:
                for key, value in updates.items():
                    if key in col_map:
                        row[col_map[key]] = value
                break

        with open(LEAVE_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        return True
    except Exception as e:
        print(f"[CSV Error] Failed to update leave record {request_id}: {e}")
        return False


async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, leave_request_id = query.data.split("_", 1)
    if leave_request_id not in pending_leave:
        await query.edit_message_text(text="⚠️ 此休假申請已不存在或已被處理。")
        return

    leave_info = pending_leave[leave_request_id]
    approver = query.from_user.username or query.from_user.first_name

    if action == "approve":
        # 1. 通知員工
        await context.bot.send_message(
            chat_id=leave_info["employee_user_id"],
            text=f"✅ 您的請假申請 (事由：{leave_info['reason']}) 已被 @{approver} 同意。"
        )
        # 2. 編輯群組訊息
        await query.edit_message_text(
            text=f"✅ 已同意 {leave_info['employee_name']} 的休假申請。\n事由：{leave_info['reason']}\n(由 @{approver} 處理)",
            reply_markup=None
        )
        # 3. 更新 CSV
        updates = {"status": "approved", "approver": approver, "decision_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        update_leave_csv_record(leave_request_id, updates)
        # 4. 清理
        pending_leave.pop(leave_request_id, None)

    elif action == "deny":
        context.user_data["denying_leave_request_id"] = leave_request_id
        prompt = await query.message.reply_text(f"📝 請回覆此訊息以輸入否決 {leave_info['employee_name']} 休假申請的原因。")
        context.user_data["deny_reason_prompt_id"] = prompt.message_id
        context.user_data["denier_username"] = approver

async def handle_deny_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("denying_leave_request_id"): return

    prompt_id = context.user_data.get("deny_reason_prompt_id")
    if not (update.message.reply_to_message and update.message.reply_to_message.message_id == prompt_id): return

    leave_request_id = context.user_data["denying_leave_request_id"]
    leave_info = pending_leave.get(leave_request_id)
    if not leave_info:
        await update.message.reply_text("⚠️ 原休假申請已不存在。")
        return

    deny_reason = update.message.text
    denier = context.user_data["denier_username"]

    # 1. 通知員工
    await context.bot.send_message(
        chat_id=leave_info["employee_user_id"],
        text=f"❌ 您的請假申請 (事由：{leave_info['reason']}) 已被 @{denier} 否決。\n否決原因：{deny_reason}"
    )
    # 2. 編輯群組原始訊息
    await context.bot.edit_message_text(
        chat_id=GROUP_CHAT_ID, message_id=leave_info["group_message_id"],
        text=f"❌ 已否決 {leave_info['employee_name']} 的休假申請。\n事由：{leave_info['reason']}\n否決原因：{deny_reason}\n(由 @{denier} 處理)",
        reply_markup=None
    )
    # 3. 更新 CSV
    updates = {
        "status": "denied", "approver": denier,
        "decision_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "deny_reason": deny_reason
    }
    update_leave_csv_record(leave_request_id, updates)

    # 4. 清理
    await update.message.reply_to_message.delete() # 刪除 "請輸入原因" 的提示
    await update.message.reply_text("否決原因已發送給員工。")
    pending_leave.pop(leave_request_id, None)
    for key in ["denying_leave_request_id", "deny_reason_prompt_id", "denier_username"]:
        context.user_data.pop(key, None)


# ==== 管理員指令 ====

# FIX: Add a helper function to escape characters for MarkdownV2
def escape_markdown(text: str) -> str:
    """Escapes special characters for Telegram's MarkdownV2 parse mode."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

async def supervisor_command(update: Update, context: ContextTypes.DEFAULT_TYPE, command_func):
    """裝飾器/包裝函式，檢查使用者是否為 supervisor"""
    user = update.effective_user
    if not user or not user.username:
        await update.message.reply_text("⚠️ 請先設定您的 @username。")
        return

    uname = user.username.lower()
    if users.get(uname, {}).get("role") != "supervisor":
        await update.message.reply_text("❌ 您沒有權限執行此指令。")
        return

    await command_func(update, context)

async def _todaystat_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today_str = datetime.now().strftime("%Y-%m-%d")
    target_uname = context.args[0].lower() if context.args else None

    records = []
    if os.path.exists(ATTENDANCE_CSV):
        with open(ATTENDANCE_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["date"] == today_str:
                    if not target_uname or row["username"] == target_uname:
                        records.append(row)

    if not records:
        msg = f"❌ {escape_markdown(today_str)} 尚無任何打卡紀錄。"
        if target_uname: msg = f"❌ 找不到使用者 @{escape_markdown(target_uname)} 在 {escape_markdown(today_str)} 的打卡紀錄。"
        await update.message.reply_text(msg, parse_mode="MarkdownV2")
        return

    stat_map = {}
    for row in records:
        uname_r = row["username"]
        if uname_r not in stat_map:
            stat_map[uname_r] = {"name": row["name"], "in": "—", "out": "—"}

        ts = row["timestamp"].split(" ")[1]
        if row["type"] == "in": stat_map[uname_r]["in"] = ts
        elif row["type"] == "out": stat_map[uname_r]["out"] = ts

    # FIX: Escape the date in the title
    escaped_today = escape_markdown(today_str)
    msg_lines = [f"📅 *{escaped_today} 打卡統計*"]
    # FIX: Using code blocks (`) for the table content avoids needing to escape most characters inside.
    msg_lines.append("`使用者          | 上班時間 | 下班時間`")
    msg_lines.append("`----------------+----------+----------`")
    for uname_r, info in sorted(stat_map.items()):
        # Ensure username column has fixed width for alignment
        user_part = f"@{uname_r:<15}"
        time_part = f" | {info['in']:<8} | {info['out']:<8}"
        msg_lines.append(f"`{user_part}{time_part}`")

    await update.message.reply_text("\n".join(msg_lines), parse_mode="MarkdownV2")


async def _monthstat_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prefix = datetime.now().strftime("%Y-%m")
    target_uname = context.args[0].lower() if context.args else None

    records = []
    if os.path.exists(ATTENDANCE_CSV):
        with open(ATTENDANCE_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["date"].startswith(prefix):
                    if not target_uname or row["username"] == target_uname:
                        records.append(row)

    if not records:
        escaped_prefix = escape_markdown(prefix)
        msg = f"❌ {escaped_prefix} 尚無任何打卡紀錄。"
        if target_uname:
            msg = f"❌ 找不到使用者 `@{escape_markdown(target_uname)}` 在 {escaped_prefix} 的打卡紀錄。"
        await update.message.reply_text(msg, parse_mode="MarkdownV2")
        return

    stat_month = {}
    for row in records:
        uname_r, day = row["username"], row["date"].split("-")[2]
        if uname_r not in stat_month: stat_month[uname_r] = {"name": row["name"], "days": {}}
        if day not in stat_month[uname_r]["days"]: stat_month[uname_r]["days"][day] = {"in": "—", "out": "—"}

        ts = row["timestamp"].split(" ")[1]
        if row["type"] == "in": stat_month[uname_r]["days"][day]["in"] = ts
        elif row["type"] == "out": stat_month[uname_r]["days"][day]["out"] = ts

    escaped_prefix = escape_markdown(prefix)
    title_target = f" for `@{escape_markdown(target_uname)}`" if target_uname else ""
    msg_lines = [f"📅 *{escaped_prefix} 月度打卡統計*{title_target}"]

    for uname_r, info in sorted(stat_month.items()):
        # FIX: Construct the header line first, then escape the ENTIRE line.
        # This correctly handles '─', '@', '(', and ')' characters.
        header_line = f"\n── @{uname_r} ({info['name']}) ──"
        msg_lines.append(escape_markdown(header_line))

        for day in sorted(info["days"].keys()):
            rec = info["days"][day]
            in_t = escape_markdown(rec["in"])
            out_t = escape_markdown(rec["out"])
            msg_lines.append(f"{escape_markdown(day)}日: 上班 {in_t}, 下班 {out_t}")

    full_msg = "\n".join(msg_lines)

    if len(full_msg) > 4096:
        await update.message.reply_text("資料過多，無法完整顯示。")
    else:
        await update.message.reply_text(full_msg, parse_mode="MarkdownV2")


async def _msg_to_employee_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ 用法：/msg [username] [訊息文字]")
        return

    target_uname = context.args[0].lower()
    if target_uname not in users or not users[target_uname].get("user_id"):
        await update.message.reply_text(f"❌ 找不到員工 @{escape_markdown(target_uname)} 或該員工尚未啟用 Bot。", parse_mode="MarkdownV2")
        return

    message_text = " ".join(context.args[1:])
    sender_uname = update.effective_user.username.lower()
    sender_display = users[sender_uname].get("name", f"@{sender_uname}")

    # FIX: Escape all dynamic text to prevent errors
    escaped_sender = escape_markdown(sender_display)
    escaped_message = escape_markdown(message_text)

    full_message = f"📨 來自 *{escaped_sender}* 的訊息:\n\n{escaped_message}"

    try:
        await context.bot.send_message(chat_id=users[target_uname]["user_id"], text=full_message, parse_mode="MarkdownV2")
        await update.message.reply_text(f"✅ 已成功私訊 @{escape_markdown(target_uname)}。", parse_mode="MarkdownV2")
    except Exception as e:
        await update.message.reply_text(f"❌ 私訊失敗：{e}")


# ==== Bot 啟動主函式 ====
def main() -> None:
    # 初始化
    load_users()
    ensure_attendance_csv()
    ensure_leave_csv()
    restore_today_status()

    # 建立 Application
    application = Application.builder().token(BOT_TOKEN).build()

    # 指令處理
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("leave", start_leave_request))
    application.add_handler(CommandHandler("todaystat", lambda u, c: supervisor_command(u, c, _todaystat_impl)))
    application.add_handler(CommandHandler("monthstat", lambda u, c: supervisor_command(u, c, _monthstat_impl)))
    application.add_handler(CommandHandler("msg", lambda u, c: supervisor_command(u, c, _msg_to_employee_impl)))

    # 按鈕與訊息處理 (順序很重要)
    # 1. 處理 Inline Keyboard 回調 (最高優先級)
    application.add_handler(CallbackQueryHandler(handle_approval, pattern="^(approve_|deny_).+"))

    # 2. 處理固定回覆按鈕
    application.add_handler(MessageHandler(filters.Regex(r"^📝 申請休假$"), start_leave_request))
    application.add_handler(MessageHandler(filters.Regex(r"^(🟢 上班打卡|🔴 下班打卡)$"), handle_button))

    # 3. 處理需要 context 的特定訊息 (例如回覆)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.REPLY, handle_deny_reason
    ))

    # 4. 處理附件 (照片/文件)
    application.add_handler(MessageHandler(
        (filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, handle_attachments
    ))

    # 5. 處理一般文字訊息，根據 context 判斷意圖
    # FIX: 將筆記轉發和請假原因處理整合到一個 handler 中，根據 context 決定行為
    async def general_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get("await_leave_reason"):
            await handle_leave_text(update, context)
        else:
            await handle_notes(update, context)

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, general_text_handler))

    # 定時任務
    from datetime import datetime, time
    from pytz import timezone

    tz = timezone("Asia/Taipei")  # 明確指定台灣時區

    # 每日 00:01 重置打卡狀態
    application.job_queue.run_daily(
        reset_daily_status,
        time=time(hour=0, minute=1, tzinfo=tz),
        name="daily_status_reset"
    )

    # 每日 18:45 提醒未下班者
    application.job_queue.run_daily(
        send_late_checkout_reminder,
        time=time(hour=18, minute=45, tzinfo=tz),
        name="late_checkout_reminder"
    )

    # 每日上班時間檢查是否有人未退勤（以 WORK_HOURS["start"] 為基準）
    h, m = map(int, WORK_HOURS["start"].split(":"))
    application.job_queue.run_daily(
        check_overnight_checkout_and_notify,
        time=time(hour=h, minute=m, tzinfo=tz),
        name="overnight_checkout_check"
    )

    # 啟動 Bot
    print("[Info] Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    if not all([BOT_TOKEN, Maps_API_KEY, WEBHOOK_URL, GROUP_CHAT_ID]):
        print("[Fatal] One or more required environment variables (BOT_TOKEN, MAPS_API_KEY, WEBHOOK_URL, GROUP_CHAT_ID) are missing.")
    else:
        main()
