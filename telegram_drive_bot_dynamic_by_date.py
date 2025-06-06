import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler, ConversationHandler
)
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime
from dateutil import parser  # מאפשר גמישות בפורמט תאריך
import os
import json

# === שלבים ===
SELECTING_DATE, SELECTING_WORKERS = range(2)

# === התחברות ל-Google Sheets ===
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SPREADSHEET_ID = '1UT4zWtuny8ES2z3dF2UTudK86HF1Mm5B'

# מיפוי חודשים
MONTH_MAP = {
    '01': 'ינואר', '02': 'פברואר', '03': 'מרץ', '04': 'אפריל',
    '05': 'מאי', '06': 'יוני', '07': 'יולי', '08': 'אוגוסט',
    '09': 'ספטמבר', '10': 'אוקטובר', '11': 'נובמבר', '12': 'דצמבר'
}

# קריאת האישורים מגוגל
CREDENTIALS_JSON = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
credentials = service_account.Credentials.from_service_account_info(
    json.loads(CREDENTIALS_JSON), scopes=SCOPES
)
service = build('sheets', 'v4', credentials=credentials)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("שלום! אנא הזן תאריך בפורמט חוקי לדוגמה:\nYYYY-MM-DD או DD/MM/YYYY או 01-06-2025")
    return SELECTING_DATE

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()
    try:
        # מנסה לפרש כל תאריך חוקי
        date_obj = parser.parse(date_text, dayfirst=False)
        formatted_date = date_obj.strftime('%d/%m/%Y')
        context.user_data['selected_date'] = formatted_date
        month_sheet = MONTH_MAP[date_obj.strftime('%m')]

        # קריאה לגיליון
        sheet = service.spreadsheets()
        range_name = f'{month_sheet}!A1:Z'
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        rows = result.get('values', [])

        if not rows:
            await update.message.reply_text("⚠️ לא נמצאו נתונים בגיליון.")
            return ConversationHandler.END

        headers = rows[0]
        date_idx = headers.index('תאריך')
        name_idx = headers.index('שם הפועל')

        # סינון שמות הפועלים לפי תאריך
        target_workers = []
        for row in rows[1:]:
            if len(row) > date_idx and row[date_idx] == formatted_date:
                if len(row) > name_idx:
                    target_workers.append(row[name_idx])

        target_workers = list(set(filter(None, target_workers)))

        if not target_workers:
            await update.message.reply_text("⚠️ לא נמצאו פועלים בתאריך הזה.")
            return ConversationHandler.END

        context.user_data['workers'] = target_workers
        context.user_data['selected'] = []

        buttons = [[InlineKeyboardButton(name, callback_data=name)] for name in target_workers]
        buttons.append([InlineKeyboardButton("סיום ✅", callback_data="done")])
        await update.message.reply_text("בחר את העובדים:", reply_markup=InlineKeyboardMarkup(buttons))
        return SELECTING_WORKERS

    except Exception:
        await update.message.reply_text("❌ שגיאה: ודא שכתבת תאריך חוקי. פורמטים אפשריים:\n- YYYY-MM-DD\n- DD/MM/YYYY\n- DD-MM-YYYY")
        return SELECTING_DATE

async def handle_worker_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == "done":
        selected = context.user_data.get("selected", [])
        await query.edit_message_text(text="העובדים שנבחרו:\n" + "\n".join(selected))
        return ConversationHandler.END

    if choice not in context.user_data["selected"]:
        context.user_data["selected"].append(choice)

    await query.answer(text=f"{choice} נוסף ✅", show_alert=False)
    return SELECTING_WORKERS

if __name__ == '__main__':
    import dotenv
    dotenv.load_dotenv()

    TOKEN = os.getenv("TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECTING_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)],
            SELECTING_WORKERS: [CallbackQueryHandler(handle_worker_selection)],
        },
        fallbacks=[]
    )

    app.add_handler(conv_handler)
    app.run_polling()
