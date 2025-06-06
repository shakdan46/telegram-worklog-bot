
import os
import datetime
import tempfile
import pandas as pd
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# Telegram token from environment variable
TOKEN = os.environ.get("BOT_TOKEN")

# File ID of the spreadsheet on Google Drive
FILE_ID = "1UT4zWtuny8ES2z3dF2UTudK86HF1Mm5B"

# Service account credentials
SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'credentials.json'
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)

# Telegram states
SELECTING_DATE, SELECTING_WORKERS = range(2)
user_data = {}

# List of workers
WORKERS = ["אבי מהיוב", "מאגד", "מוסטפא", "באסם", "אבו ערב", "יחיא", "מחמוד שקדאן", "רביע"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("שלום! אנא הזן תאריך בפורמט YYYY-MM-DD:")
    return SELECTING_DATE

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        date_input = update.message.text.strip()
        date_obj = datetime.datetime.strptime(date_input, "%Y-%m-%d").date()
        user_data[update.effective_user.id] = {"date": date_obj, "workers": []}
        keyboard = [[InlineKeyboardButton(worker, callback_data=worker)] for worker in WORKERS]
        keyboard.append([InlineKeyboardButton("✔ סיום", callback_data="done")])
        await update.message.reply_text("בחר את העובדים שעבדו ביום זה:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECTING_WORKERS
    except ValueError:
        await update.message.reply_text("פורמט תאריך לא תקין. נסה שוב (YYYY-MM-DD):")
        return SELECTING_DATE

async def receive_workers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if query.data == "done":
        await query.edit_message_text("מעדכן את הקובץ...")
        date = user_data[user_id]["date"]
        selected_workers = user_data[user_id]["workers"]
        success = update_excel_on_drive(FILE_ID, date, selected_workers)
        if success:
            await query.message.reply_text("הנתונים נשמרו בהצלחה ✅")
        else:
            await query.message.reply_text("❌ אירעה שגיאה בשמירת הנתונים.")
        return ConversationHandler.END
    else:
        if query.data not in user_data[user_id]["workers"]:
            user_data[user_id]["workers"].append(query.data)
        await query.answer(text=f"{query.data} נוסף")
        return SELECTING_WORKERS

def update_excel_on_drive(file_id, date, workers):
    try:
        # הורדה
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)

        # שמירה זמנית וטעינה
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(fh.read())
            tmp_path = tmp.name

        month_name = date.strftime("%B")
        hebrew_months = {
            "January": "ינואר", "February": "פברואר", "March": "מרץ", "April": "אפריל",
            "May": "מאי", "June": "יוני", "July": "יולי", "August": "אוגוסט",
            "September": "ספטמבר", "October": "אוקטובר", "November": "נובמבר", "December": "דצמבר"
        }
        sheet_name = hebrew_months[month_name]
        df = pd.read_excel(tmp_path, sheet_name=sheet_name)

        for worker in workers:
            mask = (df["תאריך"] == pd.Timestamp(date)) & (df["שם הפועל"] == worker)
            df.loc[mask, "הגיע לעבודה?"] = "✔"

        with pd.ExcelWriter(tmp_path, engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)

        media = MediaFileUpload(tmp_path, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        drive_service.files().update(fileId=file_id, media_body=media).execute()
        return True
    except Exception as e:
        print("שגיאה:", e)
        return False

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("הפעולה בוטלה.")
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)],
            SELECTING_WORKERS: [CallbackQueryHandler(receive_workers)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
