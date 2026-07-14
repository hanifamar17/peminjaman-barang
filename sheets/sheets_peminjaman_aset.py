import os
import json
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from peminjaman_aset.drive_uploader import _get_drive_service

ASET_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]  # perlu write access
ASET_SPREADSHEET_ID = os.getenv("ASET_SPREADSHEET_ID")
ASET_SHEET_NAME = os.getenv("ASET_SHEET_NAME")


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