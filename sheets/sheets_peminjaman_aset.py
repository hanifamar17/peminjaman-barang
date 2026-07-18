import os
import json
import datetime
import logging
import time
from google.oauth2 import service_account
from googleapiclient.discovery import build
from peminjaman_aset.drive_uploader import _get_drive_service

logger = logging.getLogger(__name__)

ASET_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]  # perlu write access
ASET_SPREADSHEET_ID = os.getenv("ASET_SPREADSHEET_ID")
ASET_SHEET_NAME = os.getenv("ASET_SHEET_NAME")
INV_SHEET_NAME = os.getenv("INV_SHEET_NAME", "inventory")

_inventaris_cache = {"data": None, "ts": 0}
CACHE_TTL = 30  # detik


def _get_service():
    creds_env = os.getenv("ASET_GOOGLE_CREDENTIALS_JSON")
    if not creds_env:
        raise RuntimeError("ASET_GOOGLE_CREDENTIALS_JSON tidak diset")
    if creds_env.strip().endswith(".json"):
        creds = service_account.Credentials.from_service_account_file(
            creds_env, scopes=ASET_SCOPES
        )
    else:
        creds_dict = json.loads(creds_env)
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=ASET_SCOPES
        )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)

def get_sheet_headers():
    """Helper kecil: ambil header baris pertama sheet, dipakai berulang di atas."""
    service = _get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=ASET_SPREADSHEET_ID,
        range=f"{ASET_SHEET_NAME}!A1:Z1",
    ).execute()
    return result.get("values", [[]])[0]

# Urutan kolom di sheet -- SESUAIKAN header baris pertama sheet kalian
# supaya urutannya sama persis dengan list `row` di bawah:
# record_id | timestamp | nomor_surat | nama | jenis_kelamin | pekerjaan |
# alamat | telepon | no_identitas | tujuan | lokasi_penggunaan | tgl_pinjam |
# tgl_kembali | nama_petugas | jaminan_identitas | jenis_identitas_jaminan |
# jaminan_surat | pdf_id | pdf_link

def _col_letter(idx):
    """0-based index -> kolom sheet (A, B, ..., Z, AA, AB, ...)"""
    letters = ""
    idx += 1
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters

# ==== Helper: batch kurangi stok inventaris ====
def deduct_inventaris_stock(item_deductions):
    """
    item_deductions: list of dict {"id": "INV-0001", "jumlah": 2}
    Return: (success: bool, error_message: str or None)
    """
    service = _get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=ASET_SPREADSHEET_ID,
        range=f"{INV_SHEET_NAME}!A:Z",
    ).execute()
    rows = result.get("values", [])
    if len(rows) < 2:
        return False, "Data inventaris kosong"

    headers = rows[0]
    try:
        idx_id = headers.index("id")
        idx_total = headers.index("jumlah_total")
        idx_dipinjam = headers.index("jumlah_dipinjam")
    except ValueError:
        return False, "Struktur sheet inventory tidak sesuai (kolom id/jumlah_total/jumlah_dipinjam hilang)"

    row_map = {}
    for i, row in enumerate(rows[1:], start=2):
        if row and len(row) > idx_id:
            row_map[row[idx_id]] = (i, row)

    updates = []
    for ded in item_deductions:
        item_id = ded["id"]
        jumlah_pinjam = ded["jumlah"]

        if item_id not in row_map:
            return False, f"Barang dengan id {item_id} tidak ditemukan di inventaris"

        row_index, row = row_map[item_id]

        try:
            total = int(row[idx_total]) if len(row) > idx_total and row[idx_total] else 0
            dipinjam = int(row[idx_dipinjam]) if len(row) > idx_dipinjam and row[idx_dipinjam] else 0
        except ValueError:
            return False, f"Data stok barang {item_id} tidak valid"

        tersedia = total - dipinjam
        if jumlah_pinjam > tersedia:
            nama = row[headers.index("nama_barang")] if "nama_barang" in headers else item_id
            return False, f"Stok {nama} tidak cukup (tersedia: {tersedia}, diminta: {jumlah_pinjam})"

        new_dipinjam = dipinjam + jumlah_pinjam
        col_letter = _col_letter(idx_dipinjam)  # aman untuk kolom >26
        updates.append({
            "range": f"{INV_SHEET_NAME}!{col_letter}{row_index}",
            "values": [[str(new_dipinjam)]],
        })

    if not updates:
        return True, None

    try:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=ASET_SPREADSHEET_ID,
            body={"valueInputOption": "RAW", "data": updates},
        ).execute()
    except Exception as e:
        logger.error(f"Gagal batchUpdate stok inventaris: {e}")
        return False, "Gagal mengurangi stok, coba lagi"

    # invalidate cache biar search berikutnya dapat stok terbaru
    _inventaris_cache["data"] = None

    return True, None

def append_peminjaman(record_id, data, pdf_file):
    """
    pdf_file: dict dengan "id" dan "webViewLink".
    Saat submit awal (belum generate PDF), kirim {"id": "", "webViewLink": ""}.
    barang disimpan sebagai JSON string supaya bisa dipakai lagi saat
    generate PDF ditunda (tombol generate di halaman ringkasan).
    """
    service = _get_service()
    row = [
        record_id,
        datetime.datetime.now().isoformat(),
        data["nomor_surat"],
        data["nama"],
        data["jenis_kelamin"],
        data["pekerjaan"],
        data["alamat"],
        data["telepon"],
        data["no_identitas"],
        data["tujuan"],
        data["lokasi_penggunaan"],
        data["tgl_pinjam"],
        data["tgl_kembali"],
        data["kota"],
        data["tgl_surat"],
        data["nama_petugas"],
        data["jaminan_identitas"],
        data["jenis_identitas_jaminan"],
        data["jaminan_surat"],
        json.dumps(data["barang"], ensure_ascii=False),
        pdf_file.get("id", ""),
        pdf_file.get("webViewLink", ""),
    ]
    service.spreadsheets().values().append(
        spreadsheetId=ASET_SPREADSHEET_ID,
        range=f"{ASET_SHEET_NAME}!A:Z",
        valueInputOption="RAW",
        body={"values": [row]},
    ).execute()
 
 
def find_row_by_id(record_id):
    service = _get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=ASET_SPREADSHEET_ID,
        range=f"{ASET_SHEET_NAME}!A:Z",
    ).execute()
    rows = result.get("values", [])
    for i, row in enumerate(rows):
        if row and row[0] == record_id:
            return i + 1, row  # 1-indexed, baris 1 = header
    return None, None
 
 
def get_all_peminjaman():
    service = _get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=ASET_SPREADSHEET_ID,
        range=f"{ASET_SHEET_NAME}!A:Z",
    ).execute()
    rows = result.get("values", [])
    if len(rows) < 2:
        return []
    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:]]


def get_last_sequence_this_month() -> int:
    """
    Hitung jumlah surat peminjaman aset yang sudah terbit di bulan & tahun
    berjalan, berdasarkan kolom 'timestamp' (waktu submit, bukan tgl_surat
    manual -- lebih akurat karena selalu terisi otomatis).
    """
    now = datetime.datetime.now()
    prefix = f"{now.year}-{now.month:02d}"
    rows = get_all_peminjaman()
    return sum(1 for r in rows if r.get("timestamp", "").startswith(prefix))

def update_row(row_index, updated_row):
    service = _get_service()
    service.spreadsheets().values().update(
        spreadsheetId=ASET_SPREADSHEET_ID,
        range=f"{ASET_SHEET_NAME}!A{row_index}:Z{row_index}",
        valueInputOption="RAW",
        body={"values": [updated_row]},
    ).execute()

# Inventaris aset (barang) -- sheet terpisah dari peminjaman, tapi masih di spreadsheet yang sama
def _next_id():
    rows = get_all_inventaris()
    nums = []
    for r in rows:
        try:
            nums.append(int(r["id"].split("-")[1]))
        except (IndexError, ValueError, KeyError):
            continue
    nxt = (max(nums) + 1) if nums else 1
    return f"INV-{nxt:04d}"
 

def get_all_inventaris():
    now = time.time()
    if _inventaris_cache["data"] is not None and (now - _inventaris_cache["ts"]) <= CACHE_TTL:
        return _inventaris_cache["data"]

    service = _get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=ASET_SPREADSHEET_ID,
        range=f"{INV_SHEET_NAME}!A:Z",
    ).execute()
    rows = result.get("values", [])
    if len(rows) < 2:
        data = []
    else:
        headers = rows[0]
        data = [dict(zip(headers, row)) for row in rows[1:]]
        for r in data:
            try:
                total = int(r.get("jumlah_total") or 0)
                dipinjam = int(r.get("jumlah_dipinjam") or 0)
            except ValueError:
                total, dipinjam = 0, 0
            r["jumlah_tersedia"] = max(total - dipinjam, 0)
            r["status"] = "Tersedia" if r["jumlah_tersedia"] > 0 else "Habis"

    _inventaris_cache["data"] = data
    _inventaris_cache["ts"] = now
    return data
 
 
def find_inventaris_by_id(item_id):
    service = _get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=ASET_SPREADSHEET_ID,
        range=f"{INV_SHEET_NAME}!A:Z",
    ).execute()
    rows = result.get("values", [])
    for i, row in enumerate(rows):
        if row and row[0] == item_id:
            return i + 1, row  # 1-indexed, row 1 = header
    return None, None
 
 
def search_inventaris(query, limit=10):
    """Dipakai untuk autocomplete di form peminjaman."""
    query = (query or "").strip().lower()
    if not query:
        return []

    rows = get_all_inventaris()
    matched = [
        r for r in rows
        if query in r.get("nama_barang", "").lower()
        or query in r.get("merk", "").lower()
        or query in r.get("sub_bidang", "").lower()
        or query in r.get("lokasi", "").lower()
    ]
    return matched[:limit]
 
 
def create_inventaris(data):
    service = _get_service()
    item_id = _next_id()
    now = datetime.datetime.now().isoformat()
    row = [
        item_id,
        data["nama_barang"],
        data.get("merk", ""),
        data.get("kondisi", "Baik"),
        data.get("lokasi", ""),
        data.get("tahun_pengadaan", ""),
        data.get("sumber_dana", ""),
        data.get("sub_bidang", ""),
        str(data.get("jumlah_total", 0)),
        "0",  # jumlah_dipinjam awal selalu 0
        now,
        now,
    ]
    service.spreadsheets().values().append(
        spreadsheetId=ASET_SPREADSHEET_ID,
        range=f"{INV_SHEET_NAME}!A:Z",
        valueInputOption="RAW",
        body={"values": [row]},
    ).execute()
    return item_id
 
 
def update_inventaris(item_id, data):
    row_index, row = find_inventaris_by_id(item_id)
    if row is None:
        return False
    jumlah_dipinjam = row[9] if len(row) > 9 else "0"  # pertahankan counter, jangan direset form edit
    updated_row = [
        item_id,
        data["nama_barang"],
        data.get("merk", ""),
        data.get("kondisi", "Baik"),
        data.get("lokasi", ""),
        data.get("tahun_pengadaan", ""),
        data.get("sumber_dana", ""),
        data.get("sub_bidang", ""),
        str(data.get("jumlah_total", 0)),
        jumlah_dipinjam,
        row[10] if len(row) > 10 else datetime.datetime.now().isoformat(),  # created_at asli
        datetime.datetime.now().isoformat(),  # last_updated
    ]
    service = _get_service()
    service.spreadsheets().values().update(
        spreadsheetId=ASET_SPREADSHEET_ID,
        range=f"{INV_SHEET_NAME}!A{row_index}:Z{row_index}",
        valueInputOption="RAW",
        body={"values": [updated_row]},
    ).execute()
    return True
 
 
def delete_inventaris(item_id, row_index=None):
    """
    Menghapus baris inventaris berdasarkan row_index dengan mencari GID secara otomatis
    menggunakan nama sheet yang diatur di INV_SHEET_NAME.
    """
    if row_index is None:
        row_index, row = find_inventaris_by_id(item_id)
        if row is None:
            return False

    service = _get_service()
    try:
        # 1. Ambil metadata spreadsheet untuk mencari GID berdasarkan nama tab (INV_SHEET_NAME)
        spreadsheet = service.spreadsheets().get(spreadsheetId=ASET_SPREADSHEET_ID).execute()
        sheet_id_gid = None
        
        for sheet in spreadsheet.get('sheets', []):
            if sheet['properties']['title'] == INV_SHEET_NAME:
                sheet_id_gid = sheet['properties']['sheetId']
                break
        
        # Jika nama tab tidak ditemukan di Google Sheets, hentikan proses
        if sheet_id_gid is None:
            print(f"Error: Tab dengan nama '{INV_SHEET_NAME}' tidak ditemukan di file Google Sheets Anda.")
            return False

        # 2. Eksekusi hapus baris menggunakan GID yang sudah ditemukan
        service.spreadsheets().batchUpdate(
            spreadsheetId=ASET_SPREADSHEET_ID,
            body={"requests": [{
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_id_gid,
                        "dimension": "ROWS",
                        "startIndex": row_index - 1, # Google API menggunakan 0-based index
                        "endIndex": row_index,
                    }
                }
            }]},
        ).execute()
        
        print(f"Berhasil menghapus baris ke-{row_index} pada tab '{INV_SHEET_NAME}' (GID: {sheet_id_gid})")
        return True
        
    except Exception as e:
        print(f"Error saat menghapus baris di Google Sheets: {e}")
        return False