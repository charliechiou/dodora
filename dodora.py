import requests
import datetime
import urllib3
from dotenv import load_dotenv
import json
import os
import re
import warnings
import ollama  # 替換 google.genai
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()

# 忽略警告與 SSL 檢查
warnings.filterwarnings("ignore", category=DeprecationWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# --- 設定區 ---
LINE_ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
CWA_API_KEY = os.getenv('CWA_API_KEY')
USER_ME = os.getenv('USER_ME')
USER_PARTNER = os.getenv('USER_PARTNER')
MAILBOX_FILE = "mailbox.json"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 信箱輔助函數 ---


def load_mailbox():
    if os.path.exists(MAILBOX_FILE):
        try:
            with open(MAILBOX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:  # 處理檔案格式錯誤
            return {USER_ME: [], USER_PARTNER: []}
    return {USER_ME: [], USER_PARTNER: []}


def save_mailbox(data):
    with open(MAILBOX_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# --- 天氣抓取函數 ---
# --- 設定您的溫度體感門檻 (可隨時調整) ---
VERY_COLD_TEMP = 15  # 低於 15 度：極冷
COLD_TEMP = 20       # 15 ~ 20 度：偏冷
HOT_TEMP = 25        # 26 ~ 32 度：偏熱 (假設 20-26 為舒適)
VERY_HOT_TEMP = 25   # 高於 25 度：極熱


def get_tainan_weather():
    """ 抓取氣象並回傳結構化資料 """
    url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"
    params = {"Authorization": CWA_API_KEY, "locationName": "臺南市",
              "elementName": ["Wx", "MaxT", "MinT", "PoP"]}
    try:
        response = requests.get(url, params=params, verify=False)
        data = response.json()
        location_data = data['records']['location'][0]
        elements = location_data['weatherElement']

        # 建立一個字典來存資料
        weather = {}
        for el in elements:
            name = el['elementName']
            value = el['time'][0]['parameter']['parameterName']
            weather[name] = value  # 存入如 {'MinT': '18', 'MaxT': '24', ...}

        return weather
    except Exception:
        return None


def get_feeling_label(weather_data):
    """ 根據四個門檻產出五種等級的體感標籤 """
    if not weather_data:
        return "未知"

    min_t = int(weather_data['MinT'])
    max_t = int(weather_data['MaxT'])
    pop = int(weather_data['PoP'])

    # 五段式冷熱判斷邏輯
    if min_t <= VERY_COLD_TEMP:
        feeling = "寒冷刺骨 (建議穿發熱衣加厚大衣)"
    elif min_t <= COLD_TEMP:
        feeling = "有些涼意 (建議穿長袖加薄外套)"
    elif max_t >= VERY_HOT_TEMP:
        feeling = "極度酷熱 (建議穿最涼爽衣物，嚴防中暑)"
    elif max_t >= HOT_TEMP:
        feeling = "有些悶熱 (建議穿透氣短袖，注意防曬)"
    else:
        feeling = "舒適涼爽 (穿著輕便舒適即可)"

    # 降雨提醒邏輯依舊維持
    rain_alert = "記得帶傘唷" if pop >= 30 else "不必帶傘"

    return f"體感：{feeling}，雨具：{rain_alert}"


def process_weather_ollama(w_data):
    """ 統一處理天氣數據並透過 Ollama 生成文字 """
    if not w_data:
        return "氣象局好像在忙碌中，晚點再問我唷！"

    feeling = get_feeling_label(w_data)
    pop_val = int(w_data.get('PoP', 0))

    # --- 完全隔離指令邏輯 ---
    if pop_val >= 30:
        umbrella_instruction = f"目前降雨機率為 {pop_val}%，請務必提醒出門『記得帶傘』。"
    else:
        umbrella_instruction = f"目前降雨機率為 {pop_val}%"

    # 組合與查詢功能一致的 Prompt
    prompt = (
        f"台南目前氣溫：{w_data['MinT']}~{w_data['MaxT']}度。\n"
        f"體感標籤：{feeling}。\n"
        f"{umbrella_instruction}\n"
        f"請以『多多拉』的身分提醒氣溫範圍及降雨機率。"
    )

    try:
        response = ollama.chat(
            model='gemma2:2b',
            messages=[
                {'role': 'system', 'content': '你名叫多多拉，語氣親切。請根據資訊給予建議。'},
                {'role': 'user', 'content': prompt},
            ],
            options={'temperature': 0.3}
        )
        raw_text = response['message']['content'].strip()
        # 移除換行符號，保持單一段落
        reply_text = raw_text.replace("\n", " ").replace("\r", " ").strip()
        reply_text = re.sub(r'\s+', ' ', reply_text)
        return reply_text
    except Exception as e:
        print(f"Ollama 生成失敗: {e}")
        return f"目前台南 {w_data['MinT']}~{w_data['MaxT']}度，多多拉覺得很{feeling}唷！"

# ==================== 地震監測 ====================


def check_earthquake():
    """ 每分鐘檢查一次地震 API """
    global LAST_EARTHQUAKE_NO
    url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001"
    params = {
        "Authorization": CWA_API_KEY,
        "limit": 1,  # 只取最新的一筆
        "format": "JSON"
    }

    try:
        # 由於這是在背景執行，不驗證 SSL 以確保連線穩定
        response = requests.get(url, params=params, verify=False)
        data = response.json()

        # 取得最新一筆地震報告
        eq_record = data['records']['Earthquake'][0]
        eq_no = eq_record['EarthquakeNo']

        # 如果是新的地震編號，才進行判斷
        if eq_no != LAST_EARTHQUAKE_NO:
            LAST_EARTHQUAKE_NO = eq_no

            info = eq_record['EarthquakeInfo']
            mag = float(info['EarthquakeMagnitude']['MagnitudeValue'])  # 規模

            # 尋找臺南市的震度資訊
            tainan_intensity = "無"
            shaking_areas = eq_record['Intensity']['ShakingArea']
            for area in shaking_areas:
                if area['CountyName'] == "臺南市":
                    tainan_intensity = area['AreaIntensity']
                    break

            # 推播標準：規模 >= 3.0 或 臺南市有震度
            if mag >= 3.0 or tainan_intensity != "無":
                msg = (
                    f"⚠️ 地震速報 (編號:{eq_no}) ⚠️\n"
                    f"剛才有地震！多多拉感覺到了唷！\n"
                    f"--------------------\n"
                    f"● 地震規模：{mag}\n"
                    f"● 臺南震度：{tainan_intensity}\n"
                    f"--------------------\n"
                    f"還好嗎？要注意安全唷！💕"
                )

                # 同時推播給兩個人
                line_bot_api.push_message(USER_ME, TextSendMessage(text=msg))
                line_bot_api.push_message(
                    USER_PARTNER, TextSendMessage(text=msg))

    except Exception as e:
        print(f"地震監測發生錯誤：{e}")

# ==================== 3. 每日廣播任務 (改用 Ollama) ====================


def send_weather_update(time_of_day):
    """ 每日定時廣播 """
    w_data = get_tainan_weather()
    # 呼叫統一處理函數
    advice = process_weather_ollama(w_data)

    prefix = "✨ 多多拉晨間報報 ✨" if time_of_day == 'morning' else "✨ 多多拉晚間報報 ✨"
    try:
        line_bot_api.broadcast(TextSendMessage(text=f"{prefix}\n\n{advice}"))
    except Exception as e:
        print(f"廣播發送失敗：{e}")


# 設定排程
scheduler = BackgroundScheduler()
scheduler.add_job(lambda: send_weather_update(
    'morning'), 'cron', hour=8, minute=30)
scheduler.add_job(lambda: send_weather_update(
    'afternoon'), 'cron', hour=18, minute=30)
scheduler.add_job(check_earthquake, 'interval', minutes=1)
scheduler.start()

# ==================== 4. Webhook 與訊息處理 ====================


@app.route("/dodora/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_msg = event.message.text

    # --- 功能 A：寫信 (強化版) ---
    if user_msg.startswith("寫信"):
        content = re.sub(r"^寫信\s*[:：]\s*", "", user_msg).strip()
        if not content:
            line_bot_api.reply_message(
                event.reply_token, TextSendMessage(text="信件內容不能是空的唷！"))
            return
        receiver_id = USER_PARTNER if user_id == USER_ME else USER_ME
        all_mails = load_mailbox()
        if receiver_id not in all_mails:
            all_mails[receiver_id] = []
        all_mails[receiver_id].append(
            {"content": content, "time": datetime.datetime.now().strftime("%m/%d %H:%M")})
        save_mailbox(all_mails)
        line_bot_api.reply_message(
            event.reply_token, TextSendMessage(text="信件已悄悄投入信箱囉！📬"))

    elif user_msg == "寫封情書":
        line_bot_api.reply_message(
            event.reply_token, TextSendMessage(text="只要說出你想對另一半說的話，我來幫你寫情書吧！請輸入『寫信: 你的話』來寄出唷！"))

    # --- 功能 B：打開信箱 ---
    elif user_msg == "打開信箱":
        all_mails = load_mailbox()
        my_mails = all_mails.get(user_id, [])
        if not my_mails:
            reply_text = "目前信箱空空如也唷！💨"
        else:
            reply_text = f"💌 目前有 {len(my_mails)} 封信唷！\n\n"
            for i, mail in enumerate(my_mails, 1):
                reply_text += f"{i}. 來自另一半 ({mail['time']})\n"
            reply_text += "\n輸入『看第 1 封』拆信唷！"
        line_bot_api.reply_message(
            event.reply_token, TextSendMessage(text=reply_text))

    # --- 功能 C：拆信 ---
    elif user_msg.startswith("看第") and user_msg.endswith("封"):
        try:
            idx = int(user_msg.replace("看第", "").replace("封", "").strip()) - 1
            all_mails = load_mailbox()
            my_mails = all_mails.get(user_id, [])
            if 0 <= idx < len(my_mails):
                mail = my_mails.pop(idx)
                save_mailbox(all_mails)
                reply_text = f"📖 拆開信件：\n--------------------\n{mail['content']}\n--------------------\n時間：{mail['time']}\n\n讀完就消失囉！"
            else:
                reply_text = "找不到那一封信唷！"
        except:
            reply_text = "格式錯了唷！"
        line_bot_api.reply_message(
            event.reply_token, TextSendMessage(text=reply_text))

    # --- 功能 D：天氣查詢 ---
    elif "天氣" in user_msg:
        # 1. 即時回覆
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="讓多多拉來幫你看看台南今天的天氣唷！🌤️")
        )

        w_data = get_tainan_weather()
        # 2. 取得與廣播一致的精確內容
        reply_text = process_weather_ollama(w_data)

        # 3. 主動推播結果
        line_bot_api.push_message(user_id, TextSendMessage(text=reply_text))


if __name__ == "__main__":
    app.run(port=5000)
