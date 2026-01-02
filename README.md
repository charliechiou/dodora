# Dodora (多多拉) 🌤️💌

一個溫暖貼心的 LINE Bot，專為情侶設計的天氣助手與私密信箱。

## ✨ 功能特色

### 🌦️ 智慧天氣播報
- **即時天氣查詢**：查詢台南市最新天氣資訊
- **體感建議**：根據溫度提供穿衣建議
- **降雨提醒**：智能判斷是否需要攜帶雨具
- **定時推播**：每日早上 8:30 和晚上 18:30 自動推送天氣報告
- **AI 生成建議**：使用本地 Ollama AI 生成溫暖的天氣提醒

### 💌 情侶信箱系統
- **寫信功能**：向另一半傳送私密訊息
- **信箱管理**：查看收到的信件數量
- **拆信閱讀**：閱讀後信件自動銷毀，保持浪漫神秘感
- **時間戳記**：每封信都記錄寄送時間

## 🛠️ 技術架構

- **Framework**: Flask (Python Web Framework)
- **Bot Platform**: LINE Messaging API
- **AI Model**: Ollama (gemma2:2b)
- **Weather API**: 中央氣象署開放資料平台 API
- **Scheduler**: APScheduler (背景排程任務)
- **Tunnel**: ngrok (本地開發與測試)

## 📋 系統需求

- Python 3.7+
- Ollama (安裝 gemma2:2b 模型)
- LINE Developer Account
- 中央氣象署 API Key
- ngrok (用於本地開發)

## 🚀 安裝步驟

### 1. 克隆專案
```bash
git clone https://github.com/charliechiou/dodora.git
cd dodora
```

### 2. 安裝 Python 依賴套件
```bash
pip install flask line-bot-sdk apscheduler requests ollama urllib3
```

### 3. 安裝並啟動 Ollama
```bash
# 安裝 Ollama (請參考 https://ollama.ai)
# 下載 gemma2:2b 模型
ollama pull gemma2:2b
```

### 4. 設定環境變數

建立 `.env` 檔案或直接設定環境變數：

```bash
export LINE_ACCESS_TOKEN="你的 LINE Channel Access Token"
export LINE_CHANNEL_SECRET="你的 LINE Channel Secret"
export CWA_API_KEY="你的中央氣象署 API Key"
export USER_ME="你的 LINE User ID"
export USER_PARTNER="另一半的 LINE User ID"
```

#### 如何取得各項設定值：

**LINE Bot 設定**:
1. 前往 [LINE Developers Console](https://developers.line.biz/)
2. 建立 Provider 和 Messaging API Channel
3. 取得 Channel Access Token 和 Channel Secret
4. 設定 Webhook URL (使用 ngrok 產生的 URL + `/dodora/callback`)

**中央氣象署 API Key**:
1. 前往 [氣象資料開放平台](https://opendata.cwa.gov.tw/)
2. 註冊帳號並申請 API 授權碼

**LINE User ID**:
- 可透過 LINE Bot 的事件日誌取得
- 或使用 LINE Bot SDK 的工具取得

### 5. 啟動服務

#### 方法一：手動啟動
```bash
# 終端機 1: 啟動 ngrok
ngrok http --domain=your-domain.ngrok-free.dev 5000

# 終端機 2: 啟動 Bot
python dodora.py
```

#### 方法二：使用啟動腳本
編輯 `startup_bot.sh` 修改路徑和設定：
```bash
chmod +x startup_bot.sh
./startup_bot.sh
```

## 📱 使用說明

### 天氣查詢
在 LINE 對話中輸入包含「天氣」的訊息：
```
天氣
今天天氣如何？
```

### 寫信給另一半
```
寫信: 今天想你了 💕
寫信：晚餐想吃什麼呢？
```

### 查看信箱
```
打開信箱
```

### 拆開信件
```
看第 1 封
看第 2 封
```

### 情書功能
```
寫封情書
```

## ⚙️ 自訂設定

### 調整溫度體感門檻
在 `dodora.py` 中修改：
```python
COLD_TEMP = 18  # 低於 18 度覺得冷
HOT_TEMP = 28   # 高於 28 度覺得熱
```

### 調整廣播時間
修改排程時間：
```python
scheduler.add_job(lambda: send_weather_update('morning'), 'cron', hour=8, minute=30)
scheduler.add_job(lambda: send_weather_update('afternoon'), 'cron', hour=18, minute=30)
```

### 切換城市
目前設定為台南市，若要更改城市，修改：
```python
params = {"Authorization": CWA_API_KEY, "locationName": "臺南市", ...}
```

## 📂 專案結構

```
dodora/
├── dodora.py           # 主程式
├── startup_bot.sh      # 啟動腳本
├── mailbox.json        # 信箱資料儲存（自動生成）
├── .env                # 環境變數（需自行建立）
├── .gitignore          # Git 忽略檔案
└── README.md           # 專案說明文件
```

## 🔒 安全性注意事項

- ⚠️ 請勿將 `.env` 檔案或包含敏感資訊的檔案提交到版本控制
- ⚠️ `mailbox.json` 包含私人訊息，已加入 `.gitignore`
- ⚠️ LINE Access Token 和 API Keys 應妥善保管
- 建議在生產環境使用 HTTPS 和更安全的 Token 管理方式

## 🐛 故障排除

### Ollama 連線問題
確保 Ollama 服務正在運行：
```bash
ollama list
ollama run gemma2:2b
```

### LINE Webhook 驗證失敗
- 檢查 `LINE_CHANNEL_SECRET` 是否正確
- 確認 ngrok URL 已正確設定在 LINE Console

### 天氣 API 回傳錯誤
- 確認 `CWA_API_KEY` 是否有效
- 檢查 API 配額是否用盡

### SSL 憑證警告
程式已設定忽略 SSL 警告（僅用於開發環境），生產環境建議移除：
```python
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
```

## 📝 開發紀錄

- 使用 tmux 管理多個背景服務
- 降雨機率 >= 30% 時觸發雨具提醒
- AI 溫度設定為 0.3 以獲得更一致的回覆
- 支援信件的時間戳記與自動銷毀機制

## 🤝 貢獻

歡迎提交 Issue 或 Pull Request！

## 📄 授權

本專案為個人專案，使用前請先聯繫作者。

## 👤 作者

Charlie Chiou ([@charliechiou](https://github.com/charliechiou))

---

💝 **讓多多拉為你們的關係增添溫暖與驚喜！**
