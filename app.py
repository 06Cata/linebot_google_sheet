import os
from flask import Flask, request, abort
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials


# --- SDK v2  ---
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- Google Sheet ---
GOOGLE_SHEET_NAME = 'camera_客戶交易紀錄' 
GOOGLE_WORKSHEET_NAME = '2024_上半年'

try:
    # gc = gspread.service_account(filename=GOOGLE_SHEET_CREDENTIALS)
    service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
    gc = gspread.authorize(credentials)
    
    spreadsheet = gc.open(GOOGLE_SHEET_NAME)
    worksheet = spreadsheet.worksheet(GOOGLE_WORKSHEET_NAME)
    print("成功連接到 Google Sheet！")
except Exception as e:
    print(f"連接 Google Sheet 失敗: {e}")
    worksheet = None 
    
# --- Line Bot Webhook ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

#
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    reply_message = "請輸入 '查詢 客戶姓名 客戶ID' 來查詢交易紀錄。"

    if text.startswith('查詢'):
        parts = text.split(' ', 2)
        if len(parts) == 3:
            query_name = parts[1]
            query_uuid = parts[2]
            reply_message = search_customer_transactions(query_name, query_uuid)
        else:
            reply_message = "指令格式不正確。\n請輸入 '查詢 客戶姓名 客戶ID'。"
    
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_message)
    )

def search_customer_transactions(customer_name, customer_uuid):
    if worksheet is None:
        return "很抱歉，無法連接到交易資料庫，請稍後再試或聯繫管理員。"

    try:
        # get_all_records() 會將第一行作為鍵 (Header)
        all_records = worksheet.get_all_records()
        
        found_transactions = []
        for r in all_records:
            sheet_name = r.get('客戶姓名')
            sheet_uuid = r.get('客戶uuid')

            if sheet_name and sheet_uuid and \
               str(sheet_name).strip() == customer_name.strip() and \
               str(sheet_uuid).strip() == customer_uuid.strip():
                found_transactions.append(r)
        
        if not found_transactions:
            return f"找不到客戶 {customer_name} ({customer_uuid}) 的交易紀錄。"
        
        try:
            found_transactions.sort(key=lambda x: x.get('日期', ''), reverse=True)
        except TypeError:
            pass
            
        # --- 未結清的交易 ---
        unsettled_transactions = []
        for r in found_transactions:
            is_settled_value = str(r.get('是否結清', '')).strip().lower()
            if is_settled_value == 'false' or is_settled_value == '否': # 您可以根據實際情況添加更多判斷條件
                unsettled_transactions.append(r)

        # 取最近三筆
        recent_three_transactions = found_transactions[:3]

        response_messages = []
        
        # 添加最近三筆
        if recent_three_transactions:
             response_messages.append("--- 最近三筆交易紀錄 ---")
        for r in recent_three_transactions:
            msg = (
                f"📅 日期：{r.get('日期', 'N/A')}\n"
                f"Ｎ 交易編號：{r.get('交易編號', 'N/A')}\n" # <-- 這裡已經有交易編號
                f"👤 客戶：{r.get('客戶姓名', 'N/A')}（{r.get('客戶uuid', 'N/A')}）\n"
                f"📌 細項：{r.get('細項', 'N/A')}\n"
                f"🎞 產品：{r.get('產品', 'N/A')}\n"
                f"💰 標價：{r.get('標價', 'N/A')}\n"
                f"💸 客戶收支：{r.get('客戶收支', 'N/A')}\n"
                f"🏪 店家實收：{r.get('店家實收', 'N/A')}\n"
                f"＄ 餘額：{r.get('餘額', 'N/A')}\n"
                f"✅ 是否結清：{r.get('是否結清', 'N/A')}"
            )
            response_messages.append(msg)
            response_messages.append("---") #
            
        # 如果有未結清的交易且與最近三筆沒有完全重疊
        recent_three_ids = {json.dumps(t, sort_keys=True) for t in recent_three_transactions}
        
        actual_unsettled_to_show = []
        for t in unsettled_transactions:
            if json.dumps(t, sort_keys=True) not in recent_three_ids:
                actual_unsettled_to_show.append(t)

        if actual_unsettled_to_show: 
            response_messages.append("\n--- 未結清交易紀錄 ---") 
            for r in actual_unsettled_to_show:
                msg = (
                    f"📅 日期：{r.get('日期', 'N/A')}\n"
                    f"Ｎ 交易編號：{r.get('交易編號', 'N/A')}\n"
                    f"👤 客戶：{r.get('客戶姓名', 'N/A')}（{r.get('客戶uuid', 'N/A')}）\n"
                    f"📌 細項：{r.get('細項', 'N/A')}\n"
                    f"🎞 產品：{r.get('產品', 'N/A')}\n"
                    f"💰 標價：{r.get('標價', 'N/A')}\n"
                    f"💸 客戶收支：{r.get('客戶收支', 'N/A')}\n"
                    f"🏪 店家實收：{r.get('店家實收', 'N/A')}\n"
                    f"＄ 餘額：{r.get('餘額', 'N/A')}\n"
                    f"✅ 是否結清：{r.get('是否結清', 'N/A')}"
                )
                response_messages.append(msg)
                response_messages.append("---")


        # final message
        if not response_messages:
            return f"找不到客戶 {customer_name} ({customer_uuid}) 的交易紀錄。"
        
        final_message = "\n".join(response_messages).rstrip('---').strip()

        if len(response_messages) <= 2 and (response_messages[0].startswith("---") and response_messages[1] == "---"):
            final_message = f"找不到客戶 {customer_name} ({customer_uuid}) 的交易紀錄。"
       
        return final_message
        
    except Exception as e:
        print(f"查詢交易紀錄時發生錯誤: {e}")
        return "查詢交易紀錄時發生未知錯誤，請稍後再試。"

# --- main ---
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
