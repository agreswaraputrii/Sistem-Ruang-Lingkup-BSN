import io
import re

from datetime import datetime

import pandas as pd

from app.database import get_connection


# ============================================================
# FORMAT MASTER LEMBAGA
# ============================================================

EXPECTED_COLUMNS = [
    "ID_LSPR",
    "Name_LSPR",
    "Date_Start_Accreditation",
    "Date_End_Accreditation",
    "Status_Accreditation",
    "Amandemen",
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


# Kolom yang nilainya wajib terisi.
REQUIRED_VALUE_COLUMNS = [
    "ID_LSPR",
    "Name_LSPR",
]


# Nama sheet yang diperbolehkan untuk file Excel.
INSTITUTION_SHEET_NAMES = [
    "Master Data Lembaga",
    "Master Lembaga",
]


# ============================================================
# BULAN INDONESIA
# ============================================================

INDONESIAN_MONTHS = {
    "januari": "January",
    "februari": "February",
    "maret": "March",
    "april": "April",
    "mei": "May",
    "juni": "June",
    "juli": "July",
    "agustus": "August",
    "september": "September",
    "oktober": "October",
    "november": "November",
    "desember": "December",
}


# ============================================================
# BASIC VALUE
# ============================================================

def is_empty(value):
    """
    Hanya mengecek apakah nilai kosong.

    Tidak mengubah isi data.
    """

    if value is None:
        return True

    if pd.isna(value):
        return True

    if isinstance(value, str):
        return not value.strip()

    return False


def value_or_none(value):

    if is_empty(value):
        return None

    return value


def value_to_text(value):
    """
    Mengubah nilai Python/Pandas menjadi teks
    yang aman disimpan di SQLite.

    Tidak melakukan cleaning atau auto-correct.
    """

    value = value_or_none(value)

    if value is None:
        return None

    if isinstance(value, str):
        return value

    # Mencegah:
    # 12345.0
    # jika Excel sebenarnya menyimpan angka bulat.
    if isinstance(value, float):

        if value.is_integer():
            return str(
                int(value)
            )

    return str(value)


# ============================================================
# DATE
# ============================================================

def date_to_database(value):
    """
    Konversi teknis nilai tanggal ke YYYY-MM-DD.

    Ini bukan cleaning ataupun auto-correct.

    Jika nilai tidak dikenali sebagai tanggal,
    nilainya tidak ditebak dan disimpan sebagai teks.
    """

    value = value_or_none(value)

    if value is None:
        return None


    if isinstance(
        value,
        (
            pd.Timestamp,
            datetime,
        ),
    ):

        return value.strftime(
            "%Y-%m-%d"
        )


    if isinstance(value, str):

        text = value

        known_formats = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
        ]


        for date_format in known_formats:

            try:

                parsed = datetime.strptime(
                    text,
                    date_format,
                )

                return parsed.strftime(
                    "%Y-%m-%d"
                )

            except ValueError:

                continue


        # Tidak ditebak.
        return text


    # Excel kadang menyimpan tanggal sebagai serial number.
    if isinstance(
        value,
        (
            int,
            float,
        ),
    ):

        if value > 1000:

            try:

                parsed = pd.to_datetime(
                    value,
                    unit="D",
                    origin="1899-12-30",
                )

                return parsed.strftime(
                    "%Y-%m-%d"
                )

            except Exception:

                pass


    return value_to_text(
        value
    )


# ============================================================
# AMENDMENT DATE
# ============================================================

def parse_amendment_date(value):

    if not value:
        return None


    date_text = str(value)


    for (
        indo_month,
        english_month,
    ) in INDONESIAN_MONTHS.items():

        date_text = re.sub(
            rf"\b{indo_month}\b",
            english_month,
            date_text,
            flags=re.IGNORECASE,
        )


    formats = [
        "%d %B %Y",
        "%d %b %Y",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ]


    for date_format in formats:

        try:

            parsed = datetime.strptime(
                date_text,
                date_format,
            )

            return parsed.strftime(
                "%Y-%m-%d"
            )

        except ValueError:

            continue


    # Tidak melakukan tebakan.
    return str(value)


# ============================================================
# PARSE AMANDEMEN
# ============================================================

def parse_amendments(
    value,
    id_lspro,
):

    value = value_or_none(
        value
    )


    if value is None:
        return []


    text = str(value)


    empty_amendment_values = {
        "tidak ditemukan",
        "tidak ada",
        "-",
    }


    if text.strip().lower() in empty_amendment_values:
        return []


    # Mendukung:
    #
    # Amandemen ke-1 (20 Februari 2025)
    # Amendemen ke-1 (20 Februari 2025)
    #
    pattern = re.compile(
        r"(?:Amandemen|Amendemen)"
        r"\s+ke\s*-\s*(\d+)"
        r"\s*\((.*?)\)",
        flags=re.IGNORECASE,
    )


    matches = pattern.findall(
        text
    )


    if not matches:

        raise ValueError(
            f"Format kolom Amandemen untuk "
            f"{id_lspro} tidak dapat dibaca. "
            f"Gunakan format seperti: "
            f"Amandemen ke-1 (20 Februari 2025)."
        )


    results = []

    used_numbers = set()


    for (
        amendment_no,
        amendment_date,
    ) in matches:

        amendment_no = int(
            amendment_no
        )


        if amendment_no in used_numbers:

            raise ValueError(
                f"Nomor Amandemen duplikat "
                f"pada {id_lspro}: "
                f"Amandemen ke-{amendment_no}."
            )


        used_numbers.add(
            amendment_no
        )


        results.append(
            {
                "amendment_no":
                    amendment_no,

                "amendment_date":
                    parse_amendment_date(
                        amendment_date
                    ),
            }
        )


    return results


# ============================================================
# READ EXCEL
# ============================================================

def read_excel_file(
    file_content,
):

    stream = io.BytesIO(
        file_content
    )


    excel_file = pd.ExcelFile(
        stream
    )


    sheet_names = (
        excel_file.sheet_names
    )


    selected_sheet = None


    # Cari nama sheet yang memang kita kenal.
    for sheet_name in INSTITUTION_SHEET_NAMES:

        if sheet_name in sheet_names:

            selected_sheet = (
                sheet_name
            )

            break


    # Jika hanya satu sheet, aman digunakan.
    if (
        selected_sheet is None
        and
        len(sheet_names) == 1
    ):

        selected_sheet = (
            sheet_names[0]
        )


    if selected_sheet is None:

        raise ValueError(
            "Sheet Master Lembaga tidak ditemukan. "
            "Gunakan sheet bernama "
            "'Master Data Lembaga' "
            "atau 'Master Lembaga'. "
            "Sheet yang tersedia: "
            + ", ".join(
                sheet_names
            )
        )


    dataframe = pd.read_excel(
        excel_file,
        sheet_name=selected_sheet,
        dtype=object,
    )


    return dataframe


# ============================================================
# READ CSV
# ============================================================

def read_csv_file(
    file_content,
):

    stream = io.BytesIO(
        file_content
    )


    dataframe = pd.read_csv(
        stream,
        dtype=object,
    )


    return dataframe


# ============================================================
# READ FILE
# ============================================================

def read_institution_file(
    file_content,
    filename,
):

    filename_lower = (
        filename.lower()
    )


    if filename_lower.endswith(
        ".xlsx"
    ):

        return read_excel_file(
            file_content
        )


    if filename_lower.endswith(
        ".xls"
    ):

        return read_excel_file(
            file_content
        )


    if filename_lower.endswith(
        ".csv"
    ):

        return read_csv_file(
            file_content
        )


    raise ValueError(
        "Format file tidak didukung. "
        "Gunakan .xlsx, .xls, atau .csv."
    )


# ============================================================
# VALIDATE FILE STRUCTURE
# ============================================================

def validate_institution_file(
    dataframe,
):

    actual_columns = list(
        dataframe.columns
    )


    missing_columns = [
        column

        for column
        in EXPECTED_COLUMNS

        if column
        not in actual_columns
    ]


    if missing_columns:

        raise ValueError(
            "Format file Master Lembaga tidak sesuai. "
            "Kolom berikut tidak ditemukan: "
            + ", ".join(
                missing_columns
            )
        )


    # ========================================================
    # REQUIRED VALUE
    # ========================================================

    for column in REQUIRED_VALUE_COLUMNS:

        empty_rows = []


        for index, row in dataframe.iterrows():

            if is_empty(
                row[column]
            ):

                empty_rows.append(
                    index + 2
                )


        if empty_rows:

            raise ValueError(
                f"Kolom {column} kosong "
                f"pada baris: "
                + ", ".join(
                    str(item)
                    for item
                    in empty_rows
                )
            )


    # ========================================================
    # DUPLICATE ID
    # ========================================================

    ids = [
        value_to_text(
            value
        )

        for value
        in dataframe[
            "ID_LSPR"
        ].tolist()
    ]


    seen = set()

    duplicates = set()


    for id_lspro in ids:

        if id_lspro in seen:

            duplicates.add(
                id_lspro
            )

        else:

            seen.add(
                id_lspro
            )


    if duplicates:

        raise ValueError(
            "Terdapat ID_LSPR duplikat "
            "di dalam file: "
            + ", ".join(
                sorted(
                    duplicates
                )
            )
        )


# ============================================================
# REPLACE AMENDMENTS
# ============================================================

def replace_institution_amendments(
    conn,
    institution_id,
    id_lspro,
    amendment_value,
):

    amendments = parse_amendments(
        amendment_value,
        id_lspro,
    )


    conn.execute(
        """
        DELETE FROM institution_amendment

        WHERE institution_id = ?
        """,
        (
            institution_id,
        ),
    )


    for amendment in amendments:

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

                amendment[
                    "amendment_no"
                ],

                amendment[
                    "amendment_date"
                ],
            ),
        )


# ============================================================
# IMPORT MASTER LEMBAGA
# ============================================================

def import_institutions(
    file_content,
    filename,
    import_mode,
):

    # ========================================================
    # VALIDATE MODE
    # ========================================================

    valid_modes = {
        "append",
        "replace",
    }


    if import_mode not in valid_modes:

        raise ValueError(
            "Mode import tidak valid."
        )


    # ========================================================
    # READ FILE
    # ========================================================

    dataframe = read_institution_file(
        file_content,
        filename,
    )


    # Hapus baris yang benar-benar kosong.
    #
    # Ini hanya mengabaikan blank row file,
    # bukan cleaning terhadap isi data.
    dataframe = dataframe.dropna(
        how="all"
    )


    validate_institution_file(
        dataframe
    )


    conn = get_connection()


    inserted_count = 0

    updated_count = 0

    missing_count = 0


    source_ids = set()


    try:

        conn.execute(
            "BEGIN"
        )


        # ====================================================
        # LOOP FILE
        # ====================================================

        for _, row in dataframe.iterrows():

            id_lspro = value_to_text(
                row[
                    "ID_LSPR"
                ]
            )


            source_ids.add(
                id_lspro
            )


            existing = (
                conn.execute(
                    """
                    SELECT
                        institution_id

                    FROM institution

                    WHERE id_lspro = ?
                    """,
                    (
                        id_lspro,
                    ),
                )
                .fetchone()
            )


            values = {

                "id_lspro":
                    id_lspro,

                "name_lspro":
                    value_to_text(
                        row[
                            "Name_LSPR"
                        ]
                    ),

                "date_start_accreditation":
                    date_to_database(
                        row[
                            "Date_Start_Accreditation"
                        ]
                    ),

                "date_end_accreditation":
                    date_to_database(
                        row[
                            "Date_End_Accreditation"
                        ]
                    ),

                "status_accreditation":
                    value_to_text(
                        row[
                            "Status_Accreditation"
                        ]
                    ),

                "address":
                    value_to_text(
                        row[
                            "Address"
                        ]
                    ),

                "kab_kota":
                    value_to_text(
                        row[
                            "Kab_Kota"
                        ]
                    ),

                "propinsi":
                    value_to_text(
                        row[
                            "Propinsi"
                        ]
                    ),

                "kode_pos":
                    value_to_text(
                        row[
                            "Kode_Pos"
                        ]
                    ),

                "telp":
                    value_to_text(
                        row[
                            "Telp"
                        ]
                    ),

                "fax":
                    value_to_text(
                        row[
                            "Fax"
                        ]
                    ),

                "email":
                    value_to_text(
                        row[
                            "Email"
                        ]
                    ),

                "cp":
                    value_to_text(
                        row[
                            "CP"
                        ]
                    ),

                "no_hp_cp":
                    value_to_text(
                        row[
                            "NoHpCP"
                        ]
                    ),
            }


            # =================================================
            # INSERT
            # =================================================

            if existing is None:

                cursor = conn.execute(
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
                        NULL
                    )
                    """,
                    (
                        values[
                            "id_lspro"
                        ],

                        values[
                            "name_lspro"
                        ],

                        values[
                            "date_start_accreditation"
                        ],

                        values[
                            "date_end_accreditation"
                        ],

                        values[
                            "status_accreditation"
                        ],

                        values[
                            "address"
                        ],

                        values[
                            "kab_kota"
                        ],

                        values[
                            "propinsi"
                        ],

                        values[
                            "kode_pos"
                        ],

                        values[
                            "telp"
                        ],

                        values[
                            "fax"
                        ],

                        values[
                            "email"
                        ],

                        values[
                            "cp"
                        ],

                        values[
                            "no_hp_cp"
                        ],
                    ),
                )


                institution_id = (
                    cursor.lastrowid
                )


                inserted_count += 1


            # =================================================
            # UPDATE
            # =================================================

            else:

                institution_id = (
                    existing[
                        "institution_id"
                    ]
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
                        source_status = 'AVAILABLE',
                        updated_at = CURRENT_TIMESTAMP,
                        synced_at = NULL

                    WHERE institution_id = ?
                    """,
                    (
                        values[
                            "name_lspro"
                        ],

                        values[
                            "date_start_accreditation"
                        ],

                        values[
                            "date_end_accreditation"
                        ],

                        values[
                            "status_accreditation"
                        ],

                        values[
                            "address"
                        ],

                        values[
                            "kab_kota"
                        ],

                        values[
                            "propinsi"
                        ],

                        values[
                            "kode_pos"
                        ],

                        values[
                            "telp"
                        ],

                        values[
                            "fax"
                        ],

                        values[
                            "email"
                        ],

                        values[
                            "cp"
                        ],

                        values[
                            "no_hp_cp"
                        ],

                        institution_id,
                    ),
                )


                updated_count += 1


            # =================================================
            # AMANDEMEN
            # =================================================

            replace_institution_amendments(
                conn=conn,

                institution_id=(
                    institution_id
                ),

                id_lspro=(
                    id_lspro
                ),

                amendment_value=(
                    row[
                        "Amandemen"
                    ]
                ),
            )


        # ====================================================
        # REPLACE MODE
        # ====================================================

        if import_mode == "replace":

            existing_institutions = (
                conn.execute(
                    """
                    SELECT
                        institution_id,
                        id_lspro,
                        source_status

                    FROM institution
                    """
                )
                .fetchall()
            )


            for institution in existing_institutions:

                existing_id = (
                    institution[
                        "id_lspro"
                    ]
                )


                if existing_id not in source_ids:

                    # Tidak menghapus row.
                    #
                    # Institution ID tetap dipertahankan agar
                    # relasi dengan data lain tidak rusak.
                    conn.execute(
                        """
                        UPDATE institution

                        SET
                            source_status =
                                'MISSING_FROM_SOURCE',

                            updated_at =
                                CURRENT_TIMESTAMP

                        WHERE institution_id = ?
                        """,
                        (
                            institution[
                                "institution_id"
                            ],
                        ),
                    )


                    if (
                        institution[
                            "source_status"
                        ]
                        !=
                        "MISSING_FROM_SOURCE"
                    ):

                        missing_count += 1


        # ====================================================
        # COMMIT
        # ====================================================

        conn.commit()


        return {

            "success":
                True,

            "import_mode":
                import_mode,

            "total_rows":
                len(
                    dataframe
                ),

            "inserted_count":
                inserted_count,

            "updated_count":
                updated_count,

            "missing_count":
                missing_count,
        }


    except Exception:

        conn.rollback()

        raise


    finally:

        conn.close()