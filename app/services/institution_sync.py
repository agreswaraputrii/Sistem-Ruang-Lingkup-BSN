import os
import re

from datetime import (
    datetime,
    timedelta,
)

from pathlib import Path

import gspread

from dotenv import load_dotenv

from google.auth.transport.requests import Request

from google.oauth2.credentials import Credentials

from app.database import get_connection


# ============================================================
# PATH
# ============================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
    .parent
)

ENV_FILE = BASE_DIR / ".env"

load_dotenv(
    ENV_FILE
)


# ============================================================
# GOOGLE CONFIG
# ============================================================

GOOGLE_MASTER_SHEET_ID = os.getenv(
    "GOOGLE_MASTER_SHEET_ID"
)

GOOGLE_MASTER_LSPRO_SHEET_NAME = os.getenv(
    "GOOGLE_MASTER_LSPRO_SHEET_NAME",
    "LSPro",
)

GOOGLE_MASTER_ACCR_DATE_SHEET_NAME = os.getenv(
    "GOOGLE_MASTER_ACCR_DATE_SHEET_NAME",
    "Accr_date",
)


GOOGLE_DIRECTORY_SHEET_ID = os.getenv(
    "GOOGLE_DIRECTORY_SHEET_ID"
)

GOOGLE_LSPR_AMENDMENT_SHEET_NAME = os.getenv(
    "GOOGLE_LSPR_AMENDMENT_SHEET_NAME",
    "LSPr edit",
)

GOOGLE_LSBU_AMENDMENT_SHEET_NAME = os.getenv(
    "GOOGLE_LSBU_AMENDMENT_SHEET_NAME",
    "LSBU",
)


GOOGLE_OAUTH_TOKEN_FILE = os.getenv(
    "GOOGLE_OAUTH_TOKEN_FILE",
    "credentials/google_token.json",
)

TOKEN_FILE = (
    BASE_DIR
    / GOOGLE_OAUTH_TOKEN_FILE
)


# ============================================================
# GOOGLE SCOPE
# ============================================================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly"
]


# ============================================================
# SYNC LOCK
# ============================================================

SYNC_LOCK_NAME = "MASTER_LEMBAGA"

SYNC_LOCK_TIMEOUT_MINUTES = 15


# ============================================================
# EXPECTED COLUMN - LSPRO
# ============================================================

EXPECTED_LSPRO_COLUMNS = [
    "ID_LSPro",
    "Name_LSPro",
    "Address",
    "Kab_Kota",
    "Propinsi",
    "Kode_Pos",
    "Telp",
    "Fax",
    "Email",
    "CP",
    "NoHpCP",
]


# ============================================================
# EXPECTED COLUMN - ACCR_DATE
# ============================================================

EXPECTED_ACCR_COLUMNS = [
    "ID_LSPro",
    "DATE_Accreditation",
    "DATE_End_of_Accreditation",
    "Status_accreditation",
]


# ============================================================
# DATABASE FIELD
# ============================================================

SYNC_FIELDS = [
    "name_lspro",
    "date_start_accreditation",
    "date_end_accreditation",
    "status_accreditation",
    "address",
    "kab_kota",
    "propinsi",
    "kode_pos",
    "telp",
    "fax",
    "email",
    "cp",
    "no_hp_cp",
]


# ============================================================
# CUSTOM ERROR
# ============================================================

class SyncBusyError(Exception):
    pass


# ============================================================
# HELPER
# ============================================================

def nullable_text(value):

    if value is None:
        return None

    value = str(
        value
    ).strip()

    if value == "":
        return None

    if value == "-":
        return None

    return value


def normalize_institution_id(
    value,
):

    value = nullable_text(
        value
    )

    if value is None:
        return None

    return value.strip()


def get_row_value(
    row,
    index,
):

    if index >= len(row):
        return None

    return nullable_text(
        row[index]
    )


# ============================================================
# SYNC LOCK STATUS
# ============================================================

def get_sync_lock_status():

    conn = get_connection()

    try:

        row = conn.execute(
            """
            SELECT
                is_locked,
                locked_at,
                locked_by

            FROM sync_lock

            WHERE lock_name = ?
            """,
            (
                SYNC_LOCK_NAME,
            ),
        ).fetchone()


        if row is None:

            return {
                "is_locked": False,
                "locked_at": None,
                "locked_by": None,
            }


        return {
            "is_locked":
                bool(
                    row["is_locked"]
                ),

            "locked_at":
                row["locked_at"],

            "locked_by":
                row["locked_by"],
        }


    finally:

        conn.close()


# ============================================================
# ACQUIRE LOCK
# ============================================================

def acquire_sync_lock():

    conn = get_connection()

    now = datetime.now()

    now_text = now.strftime(
        "%Y-%m-%d %H:%M:%S"
    )


    try:

        conn.execute(
            "BEGIN IMMEDIATE"
        )


        row = conn.execute(
            """
            SELECT
                is_locked,
                locked_at

            FROM sync_lock

            WHERE lock_name = ?
            """,
            (
                SYNC_LOCK_NAME,
            ),
        ).fetchone()


        if row is None:

            conn.execute(
                """
                INSERT INTO sync_lock (
                    lock_name,
                    is_locked,
                    locked_at,
                    locked_by
                )

                VALUES (
                    ?,
                    1,
                    ?,
                    'TEAM'
                )
                """,
                (
                    SYNC_LOCK_NAME,
                    now_text,
                ),
            )

            conn.commit()

            return


        if row["is_locked"]:

            lock_is_stale = False


            if row["locked_at"]:

                try:

                    locked_at = datetime.strptime(
                        row["locked_at"],
                        "%Y-%m-%d %H:%M:%S",
                    )

                    stale_after = (
                        locked_at
                        + timedelta(
                            minutes=(
                                SYNC_LOCK_TIMEOUT_MINUTES
                            )
                        )
                    )

                    if now >= stale_after:

                        lock_is_stale = True


                except ValueError:

                    lock_is_stale = True


            else:

                lock_is_stale = True


            if not lock_is_stale:

                conn.rollback()

                raise SyncBusyError(
                    "Sinkronisasi sedang dilakukan "
                    "oleh pengguna lain. "
                    "Silakan tunggu sampai selesai."
                )


        conn.execute(
            """
            UPDATE sync_lock

            SET
                is_locked = 1,
                locked_at = ?,
                locked_by = 'TEAM'

            WHERE lock_name = ?
            """,
            (
                now_text,
                SYNC_LOCK_NAME,
            ),
        )


        conn.commit()


    except SyncBusyError:

        raise


    except Exception:

        conn.rollback()

        raise


    finally:

        conn.close()


# ============================================================
# RELEASE LOCK
# ============================================================

def release_sync_lock():

    conn = get_connection()

    try:

        conn.execute(
            """
            UPDATE sync_lock

            SET
                is_locked = 0,
                locked_at = NULL,
                locked_by = NULL

            WHERE lock_name = ?
            """,
            (
                SYNC_LOCK_NAME,
            ),
        )

        conn.commit()


    except Exception:

        conn.rollback()

        raise


    finally:

        conn.close()


# ============================================================
# GOOGLE CREDENTIAL
# ============================================================

def get_google_credentials():

    if not TOKEN_FILE.exists():

        raise RuntimeError(
            "google_token.json tidak ditemukan. "
            "Jalankan OAuth login terlebih dahulu."
        )


    credentials = (
        Credentials
        .from_authorized_user_file(
            str(
                TOKEN_FILE
            ),
            SCOPES,
        )
    )


    if (
        credentials.expired
        and credentials.refresh_token
    ):

        credentials.refresh(
            Request()
        )


        TOKEN_FILE.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )


    if not credentials.valid:

        raise RuntimeError(
            "Token Google tidak valid."
        )


    return credentials


# ============================================================
# GOOGLE CLIENT
# ============================================================

def get_google_client():

    credentials = (
        get_google_credentials()
    )

    return gspread.authorize(
        credentials
    )


# ============================================================
# OPEN MASTER SPREADSHEET
# ============================================================

def get_master_spreadsheet(
    client,
):

    if not GOOGLE_MASTER_SHEET_ID:

        raise RuntimeError(
            "GOOGLE_MASTER_SHEET_ID "
            "belum diatur di .env"
        )


    return client.open_by_key(
        GOOGLE_MASTER_SHEET_ID
    )


# ============================================================
# OPEN DIRECTORY SPREADSHEET
# ============================================================

def get_directory_spreadsheet(
    client,
):

    if not GOOGLE_DIRECTORY_SHEET_ID:

        raise RuntimeError(
            "GOOGLE_DIRECTORY_SHEET_ID "
            "belum diatur di .env"
        )


    return client.open_by_key(
        GOOGLE_DIRECTORY_SHEET_ID
    )


# ============================================================
# READ LSPRO
# ============================================================

def read_lspro_data(
    master_spreadsheet,
):

    worksheet = (
        master_spreadsheet
        .worksheet(
            GOOGLE_MASTER_LSPRO_SHEET_NAME
        )
    )


    values = (
        worksheet
        .get_all_values()
    )


    if not values:

        raise RuntimeError(
            "Tab LSPro kosong."
        )


    headers = [
        str(item).strip()
        for item in values[0]
    ]


    missing_columns = [
        column

        for column in EXPECTED_LSPRO_COLUMNS

        if column not in headers
    ]


    if missing_columns:

        raise RuntimeError(
            "Kolom berikut tidak ditemukan "
            "di tab LSPro: "
            + ", ".join(
                missing_columns
            )
        )


    header_index = {
        name: index

        for index, name
        in enumerate(headers)
    }


    records = {}


    for row_number, row in enumerate(
        values[1:],
        start=2,
    ):

        id_lspro = (
            normalize_institution_id(
                get_row_value(
                    row,
                    header_index[
                        "ID_LSPro"
                    ],
                )
            )
        )


        if not id_lspro:

            continue


        # Hanya LSPr dan LSBU
        if not (
            id_lspro.upper().startswith(
                "LSPR-"
            )
            or
            id_lspro.upper().startswith(
                "LSBU-"
            )
        ):

            continue


        if id_lspro in records:

            raise RuntimeError(
                f"Duplikat ID_LSPro "
                f"di tab LSPro: "
                f"{id_lspro} "
                f"(baris {row_number})."
            )


        records[
            id_lspro
        ] = {

            "id_lspro":
                id_lspro,

            "name_lspro":
                get_row_value(
                    row,
                    header_index[
                        "Name_LSPro"
                    ],
                ),

            "address":
                get_row_value(
                    row,
                    header_index[
                        "Address"
                    ],
                ),

            "kab_kota":
                get_row_value(
                    row,
                    header_index[
                        "Kab_Kota"
                    ],
                ),

            "propinsi":
                get_row_value(
                    row,
                    header_index[
                        "Propinsi"
                    ],
                ),

            "kode_pos":
                get_row_value(
                    row,
                    header_index[
                        "Kode_Pos"
                    ],
                ),

            "telp":
                get_row_value(
                    row,
                    header_index[
                        "Telp"
                    ],
                ),

            "fax":
                get_row_value(
                    row,
                    header_index[
                        "Fax"
                    ],
                ),

            "email":
                get_row_value(
                    row,
                    header_index[
                        "Email"
                    ],
                ),

            "cp":
                get_row_value(
                    row,
                    header_index[
                        "CP"
                    ],
                ),

            "no_hp_cp":
                get_row_value(
                    row,
                    header_index[
                        "NoHpCP"
                    ],
                ),
        }


    return records


# ============================================================
# READ ACCREDITATION DATA
# ============================================================

def read_accreditation_data(
    master_spreadsheet,
):

    worksheet = (
        master_spreadsheet
        .worksheet(
            GOOGLE_MASTER_ACCR_DATE_SHEET_NAME
        )
    )


    values = (
        worksheet
        .get_all_values()
    )


    if not values:

        raise RuntimeError(
            "Tab Accr_date kosong."
        )


    headers = [
        str(item).strip()
        for item in values[0]
    ]


    missing_columns = [
        column

        for column in EXPECTED_ACCR_COLUMNS

        if column not in headers
    ]


    if missing_columns:

        raise RuntimeError(
            "Kolom berikut tidak ditemukan "
            "di tab Accr_date: "
            + ", ".join(
                missing_columns
            )
        )


    header_index = {
        name: index

        for index, name
        in enumerate(headers)
    }


    records = {}


    for row_number, row in enumerate(
        values[1:],
        start=2,
    ):

        id_lspro = (
            normalize_institution_id(
                get_row_value(
                    row,
                    header_index[
                        "ID_LSPro"
                    ],
                )
            )
        )


        if not id_lspro:

            continue


        if not (
            id_lspro.upper().startswith(
                "LSPR-"
            )
            or
            id_lspro.upper().startswith(
                "LSBU-"
            )
        ):

            continue


        if id_lspro in records:

            raise RuntimeError(
                f"Duplikat ID_LSPro "
                f"di tab Accr_date: "
                f"{id_lspro} "
                f"(baris {row_number})."
            )


        records[
            id_lspro
        ] = {

            "date_start_accreditation":
                get_row_value(
                    row,
                    header_index[
                        "DATE_Accreditation"
                    ],
                ),

            "date_end_accreditation":
                get_row_value(
                    row,
                    header_index[
                        "DATE_End_of_Accreditation"
                    ],
                ),

            "status_accreditation":
                get_row_value(
                    row,
                    header_index[
                        "Status_accreditation"
                    ],
                ),
        }


    return records


# ============================================================
# BUILD MASTER RECORD
# ============================================================

def build_master_records(
    master_spreadsheet,
):

    lspro_records = (
        read_lspro_data(
            master_spreadsheet
        )
    )


    accr_records = (
        read_accreditation_data(
            master_spreadsheet
        )
    )


    records = []


    for (
        id_lspro,
        institution_data,
    ) in lspro_records.items():


        accreditation_data = (
            accr_records.get(
                id_lspro
            )
        )


        if accreditation_data:

            date_start = (
                accreditation_data[
                    "date_start_accreditation"
                ]
            )

            date_end = (
                accreditation_data[
                    "date_end_accreditation"
                ]
            )

            status = (
                accreditation_data[
                    "status_accreditation"
                ]
            )


        else:

            date_start = None
            date_end = None
            status = None


        records.append(
            {

                "id_lspro":
                    id_lspro,

                "name_lspro":
                    institution_data[
                        "name_lspro"
                    ],

                "date_start_accreditation":
                    date_start,

                "date_end_accreditation":
                    date_end,

                "status_accreditation":
                    status,

                "address":
                    institution_data[
                        "address"
                    ],

                "kab_kota":
                    institution_data[
                        "kab_kota"
                    ],

                "propinsi":
                    institution_data[
                        "propinsi"
                    ],

                "kode_pos":
                    institution_data[
                        "kode_pos"
                    ],

                "telp":
                    institution_data[
                        "telp"
                    ],

                "fax":
                    institution_data[
                        "fax"
                    ],

                "email":
                    institution_data[
                        "email"
                    ],

                "cp":
                    institution_data[
                        "cp"
                    ],

                "no_hp_cp":
                    institution_data[
                        "no_hp_cp"
                    ],
            }
        )


    return records


# ============================================================
# STRICT AMENDMENT NUMBER
# ============================================================

def extract_amendment_number(
    value,
):

    value = nullable_text(
        value
    )


    if value is None:

        return None


    # ========================================================
    # PENTING:
    #
    # Hanya menerima jika TEKS DIMULAI dengan:
    #
    # Amendemen ke-1
    # Amandemen ke-1
    # Amendemen 1
    # Amandemen 1
    #
    # Tidak akan membaca judul seperti:
    #
    # "Helm ... Amandemen 1"
    #
    # ========================================================

    match = re.match(
        r"^\s*"
        r"(?:amendemen|amandemen)"
        r"\s*"
        r"(?:ke\s*[-:]?\s*)?"
        r"(\d+)",
        value,
        flags=re.IGNORECASE,
    )


    if not match:

        return None


    return int(
        match.group(1)
    )


# ============================================================
# BUILD LSPR ID
# ============================================================

def build_lspr_id_from_code(
    value,
):

    value = nullable_text(
        value
    )


    if value is None:

        return None


    if value.upper().startswith(
        "LSPR-"
    ):

        return value


    digits = re.sub(
        r"\D",
        "",
        value,
    )


    if digits == "":

        return None


    return (
        f"LSPr-"
        f"{digits.zfill(3)}"
        f"-IDN"
    )


# ============================================================
# CHECK LSPR AMENDMENT ROW
# ============================================================

def is_real_lspr_amendment_row(
    row,
):

    # ========================================================
    # Struktur LSPr edit:
    #
    # A = No LPK
    # B = No Urut Produk
    # C = Skema
    # D = Kategori
    # E = Sub Kategori
    # F = Jenis Produk
    # G = Nomor Acuan
    # H = Judul / Amendemen ke-X
    # I = Skema / tanggal amendment
    #
    # Amendment asli memiliki B:G kosong.
    # ========================================================

    no_lpk = get_row_value(
        row,
        0,
    )


    if not no_lpk:

        return False


    # B sampai G HARUS kosong.
    for index in range(
        1,
        7,
    ):

        if get_row_value(
            row,
            index,
        ):

            return False


    amendment_label = (
        get_row_value(
            row,
            7,
        )
    )


    amendment_date = (
        get_row_value(
            row,
            8,
        )
    )


    if not amendment_label:

        return False


    if not amendment_date:

        return False


    amendment_no = (
        extract_amendment_number(
            amendment_label
        )
    )


    if amendment_no is None:

        return False


    return True


# ============================================================
# READ LSPR AMENDMENTS
# ============================================================

def read_lspr_amendments(
    directory_spreadsheet,
):

    worksheet = (
        directory_spreadsheet
        .worksheet(
            GOOGLE_LSPR_AMENDMENT_SHEET_NAME
        )
    )


    values = (
        worksheet
        .get_all_values()
    )


    if not values:

        return []


    records = []

    seen = set()


    # Header ada di baris 2.
    # Data dimulai baris 3.
    for row_number, row in enumerate(
        values[2:],
        start=3,
    ):


        # ====================================================
        # HANYA BARIS AMENDMENT ASLI
        # ====================================================

        if not is_real_lspr_amendment_row(
            row
        ):

            continue


        no_lpk = (
            get_row_value(
                row,
                0,
            )
        )


        amendment_label = (
            get_row_value(
                row,
                7,
            )
        )


        amendment_date = (
            get_row_value(
                row,
                8,
            )
        )


        amendment_no = (
            extract_amendment_number(
                amendment_label
            )
        )


        id_lspro = (
            build_lspr_id_from_code(
                no_lpk
            )
        )


        if not id_lspro:

            raise RuntimeError(
                f"LSPr edit baris "
                f"{row_number}: "
                "No. LPK tidak dapat dibaca."
            )


        key = (
            id_lspro,
            amendment_no,
        )


        # ====================================================
        # DUPLICATE REAL AMENDMENT
        # ====================================================

        if key in seen:

            raise RuntimeError(
                "Duplikat Amandemen LSPr "
                "yang sebenarnya ditemukan: "
                f"{id_lspro} - "
                f"Amandemen ke-"
                f"{amendment_no}. "
                f"Periksa tab LSPr edit "
                f"sekitar baris {row_number}."
            )


        seen.add(
            key
        )


        records.append(
            {

                "id_lspro":
                    id_lspro,

                "amendment_no":
                    amendment_no,

                "amendment_date":
                    amendment_date,

                "source_type":
                    "LSPR_EDIT",

                "source_row":
                    row_number,
            }
        )


    return records


# ============================================================
# READ LSBU AMENDMENTS
# ============================================================

def read_lsbu_amendments(
    directory_spreadsheet,
):

    worksheet = (
        directory_spreadsheet
        .worksheet(
            GOOGLE_LSBU_AMENDMENT_SHEET_NAME
        )
    )


    values = (
        worksheet
        .get_all_values()
    )


    if not values:

        return []


    headers = [
        str(item).strip()
        for item in values[0]
    ]


    required_headers = [
        "NO. AKREDITASI",
        "AA",
        "RA1",
        "RA2",
        "RA3",
    ]


    missing_headers = [
        header

        for header in required_headers

        if header not in headers
    ]


    if missing_headers:

        raise RuntimeError(
            "Kolom berikut tidak ditemukan "
            "di tab LSBU: "
            + ", ".join(
                missing_headers
            )
        )


    header_index = {
        name: index

        for index, name
        in enumerate(headers)
    }


    amendment_columns = [
        (
            "AA",
            1,
        ),
        (
            "RA1",
            2,
        ),
        (
            "RA2",
            3,
        ),
        (
            "RA3",
            4,
        ),
    ]


    records = []

    seen = set()


    for row_number, row in enumerate(
        values[1:],
        start=2,
    ):

        id_lspro = (
            normalize_institution_id(
                get_row_value(
                    row,
                    header_index[
                        "NO. AKREDITASI"
                    ],
                )
            )
        )


        if not id_lspro:

            continue


        if not id_lspro.upper().startswith(
            "LSBU-"
        ):

            continue


        for (
            column_name,
            amendment_no,
        ) in amendment_columns:


            amendment_date = (
                get_row_value(
                    row,
                    header_index[
                        column_name
                    ],
                )
            )


            if not amendment_date:

                continue


            key = (
                id_lspro,
                amendment_no,
            )


            if key in seen:

                raise RuntimeError(
                    "Duplikat data LSBU "
                    "ditemukan: "
                    f"{id_lspro} - "
                    f"Amandemen ke-"
                    f"{amendment_no}."
                )


            seen.add(
                key
            )


            records.append(
                {

                    "id_lspro":
                        id_lspro,

                    "amendment_no":
                        amendment_no,

                    "amendment_date":
                        amendment_date,

                    "source_type":
                        "LSBU",

                    "source_row":
                        row_number,
                }
            )


    return records


# ============================================================
# BUILD AMENDMENT RECORD
# ============================================================

def build_amendment_records(
    directory_spreadsheet,
):

    lspr_records = (
        read_lspr_amendments(
            directory_spreadsheet
        )
    )


    lsbu_records = (
        read_lsbu_amendments(
            directory_spreadsheet
        )
    )


    all_records = (
        lspr_records
        +
        lsbu_records
    )


    seen = set()


    for record in all_records:

        key = (
            record[
                "id_lspro"
            ],

            record[
                "amendment_no"
            ],
        )


        if key in seen:

            raise RuntimeError(
                "Duplikat Amandemen "
                "ditemukan setelah "
                "penggabungan sumber: "
                f"{record['id_lspro']} - "
                f"Amandemen ke-"
                f"{record['amendment_no']}."
            )


        seen.add(
            key
        )


    return all_records


# ============================================================
# CHECK MASTER CHANGE
# ============================================================

def has_changes(
    existing,
    source,
):

    for field in SYNC_FIELDS:

        old_value = nullable_text(
            existing[
                field
            ]
        )


        new_value = nullable_text(
            source[
                field
            ]
        )


        if old_value != new_value:

            return True


    return False


# ============================================================
# SYNC MASTER
# ============================================================

def sync_master_records(
    conn,
    records,
):

    inserted_count = 0
    updated_count = 0
    unchanged_count = 0
    missing_count = 0


    source_ids = set()


    for record in records:

        id_lspro = (
            record[
                "id_lspro"
            ]
        )


        source_ids.add(
            id_lspro
        )


        existing = (
            conn.execute(
                """
                SELECT *

                FROM institution

                WHERE id_lspro = ?
                """,
                (
                    id_lspro,
                ),
            )
            .fetchone()
        )


        # ====================================================
        # INSERT
        # ====================================================

        if existing is None:

            conn.execute(
                """
                INSERT INTO institution (
                    id_lspro,
                    name_lspro,
                    date_start_accreditation,
                    date_end_accreditation,
                    status_accreditation,
                    address,
                    kab_kota,
                    propinsi,
                    kode_pos,
                    telp,
                    fax,
                    email,
                    cp,
                    no_hp_cp,
                    source_status,
                    synced_at
                )

                VALUES (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    'AVAILABLE',
                    CURRENT_TIMESTAMP
                )
                """,
                (
                    record[
                        "id_lspro"
                    ],

                    record[
                        "name_lspro"
                    ],

                    record[
                        "date_start_accreditation"
                    ],

                    record[
                        "date_end_accreditation"
                    ],

                    record[
                        "status_accreditation"
                    ],

                    record[
                        "address"
                    ],

                    record[
                        "kab_kota"
                    ],

                    record[
                        "propinsi"
                    ],

                    record[
                        "kode_pos"
                    ],

                    record[
                        "telp"
                    ],

                    record[
                        "fax"
                    ],

                    record[
                        "email"
                    ],

                    record[
                        "cp"
                    ],

                    record[
                        "no_hp_cp"
                    ],
                ),
            )


            inserted_count += 1

            continue


        changed = (
            has_changes(
                existing,
                record,
            )
        )


        restored = (
            existing[
                "source_status"
            ]
            != "AVAILABLE"
        )


        conn.execute(
            """
            UPDATE institution

            SET
                name_lspro = ?,
                date_start_accreditation = ?,
                date_end_accreditation = ?,
                status_accreditation = ?,
                address = ?,
                kab_kota = ?,
                propinsi = ?,
                kode_pos = ?,
                telp = ?,
                fax = ?,
                email = ?,
                cp = ?,
                no_hp_cp = ?,

                source_status =
                    'AVAILABLE',

                updated_at =
                    CASE

                        WHEN ? = 1
                        THEN CURRENT_TIMESTAMP

                        ELSE updated_at

                    END,

                synced_at =
                    CURRENT_TIMESTAMP

            WHERE id_lspro = ?
            """,
            (
                record[
                    "name_lspro"
                ],

                record[
                    "date_start_accreditation"
                ],

                record[
                    "date_end_accreditation"
                ],

                record[
                    "status_accreditation"
                ],

                record[
                    "address"
                ],

                record[
                    "kab_kota"
                ],

                record[
                    "propinsi"
                ],

                record[
                    "kode_pos"
                ],

                record[
                    "telp"
                ],

                record[
                    "fax"
                ],

                record[
                    "email"
                ],

                record[
                    "cp"
                ],

                record[
                    "no_hp_cp"
                ],

                1
                if (
                    changed
                    or restored
                )
                else 0,

                id_lspro,
            ),
        )


        if changed or restored:

            updated_count += 1

        else:

            unchanged_count += 1


    # ========================================================
    # MISSING FROM SOURCE
    # ========================================================

    existing_available = (
        conn.execute(
            """
            SELECT
                institution_id,
                id_lspro

            FROM institution

            WHERE source_status =
                'AVAILABLE'
            """
        )
        .fetchall()
    )


    for item in existing_available:

        if (
            item[
                "id_lspro"
            ]
            not in source_ids
        ):

            conn.execute(
                """
                UPDATE institution

                SET
                    source_status =
                        'MISSING_FROM_SOURCE',

                    updated_at =
                        CURRENT_TIMESTAMP,

                    synced_at =
                        CURRENT_TIMESTAMP

                WHERE institution_id = ?
                """,
                (
                    item[
                        "institution_id"
                    ],
                ),
            )


            missing_count += 1


    return {

        "inserted_count":
            inserted_count,

        "updated_count":
            updated_count,

        "unchanged_count":
            unchanged_count,

        "missing_count":
            missing_count,
    }


# ============================================================
# SYNC AMENDMENT
# ============================================================

def sync_amendment_records(
    conn,
    records,
):

    inserted_count = 0
    updated_count = 0
    unchanged_count = 0
    deleted_count = 0


    source_keys = set()


    for record in records:

        institution = (
            conn.execute(
                """
                SELECT
                    institution_id

                FROM institution

                WHERE id_lspro = ?
                """,
                (
                    record[
                        "id_lspro"
                    ],
                ),
            )
            .fetchone()
        )


        if institution is None:

            raise RuntimeError(
                "Data Amandemen mengacu "
                "ke lembaga yang tidak "
                "ditemukan di Master Lembaga: "
                f"{record['id_lspro']} "
                f"(sumber "
                f"{record['source_type']}, "
                f"baris "
                f"{record['source_row']})."
            )


        institution_id = (
            institution[
                "institution_id"
            ]
        )


        key = (
            institution_id,

            record[
                "amendment_no"
            ],
        )


        source_keys.add(
            key
        )


        existing = (
            conn.execute(
                """
                SELECT *

                FROM institution_amendment

                WHERE institution_id = ?

                AND amendment_no = ?
                """,
                (
                    institution_id,

                    record[
                        "amendment_no"
                    ],
                ),
            )
            .fetchone()
        )


        # ====================================================
        # INSERT
        # ====================================================

        if existing is None:

            conn.execute(
                """
                INSERT INTO institution_amendment (
                    institution_id,
                    amendment_no,
                    amendment_date
                )

                VALUES (
                    ?,
                    ?,
                    ?
                )
                """,
                (
                    institution_id,

                    record[
                        "amendment_no"
                    ],

                    record[
                        "amendment_date"
                    ],
                ),
            )


            inserted_count += 1

            continue


        # ====================================================
        # UPDATE
        # ====================================================

        old_date = nullable_text(
            existing[
                "amendment_date"
            ]
        )


        new_date = nullable_text(
            record[
                "amendment_date"
            ]
        )


        changed = (
            old_date != new_date
        )


        conn.execute(
            """
            UPDATE institution_amendment

            SET
                amendment_date = ?,

                updated_at =
                    CASE

                        WHEN ? = 1
                        THEN CURRENT_TIMESTAMP

                        ELSE updated_at

                    END

            WHERE institution_id = ?

            AND amendment_no = ?
            """,
            (
                record[
                    "amendment_date"
                ],

                1
                if changed
                else 0,

                institution_id,

                record[
                    "amendment_no"
                ],
            ),
        )


        if changed:

            updated_count += 1

        else:

            unchanged_count += 1


    # ========================================================
    # DELETE AMENDMENT NOT IN SOURCE
    # ========================================================

    existing_amendments = (
        conn.execute(
            """
            SELECT
                amendment_id,
                institution_id,
                amendment_no

            FROM institution_amendment
            """
        )
        .fetchall()
    )


    for item in existing_amendments:

        key = (
            item[
                "institution_id"
            ],

            item[
                "amendment_no"
            ],
        )


        if key not in source_keys:

            conn.execute(
                """
                DELETE FROM institution_amendment

                WHERE amendment_id = ?
                """,
                (
                    item[
                        "amendment_id"
                    ],
                ),
            )


            deleted_count += 1


    return {

        "inserted_count":
            inserted_count,

        "updated_count":
            updated_count,

        "unchanged_count":
            unchanged_count,

        "deleted_count":
            deleted_count,
    }


# ============================================================
# MAIN SYNC
# ============================================================

def sync_institutions():

    acquire_sync_lock()


    conn = None
    sync_id = None


    try:

        # ====================================================
        # GOOGLE CLIENT
        # ====================================================

        client = (
            get_google_client()
        )


        # ====================================================
        # OPEN SOURCE
        # ====================================================

        master_spreadsheet = (
            get_master_spreadsheet(
                client
            )
        )


        directory_spreadsheet = (
            get_directory_spreadsheet(
                client
            )
        )


        # ====================================================
        # READ MASTER
        # ====================================================

        master_records = (
            build_master_records(
                master_spreadsheet
            )
        )


        # ====================================================
        # READ AMENDMENT
        # ====================================================

        amendment_records = (
            build_amendment_records(
                directory_spreadsheet
            )
        )


        # ====================================================
        # DATABASE
        # ====================================================

        conn = get_connection()


        started_at = (
            datetime.now()
            .strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )


        cursor = conn.execute(
            """
            INSERT INTO sync_history (
                source_type,
                sync_status,
                started_at
            )

            VALUES (
                'GOOGLE_SHEETS_PPJ',
                'PROCESSING',
                ?
            )
            """,
            (
                started_at,
            ),
        )


        sync_id = (
            cursor.lastrowid
        )


        conn.commit()


        # ====================================================
        # TRANSACTION
        # ====================================================

        conn.execute(
            "BEGIN"
        )


        master_result = (
            sync_master_records(
                conn,
                master_records,
            )
        )


        amendment_result = (
            sync_amendment_records(
                conn,
                amendment_records,
            )
        )


        # ====================================================
        # FINISH
        # ====================================================

        finished_at = (
            datetime.now()
            .strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )


        conn.execute(
            """
            UPDATE sync_history

            SET
                sync_status =
                    'SUCCESS',

                total_source = ?,

                inserted_count = ?,

                updated_count = ?,

                unchanged_count = ?,

                missing_count = ?,

                finished_at = ?

            WHERE sync_id = ?
            """,
            (
                len(
                    master_records
                ),

                master_result[
                    "inserted_count"
                ],

                master_result[
                    "updated_count"
                ],

                master_result[
                    "unchanged_count"
                ],

                master_result[
                    "missing_count"
                ],

                finished_at,

                sync_id,
            ),
        )


        conn.commit()


        # ====================================================
        # COUNT TYPE
        # ====================================================

        lspr_amendment_total = sum(
            1

            for item
            in amendment_records

            if item[
                "source_type"
            ] == "LSPR_EDIT"
        )


        lsbu_amendment_total = sum(
            1

            for item
            in amendment_records

            if item[
                "source_type"
            ] == "LSBU"
        )


        # ====================================================
        # RETURN
        # ====================================================

        return {

            "success":
                True,

            "total_source":
                len(
                    master_records
                ),

            "inserted_count":
                master_result[
                    "inserted_count"
                ],

            "updated_count":
                master_result[
                    "updated_count"
                ],

            "unchanged_count":
                master_result[
                    "unchanged_count"
                ],

            "missing_count":
                master_result[
                    "missing_count"
                ],

            "amendment_total":
                len(
                    amendment_records
                ),

            "lspr_amendment_total":
                lspr_amendment_total,

            "lsbu_amendment_total":
                lsbu_amendment_total,

            "amendment_inserted":
                amendment_result[
                    "inserted_count"
                ],

            "amendment_updated":
                amendment_result[
                    "updated_count"
                ],

            "amendment_unchanged":
                amendment_result[
                    "unchanged_count"
                ],

            "amendment_deleted":
                amendment_result[
                    "deleted_count"
                ],

            "finished_at":
                finished_at,
        }


    except Exception as exc:

        if conn is not None:

            conn.rollback()


            finished_at = (
                datetime.now()
                .strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )


            if sync_id is not None:

                try:

                    conn.execute(
                        """
                        UPDATE sync_history

                        SET
                            sync_status =
                                'FAILED',

                            error_message = ?,

                            finished_at = ?

                        WHERE sync_id = ?
                        """,
                        (
                            str(
                                exc
                            ),

                            finished_at,

                            sync_id,
                        ),
                    )


                    conn.commit()


                except Exception:

                    conn.rollback()


        raise


    finally:

        if conn is not None:

            conn.close()


        release_sync_lock()