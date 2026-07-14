import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv

load_dotenv()

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
DRIVE_FOLDER_ID = os.getenv("PEMINJAMAN_ASET_DRIVE_FOLDER_ID")  # folder tujuan di Drive
TOKEN_FILE = os.getenv("TOKEN_FILE")


def _get_drive_service():
    creds = Credentials.from_authorized_user_file(
        TOKEN_FILE,
        DRIVE_SCOPES
    )

    # Refresh token otomatis jika access token sudah expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build(
        "drive",
        "v3",
        credentials=creds,
        cache_discovery=False
    )


def upload_file(local_path: str, mime_type: str, drive_filename: str = None) -> dict:
    """Upload satu file ke folder Drive yang ditentukan. Return dict {id, webViewLink}."""
    service = _get_drive_service()
    filename = drive_filename or os.path.basename(local_path)

    file_metadata = {"name": filename}
    if DRIVE_FOLDER_ID:
        file_metadata["parents"] = [DRIVE_FOLDER_ID]

    media = MediaFileUpload(local_path, mimetype=mime_type, resumable=False)
    
    uploaded = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id, webViewLink")
        .execute()
    )
    return uploaded


def upload_docx_and_pdf(docx_path: str, pdf_path: str, base_name: str) -> dict:
    docx_result = upload_file(
        docx_path,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        f"{base_name}.docx",
    )
    pdf_result = upload_file(pdf_path, "application/pdf", f"{base_name}.pdf")
    return {
        "docx_link": docx_result.get("webViewLink"),
        "pdf_link": pdf_result.get("webViewLink"),
    }

def delete_drive_file(file_id):
    if not file_id:
        return
    service = _get_drive_service()
    try:
        service.files().delete(fileId=file_id).execute()
    except Exception:
        pass  # file mungkin sudah terhapus manual, jangan blok proses