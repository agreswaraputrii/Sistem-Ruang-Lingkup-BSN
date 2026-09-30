from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


# ============================================================
# PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

CREDENTIALS_DIR = BASE_DIR / "credentials"

CLIENT_FILE = CREDENTIALS_DIR / "oauth_client.json"

TOKEN_FILE = CREDENTIALS_DIR / "google_token.json"


# ============================================================
# GOOGLE PERMISSION
# ============================================================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly"
]


# ============================================================
# LOGIN GOOGLE
# ============================================================

def login_google():

    if not CLIENT_FILE.exists():

        print()
        print("ERROR")
        print("File oauth_client.json tidak ditemukan.")
        print()
        print("Lokasi yang dicari:")
        print(CLIENT_FILE)

        return


    CREDENTIALS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    print()
    print("Memulai login Google...")
    print("Browser akan terbuka.")
    print()


    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_FILE),
        SCOPES,
    )


    credentials = flow.run_local_server(
        port=0,
    )


    TOKEN_FILE.write_text(
        credentials.to_json(),
        encoding="utf-8",
    )


    print()
    print("========================================")
    print("LOGIN GOOGLE BERHASIL")
    print("========================================")
    print()
    print("Token berhasil disimpan di:")
    print(TOKEN_FILE)
    print()
    print(
        "Aplikasi sekarang memiliki izin "
        "untuk membaca Google Sheets."
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    login_google()