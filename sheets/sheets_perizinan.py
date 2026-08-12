import os
import json
import time
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from googleapiclient.discovery import build

PERIZINAN_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
PERIZINAN_SPREADSHEET_ID = os.getenv("PERIZINAN_SPREADSHEET_ID")
SHEET_RIWAYAT = os.getenv("SHEET_RIWAYAT", "riwayat_perizinan")
SHEET_DURASI= os.getenv("SHEET_DURASI", "durasi_perizinan")
SHEET_PENGAJUAN= os.getenv("SHEET_PENGAJUAN", "pengajuan_perizinan")
SHEET_STATUS_PERIZINAN= os.getenv("SHEET_STATUS_PERIZINAN", "status_perizinan")

DATABASE_SISWA_SPREADSHEET_ID = os.getenv("DATABASE_SISWA_SPREADSHEET_ID")
SHEET_DATABASE_SISWA = os.getenv("SHEET_DATABASE_SISWA", "data_siswa")


_perizinan_cache = {"data": None, "fetched_at": None}
PERIZINAN_CACHE_TTL_SECONDS = int(os.getenv("PERIZINAN_CACHE_TTL", "120"))
