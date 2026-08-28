import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv
from google.oauth2 import service_account
from flask import current_app

load_dotenv()

# Upload dokumen aset peminjaman ke Google Drive
DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive']
DRIVE_FOLDER_ID = os.getenv("PEMINJAMAN_ASET_DRIVE_FOLDER_ID")  # folder tujuan di Drive
TOKEN_FILE = os.getenv("TOKEN_FILE")


def _get_drive_service():
    token_env = os.getenv("TOKEN_FILE")
    if not token_env:
        raise RuntimeError("TOKEN_FILE tidak diset")

    if token_env.strip().endswith(".json"):
        creds = Credentials.from_authorized_user_file(token_env, DRIVE_SCOPES)
    else:
        token_dict = json.loads(token_env)
        creds = Credentials.from_authorized_user_info(token_dict, DRIVE_SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        if token_env.strip().endswith(".json"):
            with open(token_env, "w") as token:
                token.write(creds.to_json())
        # else: serverless — token refreshed in-memory only, tidak persist
        # perlu simpan ke storage lain kalau mau persist across invocations

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload_file(local_path: str, mime_type: str, drive_filename: str = None) -> dict:
    service = _get_drive_service()
    filename = drive_filename or os.path.basename(local_path)

    folder_id = DRIVE_FOLDER_ID.strip() if DRIVE_FOLDER_ID else None
    file_metadata = {"name": filename}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaFileUpload(local_path, mimetype=mime_type, resumable=False)
    uploaded = (
        service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink",
            supportsAllDrives=True,
            supportsTeamDrives=True
        )
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