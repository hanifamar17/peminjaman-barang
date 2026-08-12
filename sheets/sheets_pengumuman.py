import os
import json
import time
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from googleapiclient.discovery import build


JADWAL_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
JADWAL_SPREADSHEET_ID = os.getenv("JADWAL_SPREADSHEET_ID")

# Pengumuman (pengumuman madrasah)
PENGUMUMAN_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
PENGUMUMAN_SPREADSHEET_ID = os.getenv("PENGUMUMAN_SPREADSHEET_ID")
SHEET_PENGUMUMAN = os.getenv("SHEET_PENGUMUMAN", "pengumuman")

_pengumuman_cache = {"data": None, "fetched_at": None}
PENGUMUMAN_CACHE_TTL_SECONDS = int(os.getenv("PENGUMUMAN_CACHE_TTL", "120"))

def _invalidate_pengumuman_cache():
    _pengumuman_cache["data"] = None
    _pengumuman_cache["fetched_at"] = None

bulan = {
    1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
    5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
    9: "September", 10: "Oktober", 11: "November", 12: "Desember"
}

# PENGUMUMAN
def _get_pengumuman_service():
    creds_env = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not creds_env:
        raise RuntimeError("GOOGLE_CREDENTIALS_JSON tidak diset")

    if creds_env.strip().endswith(".json"):
        creds = service_account.Credentials.from_service_account_file(
            creds_env, scopes=PENGUMUMAN_SCOPES
        )
    else:
        creds_dict = json.loads(creds_env)
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=PENGUMUMAN_SCOPES
        )

    return build("sheets", "v4", credentials=creds, cache_discovery=False)

def get_all_pengumuman(force_refresh=False):
    now = time.time()
    if (not force_refresh and _pengumuman_cache["data"] is not None
            and _pengumuman_cache["fetched_at"] is not None
            and now - _pengumuman_cache["fetched_at"] < PENGUMUMAN_CACHE_TTL_SECONDS):
        return _pengumuman_cache["data"]

    service = _get_pengumuman_service()
    range_name = f"{SHEET_PENGUMUMAN}!A:E"
    result = service.spreadsheets().values().get(
        spreadsheetId=PENGUMUMAN_SPREADSHEET_ID,
        range=range_name
    ).execute()

    rows = result.get("values", [])
    if not rows:
        _pengumuman_cache["data"] = []
        _pengumuman_cache["fetched_at"] = now
        return []

    header = rows[0]
    records = []
    for i, row in enumerate(rows[1:], start=2):
        row_padded = row + [""] * (len(header) - len(row))
        r = dict(zip(header, row_padded))
        r["_row_number"] = i
        records.append(r)

    bulan_rev = {v: k for k, v in bulan.items()}

    def _parse_updated_at(s):
        try:
            tanggal_part, jam_part = s.split(", ")
            day, bulan_nama, year = tanggal_part.split(" ")
            month = bulan_rev[bulan_nama]
            hour, minute = jam_part.split(":")
            return datetime(int(year), month, int(day), int(hour), int(minute))
        except Exception:
            return datetime.min
    
    records.sort(key=lambda r: _parse_updated_at(r.get("updated_at", "")), reverse=True)

    _pengumuman_cache["data"] = records
    _pengumuman_cache["fetched_at"] = now
    return records

def get_pengumuman_by_id(pengumuman_id):
    items = get_all_pengumuman()
    for r in items:
        if str(r.get("id")) == str(pengumuman_id):
            return r
    return None

def add_pengumuman(title, desc):
    service = _get_pengumuman_service()
    items = get_all_pengumuman(force_refresh=True)
    new_id = max([int(r["id"]) for r in items if str(r.get("id")).isdigit()], default=0) + 1

    now = datetime.now(ZoneInfo("Asia/Jakarta"))
    timestamp = f"{now.day} {bulan[now.month]} {now.year}, {now.strftime('%H:%M')}"

    values = [[new_id, title, desc or "", timestamp, timestamp]]
    service.spreadsheets().values().append(
        spreadsheetId=PENGUMUMAN_SPREADSHEET_ID,
        range=f"{SHEET_PENGUMUMAN}!A:E",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": values}
    ).execute()
    _invalidate_pengumuman_cache()
    return new_id

def update_pengumuman(pengumuman_id, title, desc):
    item = get_pengumuman_by_id(pengumuman_id)
    if not item:
        return False
    row = item["_row_number"]

    now = datetime.now(ZoneInfo("Asia/Jakarta"))
    updated_at = f"{now.day} {bulan[now.month]} {now.year}, {now.strftime('%H:%M')}"

    service = _get_pengumuman_service()
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=PENGUMUMAN_SPREADSHEET_ID,
        body={
            "valueInputOption": "USER_ENTERED",
            "data": [
                {"range": f"{SHEET_PENGUMUMAN}!B{row}:C{row}", "values": [[title, desc]]},
                {"range": f"{SHEET_PENGUMUMAN}!E{row}", "values": [[updated_at]]},
            ]
        }
    ).execute()
    _invalidate_pengumuman_cache()
    return True

def delete_pengumuman(pengumuman_id):
    item = get_pengumuman_by_id(pengumuman_id)
    if not item:
        return False
    row = item["_row_number"]

    service = _get_pengumuman_service()
    sheet_meta = service.spreadsheets().get(spreadsheetId=PENGUMUMAN_SPREADSHEET_ID).execute()
    sheet_id = None
    for s in sheet_meta["sheets"]:
        if s["properties"]["title"] == SHEET_PENGUMUMAN:
            sheet_id = s["properties"]["sheetId"]
            break
    if sheet_id is None:
        raise RuntimeError(f"Sheet {SHEET_PENGUMUMAN} tidak ditemukan")

    service.spreadsheets().batchUpdate(
        spreadsheetId=PENGUMUMAN_SPREADSHEET_ID,
        body={
            "requests": [{
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": row - 1,
                        "endIndex": row
                    }
                }
            }]
        }
    ).execute()
    _invalidate_pengumuman_cache()
    return True

