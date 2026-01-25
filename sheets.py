import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")


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

def read_sheet(sheet_name, range_header=None):
    service = get_service()
    range_name = f"{sheet_name}!A:Z" if not range_header else f"{sheet_name}!{range_header}"
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name
    ).execute()

    values = result.get('values', [])
    return values

def write_row(sheet_name, row):
    service = get_service()
    body = {'values': [row]}
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!A:Z",
        valueInputOption='RAW',
        body=body
    ).execute()

def update_cell_range(sheet_name, range_name, value):
    service = get_service()
    body = {'values': [[value]]}
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!{range_name}",
        valueInputOption='RAW',
        body=body
    ).execute()

# utility khusus inventory
def get_inventory():
    rows = read_sheet('inventory')
    if not rows: return []
    headers = rows[0]
    items = []
    for r in rows[1:]:
        d = dict(zip(headers, r))

        # ensure types
        d['stock'] = int(d.get('stock','0'))
        items.append(d)
    return items

def update_stock(item_id, delta):
    rows = read_sheet('inventory')
    if not rows:
        return False

    for idx, r in enumerate(rows[1:], start=2):
        if not r:
            continue

        # kolom A = item_id
        if r[0] == str(item_id):
            # kolom C = stock
            cur_stock = int(r[2]) if len(r) > 2 and r[2] else 0
            new_stock = max(0, cur_stock + int(delta))

            range_name = f"C{idx}"
            update_cell_range('inventory', range_name, new_stock)
            return True
    return False


def append_loan(loan_row):
    write_row('loans', loan_row)


def find_loan_by_code(code):
    rows = read_sheet('loans')
    if not rows: return None
    headers = rows[0]
    for r in rows[1:]:
        d = dict(zip(headers, r))
        if d.get('code') == code:
            return d
    return None 

def get_loan_with_items(code):
    rows = read_sheet("loans")
    if not rows:
        return None

    headers = rows[0]
    items = []
    loan_meta = None

    for r in rows[1:]:
        d = dict(zip(headers, r))

        if d.get("code") != code:
            continue

        # simpan metadata SATU KALI
        if not loan_meta:
            loan_meta = {
                "code": d.get("code"),
                "borrower_name": d.get("borrower_name"),
                "borrower_email": d.get("borrower_email"),
                "loan_date": d.get("loan_date"),
                "return_date": d.get("return_date"),
                "status": d.get("status"),
                "note": d.get("note"),
                "items": []
            }

        items.append({
            "item_id": d.get("item_id"),
            "item_name": d.get("item_name"),
            "qty": int(d.get("qty") or 0)
        })

    if not loan_meta:
        return None

    loan_meta["items"] = items
    return loan_meta

def update_loan_status(code, item_id, status, proof=''):
    rows = read_sheet('loans')
    headers = rows[0]

    code_idx = headers.index('code')
    item_idx = headers.index('item_id')
    status_idx = headers.index('status')
    proof_idx = headers.index('return_proof')

    for i, row in enumerate(rows[1:], start=2):
        if row[code_idx] == code and row[item_idx] == item_id:
            update_cell_range('loans', f'{chr(65+status_idx)}{i}', status)
            if proof:
                update_cell_range('loans', f'{chr(65+proof_idx)}{i}', proof)

