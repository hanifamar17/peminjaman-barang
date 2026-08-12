import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
AKUN_SPREADSHEET_ID = os.getenv("AKUN_SPREADSHEET_ID")
SHEET_AKUN = os.getenv("SHEET_AKUN", "akun")

def get_service():
    creds_env = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not creds_env:
        raise RuntimeError("GOOGLE_CREDENTIALS_JSON tidak diset")

    # === PATH FILE (lokal) ===
    if creds_env.strip().endswith(".json"):
        creds = service_account.Credentials.from_service_account_file(
            creds_env,
            scopes=SCOPES
        )

    # === JSON STRING (Vercel) ===
    else:
        creds_dict = json.loads(creds_env)
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=SCOPES
        )

    return build(
        "sheets",
        "v4",
        credentials=creds,
        cache_discovery=False
    )

def read_auth_sheet(sheet_name, range_header=None):
    service = get_service()
    range_name = f"{sheet_name}!A:Z" if not range_header else f"{sheet_name}!{range_header}"
    result = service.spreadsheets().values().get(
        spreadsheetId=AKUN_SPREADSHEET_ID,
        range=range_name
    ).execute()
    return result.get("values", [])

def get_users():
    rows = read_auth_sheet(SHEET_AKUN)
    if not rows or len(rows) < 2:
        return []
    headers = [h.strip().lower() for h in rows[0]]
    return [dict(zip(headers, r)) for r in rows[1:]]
