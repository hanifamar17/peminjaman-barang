import os
import json
import time
from google.oauth2 import service_account
from googleapiclient.discovery import build


JADWAL_PELAJARAN_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
JADWAL_PELAJARAN_SPREADSHEET_ID = os.getenv("JADWAL_PELAJARAN_SPREADSHEET_ID")

# nama sheet per tab
SHEET_KELAS = os.getenv("JADWAL_SHEET_KELAS", "Kelas")
SHEET_GURU_MAPEL = os.getenv("JADWAL_SHEET_GURU_MAPEL", "Guru_Mapel")
SHEET_JADWAL = os.getenv("JADWAL_SHEET_JADWAL", "Jadwal")
SHEET_EKSKUL = os.getenv("JADWAL_SHEET_EKSKUL", "Ekstrakurikuler")
SHEET_JUMAT_BERKAH = os.getenv("JADWAL_SHEET_JUMAT_BERKAH", "Jumat_Berkah")
SHEET_GURU_PIKET = os.getenv("JADWAL_SHEET_GURU_PIKET", "Guru_Piket")

_cache = {"data": None, "fetched_at": None}
CACHE_TTL_SECONDS = int(os.getenv("JADWAL_PELAJARAN_CACHE_TTL", "120"))


def _get_jadwal_pelajaran_service():
    creds_env = os.getenv("JADWAL_GOOGLE_CREDENTIALS_JSON")
    if not creds_env:
        raise RuntimeError("JADWAL_GOOGLE_CREDENTIALS_JSON tidak diset")

    if creds_env.strip().endswith(".json"):
        creds = service_account.Credentials.from_service_account_file(
            creds_env, scopes=JADWAL_PELAJARAN_SCOPES
        )
    else:
        creds_dict = json.loads(creds_env)
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=JADWAL_PELAJARAN_SCOPES
        )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _sheet_range(sheet_name):
    return f"{sheet_name}!A:Z"


def _rows_to_dicts(values):
    if not values:
        return []
    header = values[0]
    out = []
    for row in values[1:]:
        row = row + [None] * (len(header) - len(row))  # pad kolom kosong
        out.append(dict(zip(header, row)))
    return out


def _fetch_all_sheets():
    service = _get_jadwal_pelajaran_service()
    sheet = service.spreadsheets().values()

    ranges = [
        _sheet_range(SHEET_KELAS),
        _sheet_range(SHEET_GURU_MAPEL),
        _sheet_range(SHEET_JADWAL),
        _sheet_range(SHEET_JUMAT_BERKAH),
        _sheet_range(SHEET_GURU_PIKET),
    ]

    resp = sheet.batchGet(
        spreadsheetId=JADWAL_PELAJARAN_SPREADSHEET_ID,
        ranges=ranges,
    ).execute()

    vr = resp.get("valueRanges", [])
    data = {
        "kelas": _rows_to_dicts(vr[0].get("values", [])),
        "guru_mapel": _rows_to_dicts(vr[1].get("values", [])),
        "jadwal": _rows_to_dicts(vr[2].get("values", [])),
        "jumat_berkah": _rows_to_dicts(vr[3].get("values", [])),
        "guru_piket": _rows_to_dicts(vr[4].get("values", [])),
    }
    return data


def get_jadwal_pelajaran_data(force_refresh=False):
    now = time.time()
    if (
        not force_refresh
        and _cache["data"] is not None
        and _cache["fetched_at"] is not None
        and (now - _cache["fetched_at"]) < CACHE_TTL_SECONDS
    ):
        return _cache["data"]

    data = _fetch_all_sheets()
    data["piket_per_hari"] = _build_piket_per_hari(data["guru_piket"])
    data["wali_kelas_map"] = _build_wali_kelas_map(data["kelas"])
    _cache["data"] = data
    _cache["fetched_at"] = now
    return data


def get_jadwal_by_hari(hari):
    data = get_jadwal_pelajaran_data()
    hari = hari.upper()
    return [row for row in data["jadwal"] if (row.get("hari") or "").upper() == hari]


def get_jadwal_by_kelas(nama_kelas):
    data = get_jadwal_pelajaran_data()
    return [row for row in data["jadwal"] if row.get("nama_kelas") == nama_kelas]

def _build_piket_per_hari(guru_piket_rows):
    out = {}
    for r in guru_piket_rows:
        hari = (r.get("Hari") or "").strip().upper()
        nama = r.get("Nama")
        if not hari or not nama:
            continue
        out.setdefault(hari, []).append(nama)
    return out

def _build_wali_kelas_map(kelas_rows):
    return {
        (r.get("nama_kelas") or "").strip(): r.get("wali_kelas")
        for r in kelas_rows
        if r.get("nama_kelas")
    }



