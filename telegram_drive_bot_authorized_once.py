# telegram_drive_bot_authorized_once.py
import os
import io
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler,
                          ContextTypes, ConversationHandler, MessageHandler, filters)
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from openpyxl import load_workbook
import tempfile
from dotenv import load_dotenv

load_dotenv()

# שלבים
SELECTING_DATE, SELECTING_WORKERS, CONFIRM_SELECTION, \
ASK_NAME, ASK_SALARY, ASK_START_DATE = range(6)

# הגדרות
SCOPES = ['https://www.googleapis.com/auth/drive']
FILE_ID = os.environ.get("EXCEL_FILE_ID")
AUTHORIZED_USERS_FILE = "authorized_users.json"
ADMIN_PASSWORD = "204560916"
CREDENTIALS_JSON = json.loads(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON
