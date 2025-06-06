import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler, ConversationHandler
)
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime
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

# === קריאת האישורים מה־Environment ===
CREDENTIALS_JSON = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
credentials = service_account.Credentials.from_service_account_info(
    json.loads(CREDENTIALS_JSON), scopes=SCOPES)
service = build('sheets', 'v4', credentials=credentials)

# === התחלה ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("שלום! אנא הזן תאריך בפורמט: YYYY-MM-DD")
    return SELECTING_DATE

# === קבלת תאריך ===
async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()
    try:
        # ניתוח תאריך מהטקסט
        date_obj = datetime.strptime(date_text, '%Y-%m-%d')
        formatted_date = date_obj.strftime('%d/%m/%Y')  # פורמט כמו בגוגל שיטס
        context.user_data['selected_date'] = formatted_date
        month_sheet = MONTH_MAP[date_obj.strftime('%m')]

        # קריאת הנתונים מהגיליון
        sheet = service.spreadsheets()
        range_name = f'{month_sheet}!A1:Z'
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        rows = result.get('values', [])

        headers = rows[0]
        date_idx = headers.index('תאריך')
        name_idx = headers.index('שם הפועל')

        target_workers = []
        for row in rows[1:]:
            if len(row) > date_idx and row[date_idx].strip() == formatted_date:
                if len(row) > name_idx:
                    target_workers.append(row[name_idx].strip())

        target_workers = list(set(filter(None, target_workers)))  # הסרת כפולים וריקים

        if not target_workers:
            await update.message.reply_text("⚠️ לא נמצאו פועלים בתאריך הזה.")
            return ConversationHandler.END

        context.user_data['workers'] = target_workers
        context.user_data['selected'] = []

        # בניית כפתורים
        buttons = [[InlineKeyboardButton(name, callback_data=name)] for name in target_workers]
        buttons.append([InlineKeyboardButton("סיום ✅", callback_data="done")])

        await update.message.reply_text("בחר את העובדים:", reply_markup=InlineKeyboardMarkup(buttons))
        return SELECTING_WORKERS

    except Exception as e:
        await update.message.reply_text("❌ שגיאה: ודא שכתבת תאריך חוקי בפורמט YYYY-MM-DD")
        return SELECTING_DATE

# === בחירת פועלים ===
async def handle_worker_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == "done":
        selected = context.user_data.get("selected", [])
        if selected:
            await query.edit_message_text(
                text="העובדים שנבחרו:\n" + "\n".join(selected))
        else:
            await query.edit_message_text(text="לא נבחרו עובדים.")
        return ConversationHandler.END

    if choice not in context.user_data["selected"]:
        context.user_data["selected"].append(choice)

    await query.answer(text=f"{choice} נוסף ✅", show_alert=False)
    return SELECTING_WORKERS

# === הפעלת הבוט ===
if __name__ == '__main__':
    TOKEN = os.environ.get("BOT_TOKEN")

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
