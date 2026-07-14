from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/drive"
]

flow = InstalledAppFlow.from_client_secrets_file(
    "./creds/client_secret_peminjaman_aset_creds.json",
    SCOPES
)

creds = flow.run_local_server(port=0)

with open("creds/token.json", "w") as token:
    token.write(creds.to_json())

print("Token berhasil dibuat")