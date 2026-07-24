import os
import json
import time
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from googleapiclient.discovery import build

# =========================
# KONFIGURASI TERPISAH UNTUK JADWAL BOOKING RUANGAN
# Spreadsheet & service account BEDA dari sheets.py (inventory/peminjaman)
# =========================
JADWAL_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
PENGUMUMAN_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
JADWAL_SPREADSHEET_ID = os.getenv("JADWAL_SPREADSHEET_ID")
JADWAL_SHEET_NAME = os.getenv("JADWAL_SHEET_NAME", "Form Responses 1")
KALENDER_SHEET_NAME = os.getenv("KALENDER_SHEET_NAME", "kalender_akademik")
PENGUMUMAN_SPREADSHEET_ID = os.getenv("JADWAL_SPREADSHEET_ID")
PENGUMUMAN_SHEET_NAME = os.getenv("PENGUMUMAN_SHEET_NAME", "pengumuman")

# Cache sederhana in-memory supaya tidak fetch ke Sheets API setiap request
_cache = {"data": None, "fetched_at": None}
CACHE_TTL_SECONDS = int(os.getenv("JADWAL_CACHE_TTL", "120"))  # default 2 menit

_kalender_cache = {"data": None, "fetched_at": None}
KALENDER_CACHE_TTL_SECONDS = int(os.getenv("KALENDER_CACHE_TTL", "3600"))  # jarang berubah, TTL bisa lebih lama


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

def _get_jadwal_service():
    creds_env = os.getenv("JADWAL_GOOGLE_CREDENTIALS_JSON")
    if not creds_env:
        raise RuntimeError("JADWAL_GOOGLE_CREDENTIALS_JSON tidak diset")

    # === PATH FILE (lokal) ===
    if creds_env.strip().endswith(".json"):
        creds = service_account.Credentials.from_service_account_file(
            creds_env, scopes=JADWAL_SCOPES
        )
    # === JSON STRING (Vercel) ===
    else:
        creds_dict = json.loads(creds_env)
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=JADWAL_SCOPES
        )

    return build("sheets", "v4", credentials=creds, cache_discovery=False)


# JADWAL LAB
def _read_jadwal_raw():
    service = _get_jadwal_service()
    range_name = f"{JADWAL_SHEET_NAME}!A:Z"
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=JADWAL_SPREADSHEET_ID, range=range_name)
        .execute()
    )
    return result.get("values", [])

def _parse_time(t):
    """Terima format 'H:MM', 'H:MM:SS', atau 'HH.MM' dari isian form/sheet, kembalikan datetime.time"""
    if not t:
        return None
    t = t.strip().replace(".", ":")
    parts = t.split(":")
    try:
        if len(parts) == 2:
            h, m = parts
            return datetime.time(int(h), int(m))
        elif len(parts) == 3:
            h, m, s = parts
            return datetime.time(int(h), int(m), int(s))
        return None
    except Exception:
        return None

def _parse_tanggal(t):
    """Sheet menyimpan tanggal sebagai string 'DD/MM/YYYY'. Kembalikan objek date agar
    bisa dibandingkan/diformat konsisten, dan simpan juga versi ISO (YYYY-MM-DD)."""
    if not t:
        return None
    t = t.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None

def get_jadwal(force_refresh=False):
    """
    Ambil data jadwal dari 'Form Responses 1', hasil sudah diparse.
    Menggunakan cache in-memory (TTL) agar hemat kuota Sheets API.
    """
    now = datetime.now()
    if (
        not force_refresh
        and _cache["data"] is not None
        and _cache["fetched_at"] is not None
        and (now - _cache["fetched_at"]).total_seconds() < CACHE_TTL_SECONDS
    ):
        return _cache["data"]

    rows = _read_jadwal_raw()
    if not rows or len(rows) < 2:
        _cache["data"] = []
        _cache["fetched_at"] = now
        return []

    headers = [h.strip().lower() for h in rows[0]]

    HEADER_MAP = {
        "timestamp": "timestamp",
        "nama pemesan": "nama_pemesan",
        "nama kegiatan": "nama_kegiatan",
        "tanggal kegiatan": "tanggal",
        "waktu mulai": "waktu_mulai_raw",
        "waktu berakhir": "waktu_selesai_raw",
        "catatan tambahan": "catatan_tambahan",
        "status": "status_sheet",
    }

    idx = {}
    for h_text, field in HEADER_MAP.items():
        if h_text in headers:
            idx[field] = headers.index(h_text)

    entries = []
    for r in rows[1:]:
        if not r or not any(r):
            continue

        def get(field):
            i = idx.get(field)
            return r[i].strip() if i is not None and i < len(r) else ""

        status = get("status_sheet")
        if status != "✅ Disetujui":
            continue  # skip semua yang belum/tidak disetujui

        tanggal_raw = get("tanggal")
        tanggal_obj = _parse_tanggal(tanggal_raw)

        entry = {
            "nama_pemesan": get("nama_pemesan"),
            "nama_kegiatan": get("nama_kegiatan"),
            "tanggal": tanggal_raw,
            "tanggal_iso": tanggal_obj.isoformat() if tanggal_obj else None,
            "waktu_mulai_raw": get("waktu_mulai_raw"),
            "waktu_selesai_raw": get("waktu_selesai_raw"),
            "catatan_tambahan": get("catatan_tambahan"),
        }
        entries.append(entry)

    _cache["data"] = entries
    _cache["fetched_at"] = now
    return entries

def get_jadwal_by_date(tanggal_iso_str):
    """tanggal_iso_str format: YYYY-MM-DD"""
    return [e for e in get_jadwal() if e["tanggal_iso"] == tanggal_iso_str]


# KALENDER
def _read_kalender_raw():
    service = _get_jadwal_service()  # scope readonly sama, bisa reuse
    range_name = f"{KALENDER_SHEET_NAME}!A:Z"
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=JADWAL_SPREADSHEET_ID, range=range_name)
        .execute()
    )
    return result.get("values", [])

def get_kalender_akademik(force_refresh=False):
    """
    Ambil data kalender akademik (libur/agenda madrasah).
    Cache in-memory terpisah dari jadwal lab.
    """
    now = datetime.now()
    if (
        not force_refresh
        and _kalender_cache["data"] is not None
        and _kalender_cache["fetched_at"] is not None
        and (now - _kalender_cache["fetched_at"]).total_seconds() < KALENDER_CACHE_TTL_SECONDS
    ):
        return _kalender_cache["data"]

    raw = _read_kalender_raw()
    if not raw:
        _kalender_cache["data"] = []
        _kalender_cache["fetched_at"] = now
        return []

    header = raw[0]
    rows = raw[1:]
    events = []
    for row in rows:
        record = dict(zip(header, row))
        tgl_mulai = _parse_tanggal(record.get("tanggal_mulai"))
        tgl_selesai = _parse_tanggal(record.get("tanggal_selesai")) or tgl_mulai
        if not tgl_mulai:
            continue
        events.append({
            "tanggal_mulai_iso": tgl_mulai.isoformat(),
            "tanggal_selesai_iso": tgl_selesai.isoformat(),
            "keterangan": record.get("keterangan", ""),
            "kategori": record.get("kategori", ""),
        })

    _kalender_cache["data"] = events
    _kalender_cache["fetched_at"] = now
    return events

def get_kalender_by_date(tanggal_iso_str):
    """Ambil semua event kalender akademik yang mencakup tanggal tsb (untuk rentang tanggal)."""
    result = []
    for e in get_kalender_akademik():
        if e["tanggal_mulai_iso"] <= tanggal_iso_str <= e["tanggal_selesai_iso"]:
            result.append(e)
    return result


# PENGUMUMAN
def _get_pengumuman_service():
    creds_env = os.getenv("JADWAL_GOOGLE_CREDENTIALS_JSON")
    if not creds_env:
        raise RuntimeError("JADWAL_GOOGLE_CREDENTIALS_JSON tidak diset")

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
    range_name = f"{PENGUMUMAN_SHEET_NAME}!A:E"
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
        range=f"{PENGUMUMAN_SHEET_NAME}!A:E",
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
                {"range": f"{PENGUMUMAN_SHEET_NAME}!B{row}:C{row}", "values": [[title, desc]]},
                {"range": f"{PENGUMUMAN_SHEET_NAME}!E{row}", "values": [[updated_at]]},
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
        if s["properties"]["title"] == PENGUMUMAN_SHEET_NAME:
            sheet_id = s["properties"]["sheetId"]
            break
    if sheet_id is None:
        raise RuntimeError(f"Sheet {PENGUMUMAN_SHEET_NAME} tidak ditemukan")

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

