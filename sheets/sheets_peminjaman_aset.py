import os
import json
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from peminjaman_aset.drive_uploader import _get_drive_service

ASET_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]  # perlu write access
ASET_SPREADSHEET_ID = os.getenv("ASET_SPREADSHEET_ID")
ASET_SHEET_NAME = os.getenv("ASET_SHEET_NAME")
INV_SHEET_NAME = os.getenv("INV_SHEET_NAME", "inventory")


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
    service = _get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=ASET_SPREADSHEET_ID,
        range=f"{INV_SHEET_NAME}!A:Z",
    ).execute()
    rows = result.get("values", [])
    if len(rows) < 2:
        return []
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