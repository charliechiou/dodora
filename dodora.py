import requests
import datetime
import urllib3
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
        with open(MAILBOX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {USER_ME: [], USER_PARTNER: []}


def save_mailbox(data):
    with open(MAILBOX_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# --- 天氣抓取函數 ---
# --- 設定您的溫度體感門檻 (可隨時調整) ---
COLD_TEMP = 18  # 低於 18 度您覺得冷
HOT_TEMP = 28   # 高於 28 度您覺得熱


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
    """ 根據您的標準產出體感標籤 """
    if not weather_data:
        return "未知"

    min_t = int(weather_data['MinT'])
    max_t = int(weather_data['MaxT'])
    pop = int(weather_data['PoP'])

    # 冷熱判斷邏輯
    if min_t <= COLD_TEMP:
        feeling = "寒冷 (請務必提醒穿厚外套)"
    elif max_t >= HOT_TEMP:
        feeling = "酷熱 (請提醒防曬與補水)"
    else:
        feeling = "舒適涼爽"

    # 額外加入降雨提醒邏輯
    rain_alert = "記得帶傘唷" if pop >= 30 else "不必帶傘"

    return f"體感：{feeling}，雨具：{rain_alert}"

# ==================== 3. 每日廣播任務 (改用 Ollama) ====================


def send_weather_update(time_of_day):
    weather_info = get_tainan_weather()
    prompt = f"時段：{'早上' if time_of_day == 'morning' else '傍晚'}\n氣象數據：{weather_info}"

    try:
        response = ollama.chat(
            model='gemma2:2b',
            messages=[
                {'role': 'system', 'content': (
                    "你名叫多多拉，是專業且親切的氣象助手。你的任務是將氣象數據轉化為溫暖的建議。\n"
                    "請嚴格遵守以下格式輸出：\n"
                    "1.【今日天氣簡報】：(一句話描述)\n"
                    "2.【穿衣建議】：(具體且精確的建議)\n"
                    "3.【多多拉提醒】：(親切的結尾語助詞用『唷』)\n"
                    "注意：文字要精簡，不准使用『大家』，直接對使用者說話。"
                )},
                {'role': 'user', 'content': prompt},
            ],
            options={'temperature': 0.3, 'num_predict': 200}  # 降低隨機性
        )
        advice = response['message']['content'].strip()
        line_bot_api.broadcast(TextSendMessage(
            text=f"✨ 多多拉晨間報報 ✨\n\n{advice}" if time_of_day == 'morning' else f"✨ 多多拉晚間報報 ✨\n\n{advice}"))
    except Exception as e:
        print(f"本地廣播生成失敗：{e}")


# 設定排程
scheduler = BackgroundScheduler()
scheduler.add_job(lambda: send_weather_update(
    'morning'), 'cron', hour=8, minute=30)
scheduler.add_job(lambda: send_weather_update(
    'afternoon'), 'cron', hour=18, minute=30)
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

        if w_data:
            feeling = get_feeling_label(w_data)
            pop_val = int(w_data.get('PoP', 0))

            # --- 完全隔離指令 ---
            if pop_val >= 30:
                # 只有機率高時，才把「雨具」這個概念丟給 AI
                umbrella_instruction = f"目前降雨機率為 {pop_val}%，請務必提醒出門『記得帶傘』。"
            else:
                # 機率低時，對 AI 來說「雨傘」這個詞根本不存在
                umbrella_instruction = ""

            # 3. 組合 Prompt
            # 如果沒有雨傘指令，AI 的 Prompt 裡就只有氣溫和體感
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
                        {'role': 'system',
                            'content': '你名叫多多拉，語氣親切。請根據使用者提供的資訊給予穿衣與生活建議。'},
                        {'role': 'user', 'content': prompt},
                    ],
                    options={'temperature': 0.3}  # 極低隨機性
                )
                raw_text = response['message']['content'].strip()
                # 將換行符號替換為空，並處理多餘空格
                reply_text = raw_text.replace(
                    "\n", " ").replace("\r", " ").strip()
                # 如果擔心 AI 生成多個空格，可以用 re 模組處理
                reply_text = re.sub(r'\s+', ' ', reply_text)
            except Exception as e:
                reply_text = f"目前台南 {w_data['MinT']}~{w_data['MaxT']}度，多多拉覺得很{feeling}唷！"
        else:
            reply_text = "氣象局好像在忙碌中，晚點再問我唷！"

        # 主動推播結果
        line_bot_api.push_message(user_id, TextSendMessage(text=reply_text))


if __name__ == "__main__":
    app.run(port=5000)
