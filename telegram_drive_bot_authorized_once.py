import logging
import io
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler, ConversationHandler
)
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from datetime import datetime
import openpyxl

# === שלבים ===
AUTH, SELECTING_DATE, SELECTING_WORKERS, CONFIRM_SELECTION = range(4)

# === קבועים ===
SCOPES = ['https://www.googleapis.com/auth/drive']
FILE_ID = '1UT4zWtuny8ES2z3dF2UTudK86HF1Mm5B'
PASSWORD = '204560916'
AUTHORIZED_USERS = set()
MONTH_MAP = {
    '01': 'ינואר', '02': 'פברואר', '03': 'מרץ', '04': 'אפריל',
    '05': 'מאי', '06': 'יוני', '07': 'יולי', '08': 'אוגוסט',
    '09': 'ספטמבר', '10': 'אוקטובר', '11': 'נובמבר', '12': 'דצמבר'
}

# === התחברות ל-Google Drive ===
CREDENTIALS_JSON = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
credentials = service_account.Credentials.from_service_account_info(eval(CREDENTIALS_JSON), scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)

# === התחלה עם סיסמה חד־פעמית ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in AUTHORIZED_USERS:
        await update.message.reply_text("✅ כבר זוהית. אנא הזן תאריך בפורמט YYYY-MM-DD:")
        return SELECTING_DATE
    else:
        await update.message.reply_text("🔐 הזן סיסמה כדי להתחיל:")
        return AUTH

async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == PASSWORD:
        AUTHORIZED_USERS.add(update.effective_user.id)
        await update.message.reply_text("🔓 סיסמה נכונה. הזן תאריך בפורמט YYYY-MM-DD:")
        return SELECTING_DATE
    else:
        await update.message.reply_text("❌ סיסמה שגויה. נסה שוב:")
        return AUTH

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()
    try:
        date_obj = datetime.strptime(date_text, '%Y-%m-%d')
        hebrew_month = MONTH_MAP[date_obj.strftime('%m')]
        selected_date = date_obj.strftime('%d/%m/%Y')
        context.user_data['selected_date'] = selected_date
        context.user_data['month_name'] = hebrew_month

        request = drive_service.files().get_media(fileId=FILE_ID)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)

        wb = openpyxl.load_workbook(fh)
        sheet = wb[hebrew_month]

        workers = set()
        for row in sheet.iter_rows(min_row=2, values_only=True):
            row_date = row[0].strftime('%d/%m/%Y') if isinstance(row[0], datetime) else row[0]
            if row_date == selected_date and row[1]:
                workers.add(str(row[1]).strip())

        if not workers:
            await update.message.reply_text("⚠️ לא נמצאו פועלים בתאריך הזה.")
            return ConversationHandler.END

        context.user_data['all_workers'] = list(workers)
        context.user_data['selected'] = []

        return await show_worker_selection(update, context)

    except Exception as e:
        print(e)
        await update.message.reply_text("❌ שגיאה: ודא שכתבת תאריך חוקי בפורמט YYYY-MM-DD")
        return SELECTING_DATE

async def show_worker_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected = context.user_data.get("selected", [])
    available = [w for w in context.user_data["all_workers"] if w not in selected]

    buttons = [[InlineKeyboardButton(name, callback_data=name)] for name in available]
    buttons.append([InlineKeyboardButton("סיום ✅", callback_data="done")])

    if update.callback_query:
        await update.callback_query.edit_message_text("בחר את העובדים:", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.message.reply_text("בחר את העובדים:", reply_markup=InlineKeyboardMarkup(buttons))

    return SELECTING_WORKERS

async def handle_worker_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == "done":
        selected = context.user_data.get("selected", [])
        if not selected:
            await query.edit_message_text(text="❗ לא נבחרו עובדים.")
            return ConversationHandler.END

        return await show_confirmation_menu(query, context)

    if choice not in context.user_data["selected"]:
        context.user_data["selected"].append(choice)

    return await show_worker_selection(update, context)

async def show_confirmation_menu(query, context):
    selected = context.user_data["selected"]
    text = "📝 העובדים שנבחרו:\n" + "\n".join(selected)
    buttons = [
        [InlineKeyboardButton("✅ אישור סופי", callback_data="confirm_final")],
        [InlineKeyboardButton("❌ מחק שם", callback_data="remove_worker")],
        [InlineKeyboardButton("➕ הוסף פועל נוסף", callback_data="add_worker")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    return CONFIRM_SELECTION

async def confirm_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected = context.user_data["selected"]

    # הורדת הקובץ
    request = drive_service.files().get_media(fileId=FILE_ID)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.seek(0)

    wb = openpyxl.load_workbook(fh)
    sheet = wb[context.user_data['month_name']]
    selected_date = context.user_data['selected_date']

    for row in sheet.iter_rows(min_row=2):
        date_cell = row[0]
        name_cell = row[1]
        status_cell = row[2]
        date_val = date_cell.value.strftime('%d/%m/%Y') if isinstance(date_cell.value, datetime) else date_cell.value
        name_val = str(name_cell.value).strip() if name_cell.value else ""
        if date_val == selected_date and name_val in selected:
            status_cell.value = True

    out_stream = io.BytesIO()
    wb.save(out_stream)
    out_stream.seek(0)

    media_body = MediaIoBaseUpload(out_stream, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    drive_service.files().update(fileId=FILE_ID, media_body=media_body).execute()

    await query.edit_message_text("✅ הנתונים עודכנו בהצלחה!\n" + "\n".join(selected))
    return ConversationHandler.END

async def remove_worker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected = context.user_data["selected"]
    buttons = [[InlineKeyboardButton(name + " ❌", callback_data="remove_" + name)] for name in selected]
    buttons.append([InlineKeyboardButton("🔙 חזרה", callback_data="back_to_confirm")])
    await query.edit_message_text("בחר עובד למחיקה:", reply_markup=InlineKeyboardMarkup(buttons))
    return CONFIRM_SELECTION

async def remove_worker_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    name = query.data.replace("remove_", "")
    context.user_data["selected"].remove(name)
    return await show_confirmation_menu(query, context)

async def confirmation_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == "confirm_final":
        return await confirm_selection(update, context)
    elif data == "remove_worker":
        return await remove_worker(update, context)
    elif data.startswith("remove_"):
        return await remove_worker_choice(update, context)
    elif data == "add_worker":
        return await show_worker_selection(update, context)
    elif data == "back_to_confirm":
        return await show_confirmation_menu(update.callback_query, context)

    return CONFIRM_SELECTION

# === הפעלה ===
if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AUTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_password)],
            SELECTING_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)],
            SELECTING_WORKERS: [CallbackQueryHandler(handle_worker_selection)],
            CONFIRM_SELECTION: [CallbackQueryHandler(confirmation_router)],
        },
        fallbacks=[]
    )

    app.add_handler(conv_handler)
    app.run_polling()
