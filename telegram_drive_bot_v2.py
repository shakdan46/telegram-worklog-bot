
import os
import tempfile
import pandas as pd
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import io

BOT_TOKEN = os.environ.get("BOT_TOKEN")
SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'credentials.json'
FILE_ID = '1UT4zWtuny8ES2z3dF2UTudK86HF1Mm5B'

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build('drive', 'v3', credentials=credentials)

SELECTING_DATE, SELECTING_WORKERS = range(2)
user_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("שלום! אנא הזן תאריך בפורמט YYYY-MM-DD:")
    return SELECTING_DATE

async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        date = datetime.strptime(update.message.text, "%Y-%m-%d").date()
        user_data[update.effective_chat.id] = {'date': date, 'workers': []}

        keyboard = [
            [InlineKeyboardButton("אבי חביב", callback_data="אבי חביב")],
            [InlineKeyboardButton("מחמוד שקדאן", callback_data="מחמוד שקדאן")],
            [InlineKeyboardButton("✔ סיום", callback_data="done")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("בחר את העובדים:", reply_markup=reply_markup)
        return SELECTING_WORKERS
    except ValueError:
        await update.message.reply_text("⚠️ פורמט לא תקין. נסה שוב: YYYY-MM-DD")
        return SELECTING_DATE

async def handle_worker_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selection = query.data
    chat_id = update.effective_chat.id

    if selection == "done":
        date = user_data[chat_id]['date']
        selected_workers = user_data[chat_id]['workers']
        success = update_excel_on_drive(FILE_ID, date, selected_workers)
        if success:
            await query.edit_message_text("הנתונים נשמרו בהצלחה ✅")
        else:
            await query.edit_message_text("אירעה שגיאה בשמירת הנתונים ❌")
        return ConversationHandler.END
    else:
        user_data[chat_id]['workers'].append(selection)
        await query.edit_message_text(f"נבחרו: {', '.join(user_data[chat_id]['workers'])}")
        return SELECTING_WORKERS

def update_excel_on_drive(file_id, date, selected_workers):
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)

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

        # Updated matching logic
        df["תאריך"] = pd.to_datetime(df["תאריך"], errors="coerce").dt.date
        date_obj = pd.to_datetime(date).date()
        for worker in selected_workers:
            mask = (df["תאריך"] == date_obj) & (df["שם הפועל"] == worker)
            df.loc[mask, "הגיע לעבודה?"] = "✔"

        df.to_excel(tmp_path, sheet_name=sheet_name, index=False)

        media_body = MediaFileUpload(tmp_path, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        service.files().update(fileId=file_id, media_body=media_body).execute()
        return True
    except Exception as e:
        print(f"שגיאה: {e}")
        return False

from telegram.ext import ConversationHandler
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        SELECTING_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date)],
        SELECTING_WORKERS: [CallbackQueryHandler(handle_worker_selection)],
    },
    fallbacks=[]
))
app.run_polling()
