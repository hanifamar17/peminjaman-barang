import os
import json
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

# =========================
# KONFIGURASI TERPISAH UNTUK JADWAL BOOKING RUANGAN
# Spreadsheet & service account BEDA dari sheets.py (inventory/peminjaman)
# =========================
JADWAL_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
JADWAL_SPREADSHEET_ID = os.getenv("JADWAL_SPREADSHEET_ID")
JADWAL_SHEET_NAME = os.getenv("JADWAL_SHEET_NAME", "Form Responses 1")

# Cache sederhana in-memory supaya tidak fetch ke Sheets API setiap request
_cache = {"data": None, "fetched_at": None}
CACHE_TTL_SECONDS = int(os.getenv("JADWAL_CACHE_TTL", "120"))  # default 2 menit


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
            return datetime.datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None

def get_jadwal(force_refresh=False):
    """
    Ambil data jadwal dari 'Form Responses 1', hasil sudah diparse.
    Menggunakan cache in-memory (TTL) agar hemat kuota Sheets API.
    """
    now = datetime.datetime.now()
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