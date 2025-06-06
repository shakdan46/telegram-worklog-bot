import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
)
from google.oauth2 import service_account
from googleapiclient.discovery import build

# === שלבים ===
SELECTING_DATE, SELECTING_WORKERS = range(2)

# === הגדרות קובץ Google Sheets ===
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SPREADSHEET_ID = '1UT4zWtuny8ES2z3dF2UTudK86HF1Mm5B'

# === מיפוי חודשים לעברית ===
MONTH_MAP = {
    '01': 'ינואר', '02': 'פברואר', '03': 'מרץ', '04': 'אפריל',
    '05': 'מאי', '06': 'יוני', '07': 'יולי', '08': 'אוגוסט',
    '09': 'ספטמבר', '10': 'אוקטובר', '11': 'נובמבר', '12': 'דצמבר'
}

# === התחברות לחשבון שירות ===
CREDENTIALS_JSON = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
if not CREDENTIALS_JSON:
    raise Exception("GOOGLE_APPLICATION_CREDENTIALS_JSON not set in environment.")
credentials = service_account.Credentials.from_service_account_info(eval(CREDENTIALS_JSON), scopes=SCOPES)
service = build('sheets', 'v4', credentials=credentials)

# === פונקציית התחלה ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("שלום! אנא הזן תאריך בפורמט: YYYY-MM-DD")
    return SELECTING_DATE

# === קבלת תאריך והצגת עובדים ===
async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()
    try:
        date_obj = datetime.strptime(date_text, '%Y-%m-%d')
        context.user_data['selected_date'] = date_obj.strftime('%Y-%m-%d')
        sheet_name = MONTH_MAP[date_obj.strftime('%m')]
        sheet_range = f"{sheet_name}!A1:Z"

        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=sheet_range
        ).execute()
        rows = result.get('values', [])

        if not rows:
            await update.message.reply_text("❌ לא נמצאו נתונים בגיליון.")
            return ConversationHandler.END

        headers = rows[0]
        date_idx = headers.index('תאריך')
        name_idx = headers.index('שם הפועל')

        selected_workers = []
        target_date = date_obj.strftime('%d/%m/%Y')

        for row in rows[1:]:
            if len(row) > max(date_idx, name_idx) and row[date_idx] == target_date:
                name = row[name_idx]
                if name:
                    selected_workers.append(name)

        selected_workers = sorted(list(set(selected_workers)))
        if not selected_workers:
            await update.message.reply_text("⚠️ לא נמצאו פועלים בתאריך הזה.")
            return ConversationHandler.END

        context.user_data['workers'] = selected_workers
        context.user_data['selected'] = []

        buttons = [[InlineKeyboardButton(name, callback_data=name)] for name in selected_workers]
        buttons.append([InlineKeyboardButton("סיום ✅", callback_data="done")])
        await update.message.reply_text("בחר את העובדים:", reply_markup=InlineKeyboardMarkup(buttons))
        return SELECTING_WORKERS

    except ValueError:
        await update.message.reply_text("❌ שגיאה: ודא שכתבת תאריך חוקי בפורמט YYYY-MM-DD")
        return SELECTING_DATE
    except Exception as e:
        logging.error(f"שגיאה בקבלת עובדים: {e}")
        await update.message.reply_text("⚠️ שגיאה כללית בשליפת נתונים.")
        return ConversationHandler.END

# === בחירת עובדים ===
async def handle_worker_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selection = query.data

    if selection == "done":
        selected = context.user_data.get("selected", [])
        if selected:
            await query.edit_message_text(text="העובדים שנבחרו:\n" + "\n".join(selected))
        else:
            await query.edit_message_text(text="לא נבחרו עובדים.")
        return ConversationHandler.END

    if selection not in context.user_data['selected']:
        context.user_data['selected'].append(selection)
        await query.answer(text=f"{selection} נוסף ✅", show_alert=False)

    return SELECTING_WORKERS

# === MAIN ===
if __name__ == '__main__':
    import asyncio

    TOKEN = os.environ.get('TELEGRAM_TOKEN')
    if not TOKEN:
        raise Exception("❌ TELEGRAM_TOKEN לא מוגדר ב־Environment Variables ב־Render.")

    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)],
            SELECTING_WORKERS: [CallbackQueryHandler(handle_worker_selection)],
        },
        fallbacks=[],
    )

    app.add_handler(conv_handler)
    app.run_polling()
