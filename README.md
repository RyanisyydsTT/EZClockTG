# EZClock Bot

EZClock Bot 是一個用於追蹤出勤和休假的 Telegram 機器人。

## 功能

*   透過按鈕簽到和簽退
*   追蹤員工打卡位置
*   透過按鈕申請休假
*   管理員可以查詢出勤統計資料
*   管理員可以向員工發送訊息

## 必要條件

在使用機器人之前，每個用戶都必須先向機器人發送一條訊息。這樣機器人才能獲得與用戶聊天的權限。

## 設定

1.  **取得群組聊天 ID：**
    *   將機器人新增到您想要使用的 Telegram 群組。
    *   向群組發送任何訊息。
    *   使用下列其中一個 API 端點來取得群組的 `chat_id`。將 `YOUR_BOT_TOKEN` 替換為您的機器人權杖：
        *   `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
    *   在回應中找到 `chat` 物件，並記下 `id` 的值。這就是您的群組聊天 ID。
  
    *   您也可以從``@RawDataBot``取得，將機器人加入至群組後輸入``/start``，在回覆訊息中找到 ``chat:``底下的``"id": ＸＸＸＸＸＸＸＸ``，該數值即為您的群組聊天ID。

2.  **設定環境：**
    *   建立一個名為 `.env` 的檔案。
    *   將您的機器人權杖和群組聊天 ID 新增到 `.env` 檔案中，如下所示：
        ```
        BOT_TOKEN=YOUR_BOT_TOKEN
        GROUP_CHAT_ID=YOUR_GROUP_CHAT_ID
        ```
3. 設定 Cloudflare Tunnel(或其他內網穿透服務)
   *   前往 [Cloudflare One(ZeroTrust)](https://one.dash.cloudflare.com/)
   *   在側邊欄選擇 網路 -> Tunnels
   *   建立一個新Tunnel
   *   使用cloudflared，選擇適合您的安裝方式
   *   應用成功後，在Dash上選擇 "公用主機名稱"， 綁定您的網域 (ex: ``clock[.]ryanisyyds[.]xyz``)
   *   類型選擇HTTP，IP預設為``127.0.0.1``，請依實際情況設定並加入連接阜(Port)，連接阜通常為``5005`` (ex: ``127.0.0.1:5005``)        

## 使用方法

### 新增使用者

1.  開啟 `users.csv` 檔案。
2.  在一個新行中新增使用者的姓名。 REPO原檔有附上填寫格式

### 取得使用者聊天 ID

1.  當使用者向機器人發送訊息時，機器人會將他們的使用者名稱與 `users.csv` 檔案中的姓名進行比對。
2.  如果找到相符的姓名，機器人會自動擷取並儲存該使用者的聊天 ID。

### 一般指令

使用者可以透過點擊鍵盤按鈕來執行以下操作：

*   **🟢 上班打卡** - 記錄您的簽到時間。
*   **🔴 下班打卡** - 記錄您的簽退時間。
*   **📝 申請休假** - 申請休假。

### 管理員指令

只有在 `users.csv` 中 `role` 欄位設定為 `supervisor` 的使用者才能使用以下指令：

*   `/todaystat [opt* username]` - 顯示今天所有或指定使用者的打卡狀態。
*   `/monthstat [opt* username]` - 顯示本月所有或指定使用者的打卡狀態。
*   `/msg [username] [message]` - 向指定的使用者發送私人訊息。

## 貢獻

歡迎提出PR。對於重大的變更，請先開啟一個議題以討論您想要變更的內容。
