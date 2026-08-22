import os
import re
import uuid
import json
import time
from datetime import datetime, date, timezone, timedelta
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from googleapiclient.discovery import build

PERIZINAN_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
PERIZINAN_SPREADSHEET_ID = os.getenv("PERIZINAN_SPREADSHEET_ID")
SHEET_RIWAYAT = os.getenv("SHEET_RIWAYAT", "riwayat_perizinan")
SHEET_DURASI= os.getenv("SHEET_DURASI", "durasi_perizinan")
SHEET_PENGAJUAN= os.getenv("SHEET_PENGAJUAN", "pengajuan_perizinan")
SHEET_STATUS_PERIZINAN= os.getenv("SHEET_STATUS_PERIZINAN", "status_perizinan")
SHEET_SETTING = os.getenv("SHEET_SETTING", "setting_perizinan")
DEFAULT_JPL_MENIT = int(os.getenv("DEFAULT_JPL_MENIT", "50"))

DB_SISWA_SPREADSHEET_ID = os.getenv("DB_SISWA_SPREADSHEET_ID")
SHEET_DB_SISWA = os.getenv("SHEET_DB_SISWA", "data_siswa")
SHEET_DB_WALI_KELAS = os.getenv("SHEET_DB_WALI_KELAS", "wali_kelas")
JPL_PER_HARI = 10

_perizinan_cache = {"data": None, "fetched_at": None}
PERIZINAN_CACHE_TTL_SECONDS = int(os.getenv("PERIZINAN_CACHE_TTL", "120"))

ENUM_JENIS_KELAMIN = {"L", "P"}
ENUM_KELAS_UMUM = {str(i) for i in range(7, 13)}
ENUM_KELAS_DINIYYAH = {str(i) for i in range(1, 7)}
ENUM_STATUS_PETUGAS = {"guru", "wali_kelas", "pembimbing"}
ENUM_STATUS_PERIZINAN = {"disetujui", "selesai", "menunggu_acc", "ditolak", "dibatalkan"}
ENUM_DURASI = {"2_jpl", "4_jpl", "6_jpl", "8_jpl", "10_jpl", "1_hari", "lebih_1_hari"}
 
MAX_ALASAN = 200
MAX_NAMA = 100
MAX_PETUGAS = 100
MAX_CATATAN = 200

ROLE_WALI_KELAS = "wali_kelas"
ROLE_GURU = "guru"
ROLE_PEMBIMBING = "pembimbing"
ROLE_ADMIN = "admin"

 
# SANITASI & VALIDASI
def sanitize_text(value: str, max_len: int) -> str:
    """Strip formula-injection char di depan, trim panjang."""
    if value is None:
        return ""
    v = str(value).strip()
    if v and v[0] in ("=", "+", "-", "@"):
        v = "'" + v  # netralkan formula
    return v[:max_len]

def validate_enum(value, allowed: set, field_name: str):
    if value not in allowed:
        raise ValueError(f"{field_name} tidak valid: {value}. Harus salah satu dari {sorted(allowed)}")
 
def validate_nisn_format(nisn: str):
    if not re.fullmatch(r"\d{8}", str(nisn)):
        raise ValueError("nisn harus 8 digit angka")
 
def validate_tanggal(tanggal_str: str, max_hari_lampau: int = 7):
    try:
        tgl = datetime.strptime(tanggal_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("tanggal harus format YYYY-MM-DD")
    if tgl < (datetime.now().date() - timedelta(days=max_hari_lampau)):
        raise ValueError(f"tanggal tidak boleh lebih dari {max_hari_lampau} hari ke belakang")
    return tgl
 
def gen_id_perizinan(tanggal: str) -> str:
    tgl_compact = tanggal.replace("-", "")
    return f"PZ-{tgl_compact}-{uuid.uuid4().hex[:4].upper()}"
 
def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

 
# SHEET CLIENT
def _get_perizinan_service():
    creds_env = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not creds_env:
        raise RuntimeError("GOOGLE_CREDENTIALS_JSON tidak diset")
    if creds_env.strip().endswith(".json"):
        creds = service_account.Credentials.from_service_account_file(
            creds_env, scopes=PERIZINAN_SCOPES
        )
    else:
        creds_dict = json.loads(creds_env)
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=PERIZINAN_SCOPES
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
        row = row + [None] * (len(header) - len(row))
        out.append(dict(zip(header, row)))
    return out
 
def _get_header(spreadsheet_id, sheet_name):
    service = _get_perizinan_service()
    resp = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{sheet_name}!A1:Z1"
    ).execute()
    values = resp.get("values", [])
    return values[0] if values else []
 
def read_sheet(spreadsheet_id, sheet_name):
    service = _get_perizinan_service()
    resp = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=_sheet_range(sheet_name)
    ).execute()
    return _rows_to_dicts(resp.get("values", []))
 
def append_row(spreadsheet_id, sheet_name, row_dict):
    """row_dict: {header_name: value}. Kolom yg gak disebut diisi kosong sesuai urutan header."""
    header = _get_header(spreadsheet_id, sheet_name)
    row = [row_dict.get(h, "") for h in header]
    service = _get_perizinan_service()
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=_sheet_range(sheet_name),
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()
 
def update_cells(spreadsheet_id, sheet_name, id_field, id_value, updates: dict):
    """Cari row dengan id_field==id_value, update kolom sesuai dict {header: value}."""
    service = _get_perizinan_service()
    resp = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=_sheet_range(sheet_name)
    ).execute()
    values = resp.get("values", [])
    if not values:
        raise ValueError("sheet kosong")
    header = values[0]
    if id_field not in header:
        raise ValueError(f"kolom {id_field} tidak ada")
    id_col = header.index(id_field)
 
    row_number = None
    for i, row in enumerate(values[1:], start=2):
        if len(row) > id_col and row[id_col] == id_value:
            row_number = i
            break
    if row_number is None:
        raise ValueError(f"{id_value} tidak ditemukan di {sheet_name}")
 
    data = []
    for field, val in updates.items():
        if field not in header:
            continue
        col_letter = _col_letter(header.index(field))
        data.append({"range": f"{sheet_name}!{col_letter}{row_number}", "values": [[val]]})
 
    if data:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": data},
        ).execute()
 
def _col_letter(idx0):
    """0-indexed -> huruf kolom (A, B, ..., Z, AA, ...)."""
    idx = idx0 + 1
    letters = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters
 
def _cache_valid():
    if _perizinan_cache["data"] is None or _perizinan_cache["fetched_at"] is None:
        return False
    age = (datetime.now() - _perizinan_cache["fetched_at"]).total_seconds()
    return age < PERIZINAN_CACHE_TTL_SECONDS
 
def get_data_siswa(force=False):
    if not force and _cache_valid():
        return _perizinan_cache["data"]
    records = read_sheet(DB_SISWA_SPREADSHEET_ID, SHEET_DB_SISWA)
    _perizinan_cache["data"] = records
    _perizinan_cache["fetched_at"] = datetime.now()
    return records

def get_list_kelas():
    try:
        rows = get_data_siswa()
    except Exception as e:
        print(f"[WARNING] Gagal membaca data siswa: {e}")
        return []

    kelas_set = {
        str(r.get("kelas_umum")).strip()
        for r in rows
        if r.get("kelas_umum")
    }

    def parse_kelas_key(val):
        # Ekstrak angka pertama dan sisa string
        match = re.match(r'^(\d+)\s*(.*)$', val)
        if match:
            num = int(match.group(1))
            suffix = match.group(2)
            return (0, num, suffix)
        return (1, 0, val)

    return sorted(list(kelas_set), key=parse_kelas_key)

def invalidate_cache():
    _perizinan_cache["data"] = None
    _perizinan_cache["fetched_at"] = None
 
def find_siswa_by_nisn(nisn: str):
    for row in get_data_siswa():
        if str(row.get("nisn")) == str(nisn):
            return row
    return None

 
# WALI KELAS LOOKUP
_wali_kelas_cache = {"data": None, "fetched_at": None}
 
_ROMAWI_KE_ARAB = {"VII": "7", "VIII": "8", "IX": "9", "X": "10", "XI": "11", "XII": "12"}
_ARAB_KE_ROMAWI = {v: k for k, v in _ROMAWI_KE_ARAB.items()}
 
def _varian_kelas(kelas: str) -> set:
    """'11 SOS1' -> {'11 SOS1', 'XI SOS1'}. Support arab & romawi dua arah."""
    kelas = re.sub(r"\s+", " ", kelas.strip().upper())
    if not kelas:
        return set()
    token, _, sisa = kelas.partition(" ")
    varian = {kelas}
    if token in _ARAB_KE_ROMAWI:
        varian.add(f"{_ARAB_KE_ROMAWI[token]} {sisa}".strip())
    elif token in _ROMAWI_KE_ARAB:
        varian.add(f"{_ROMAWI_KE_ARAB[token]} {sisa}".strip())
    return varian
 
def get_wali_kelas_map(force=False):
    if not force and _wali_kelas_cache["data"] is not None and _wali_kelas_cache["fetched_at"] is not None \
            and (time.time() - _wali_kelas_cache["fetched_at"]) < PERIZINAN_CACHE_TTL_SECONDS:
        return _wali_kelas_cache["data"]
    rows = read_sheet(DB_SISWA_SPREADSHEET_ID, SHEET_DB_WALI_KELAS)
    data = {}
    for r in rows:
        kelas_raw = str(r.get("kelas", "")).strip()
        if not kelas_raw:
            continue
        nama = r.get("nama_wali_kelas", "")
        for varian in _varian_kelas(kelas_raw):
            data[varian] = nama
    _wali_kelas_cache["data"] = data
    _wali_kelas_cache["fetched_at"] = time.time()
    return data
 
def get_wali_kelas_untuk_siswa(siswa: dict):
    kelas = str(siswa.get("kelas_umum", "")).strip()
    wali_map = get_wali_kelas_map()
    for varian in _varian_kelas(kelas):
        if varian in wali_map:
            return wali_map[varian]
    return ""
 
 
# VALIDASI JAM/TANGGAL MULAI-SELESAI
def validate_jam(jam_str, field_name="jam"):
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", jam_str or ""):
        raise ValueError(f"{field_name} harus format HH:MM")
 
def validate_rentang_manual(tanggal_mulai, jam_mulai, tanggal_selesai, jam_selesai):
    """Validasi format + selesai >= mulai. Gak ngitung durasi apapun, murni input user."""
    validate_tanggal(tanggal_mulai)
    validate_tanggal(tanggal_selesai)
    validate_jam(jam_mulai, "jam_mulai")
    validate_jam(jam_selesai, "jam_selesai")
    mulai = datetime.strptime(f"{tanggal_mulai} {jam_mulai}", "%Y-%m-%d %H:%M")
    selesai = datetime.strptime(f"{tanggal_selesai} {jam_selesai}", "%Y-%m-%d %H:%M")
    if selesai <= mulai:
        raise ValueError("tanggal/jam selesai harus setelah tanggal/jam mulai")
 
def check_duplikat_aktif(nisn, tanggal, durasi):
    for row in read_sheet(PERIZINAN_SPREADSHEET_ID, SHEET_RIWAYAT):
        if (str(row.get("nisn")) == str(nisn)
                and row.get("tanggal") == tanggal
                and str(row.get("durasi")) == str(durasi)
                and row.get("status_perizinan") == "aktif"):
            return True
    return False
 
# SIMPLE RATE LIMIT (in-memory, per session)
_rate_limit_store = {}
RATE_LIMIT_WINDOW = 60  # detik
RATE_LIMIT_MAX = 10
 
# DOMAIN FUNCTIONS
def get_izin_aktif_hari_ini():
    today = datetime.now().strftime("%Y-%m-%d")
    rows = [r for r in read_sheet(PERIZINAN_SPREADSHEET_ID, SHEET_RIWAYAT)
            if r.get("tanggal") == today and r.get("status_perizinan") == "aktif"]
    return today, rows
 
def get_riwayat(kelas=None, bulan=None):
    rows = read_sheet(PERIZINAN_SPREADSHEET_ID, SHEET_RIWAYAT)
    if kelas:
        siswa_kelas = {str(s["nisn"]) for s in get_data_siswa() if str(s.get("kelas_umum")) == str(kelas)}
        rows = [r for r in rows if str(r.get("nisn")) in siswa_kelas]
    if bulan:
        rows = [r for r in rows if str(r.get("tanggal", "")).startswith(bulan)]
    return rows
 
def get_riwayat_detail(id_perizinan):
    return next((r for r in read_sheet(PERIZINAN_SPREADSHEET_ID, SHEET_RIWAYAT)
                 if r.get("id_perizinan") == id_perizinan), None)
 
def get_surat_data(id_perizinan):
    return get_riwayat_detail(id_perizinan)
 
def simpan_perizinan_langsung(row: dict):
    append_row(PERIZINAN_SPREADSHEET_ID, SHEET_RIWAYAT, row)
    invalidate_cache()
 
def simpan_pengajuan(row: dict):
    append_row(PERIZINAN_SPREADSHEET_ID, SHEET_PENGAJUAN, row)
    invalidate_cache()
 
def get_pengajuan(filter_status="semua"):
    rows = read_sheet(PERIZINAN_SPREADSHEET_ID, SHEET_PENGAJUAN)
    if filter_status != "semua":
        rows = [r for r in rows if r.get("status_perizinan") == filter_status]
    return rows

def get_pengajuan_detail(id_perizinan):
    return next((r for r in read_sheet(PERIZINAN_SPREADSHEET_ID, SHEET_PENGAJUAN)
                 if r.get("id_perizinan") == id_perizinan), None)
  
def proses_acc(id_perizinan, aksi, catatan, target_row=None, **kwargs):
    ts = now_iso()
    
    if not target_row:
        target_row = get_pengajuan_detail(id_perizinan) or {}

    if not target_row:
        raise ValueError("Data pengajuan tidak ditemukan.")

    if aksi == "approve":
        new_status = "aktif"
        
        # Payload lengkap dengan kolom jam & tanggal
        payload_riwayat = {
            "id_perizinan": target_row.get("id_perizinan", id_perizinan),
            "nisn": target_row.get("nisn"),
            "nama_siswa": target_row.get("nama_siswa"),
            "tanggal": target_row.get("tanggal"),
            "durasi": target_row.get("durasi"),
            "alasan": target_row.get("alasan"),
            "petugas": target_row.get("petugas"),
            "status_petugas": target_row.get("status_petugas"),
            "status_perizinan": "aktif",
            "jam_mulai": target_row.get("jam_mulai"),
            "tanggal_mulai": target_row.get("tanggal_mulai"),
            "jam_selesai": target_row.get("jam_selesai"),
            "tanggal_selesai": target_row.get("tanggal_selesai"),
            "wali_kelas_tujuan": target_row.get("wali_kelas_tujuan"),
            "tanggal_acc": ts,
            "catatan_wali_kelas": catatan,
            "created_at": target_row.get("created_at", ts),
            "updated_at": ts,
        }
        
        # Salin ke SHEET_RIWAYAT
        simpan_perizinan_langsung(payload_riwayat)
    else:
        new_status = "ditolak"

    # Update status di SHEET_PENGAJUAN
    update_cells(PERIZINAN_SPREADSHEET_ID, SHEET_PENGAJUAN, "id_perizinan", id_perizinan, {
        "status_perizinan": new_status,
        "tanggal_acc": ts,
        "catatan_wali_kelas": catatan,
        "updated_at": ts,
    })
    
    invalidate_cache()
    
    return {
        "success": True,
        "status": new_status,
        "message": f"Pengajuan berhasil diproses: {new_status}"
    }
 
def rate_limit_check(key: str):
    now = datetime.now()
    hist = _rate_limit_store.get(key, [])
    hist = [t for t in hist if (now - t).total_seconds() < RATE_LIMIT_WINDOW]
    if len(hist) >= RATE_LIMIT_MAX:
        raise ValueError("Terlalu banyak submit, coba lagi beberapa saat lagi")
    hist.append(now)
    _rate_limit_store[key] = hist

