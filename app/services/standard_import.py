import io

import pandas as pd

from app.database import get_connection


# ============================================================
# CONFIG
# ============================================================

SHEET_NAME = "Master Standar"


EXPECTED_COLUMNS = [
    "id_standar",
    "nomor_acuan_standar",
    "judul_acuan_standar",
]


VALID_IMPORT_MODES = {
    "append",
    "replace",
}


# ============================================================
# CHECK MISSING
# ============================================================

def is_missing(
    value,
):

    if value is None:

        return True


    try:

        if pd.isna(
            value
        ):

            return True


    except Exception:

        pass


    return False


# ============================================================
# VALUE TO TEXT
# ============================================================

def value_to_text(
    value,
):

    if is_missing(
        value
    ):

        return None


    if isinstance(
        value,
        str,
    ):

        return value


    if isinstance(
        value,
        float,
    ):

        if value.is_integer():

            return str(
                int(
                    value
                )
            )


    return str(
        value
    )


# ============================================================
# OPTIONAL TEXT
# ============================================================

def value_to_optional_text(
    value,
):

    value_text = (
        value_to_text(
            value
        )
    )


    if value_text is None:

        return ""


    return value_text


# ============================================================
# VALIDATE CODE
# ============================================================

def validate_code_format(
    code,
    row_number,
):

    if not code:

        raise ValueError(
            (
                f"Baris {row_number}: "
                "ID Standar wajib diisi."
            )
        )


    code_text = str(
        code
    )


    if not code_text.startswith(
        "STD-"
    ):

        raise ValueError(
            (
                f"Baris {row_number}: "
                f"ID Standar '{code_text}' "
                "tidak valid. "
                "Format yang benar adalah "
                "STD-XXXX, contoh STD-0001."
            )
        )


    number_part = (
        code_text[4:]
    )


    if (
        len(
            number_part
        )
        !=
        4
    ):

        raise ValueError(
            (
                f"Baris {row_number}: "
                f"ID Standar '{code_text}' "
                "tidak valid. "
                "Setelah 'STD-' harus terdiri "
                "dari tepat 4 digit angka."
            )
        )


    if not number_part.isdigit():

        raise ValueError(
            (
                f"Baris {row_number}: "
                f"ID Standar '{code_text}' "
                "tidak valid. "
                "Bagian setelah 'STD-' "
                "harus berupa angka."
            )
        )


# ============================================================
# READ FILE
# ============================================================

def read_standard_file(
    file_content,
    filename,
):

    filename_lower = (
        filename.lower()
    )


    # ========================================================
    # EXCEL
    # ========================================================

    if filename_lower.endswith(
        (
            ".xlsx",
            ".xls",
        )
    ):

        stream = io.BytesIO(
            file_content
        )


        excel_file = (
            pd.ExcelFile(
                stream
            )
        )


        if (
            SHEET_NAME
            in
            excel_file.sheet_names
        ):

            selected_sheet = (
                SHEET_NAME
            )


        elif (
            len(
                excel_file.sheet_names
            )
            ==
            1
        ):

            selected_sheet = (
                excel_file.sheet_names[
                    0
                ]
            )


        else:

            raise ValueError(
                (
                    "Sheet Master Standar "
                    "tidak ditemukan. "
                    "Gunakan sheet bernama "
                    f"'{SHEET_NAME}'."
                )
            )


        dataframe = (
            pd.read_excel(
                excel_file,
                sheet_name=(
                    selected_sheet
                ),
                dtype=object,
            )
        )


        return dataframe


    # ========================================================
    # CSV
    # ========================================================

    if filename_lower.endswith(
        ".csv"
    ):

        stream = io.BytesIO(
            file_content
        )


        return pd.read_csv(
            stream,
            dtype=object,
        )


    raise ValueError(
        (
            "Format file tidak didukung. "
            "Gunakan .xlsx, .xls, atau .csv."
        )
    )


# ============================================================
# VALIDATE COLUMNS
# ============================================================

def validate_columns(
    dataframe,
):

    actual_columns = [

        column

        for column
        in dataframe.columns

        if not (

            column is None

            or

            str(
                column
            ).startswith(
                "Unnamed:"
            )

        )

    ]


    missing_columns = [

        column

        for column
        in EXPECTED_COLUMNS

        if column
        not in actual_columns

    ]


    if missing_columns:

        raise ValueError(
            (
                "Format Master Standar "
                "tidak sesuai. "
                "Kolom berikut tidak ditemukan: "
            )
            +
            ", ".join(
                missing_columns
            )
        )


# ============================================================
# VALIDATE ROW
# ============================================================

def validate_row(
    row,
    row_number,
):

    code = (
        value_to_text(
            row[
                "id_standar"
            ]
        )
    )


    standard_number = (
        value_to_text(
            row[
                "nomor_acuan_standar"
            ]
        )
    )


    validate_code_format(
        code,
        row_number,
    )


    # ========================================================
    # NOMOR ACUAN WAJIB
    # ========================================================

    if not standard_number:

        raise ValueError(
            (
                f"Baris {row_number}: "
                "Nomor Acuan Standar wajib diisi."
            )
        )


    # ========================================================
    # JUDUL BOLEH KOSONG
    # ========================================================

    # Tidak ada validasi wajib untuk
    # judul_acuan_standar.


# ============================================================
# FIND BY CODE
# ============================================================

def find_by_code(
    conn,
    code,
):

    return (
        conn.execute(
            """
            SELECT
                standard_id,
                standard_code,
                standard_number,
                standard_title

            FROM master_standard

            WHERE standard_code = ?

            LIMIT 1
            """,
            (
                code,
            ),
        )
        .fetchone()
    )


# ============================================================
# FIND BY STANDARD NUMBER
# ============================================================

def find_by_number(
    conn,
    standard_number,
):

    return (
        conn.execute(
            """
            SELECT
                standard_id,
                standard_code,
                standard_number,
                standard_title

            FROM master_standard

            WHERE standard_number = ?

            LIMIT 1
            """,
            (
                standard_number,
            ),
        )
        .fetchone()
    )


# ============================================================
# VALIDATE FULL FILE
# ============================================================

def validate_full_file(
    dataframe,
):

    seen_codes = {}

    seen_numbers = {}


    for (
        index,
        row,
    ) in dataframe.iterrows():

        row_number = (
            index + 2
        )


        validate_row(
            row,
            row_number,
        )


        code = (
            value_to_text(
                row[
                    "id_standar"
                ]
            )
        )


        standard_number = (
            value_to_text(
                row[
                    "nomor_acuan_standar"
                ]
            )
        )


        # ====================================================
        # DUPLICATE ID
        # ====================================================

        if code in seen_codes:

            raise ValueError(
                (
                    f"Baris {row_number}: "
                    f"ID Standar '{code}' "
                    "duplikat di dalam file. "
                    "ID tersebut sebelumnya "
                    "sudah digunakan pada baris "
                    f"{seen_codes[code]}."
                )
            )


        # ====================================================
        # DUPLICATE NOMOR ACUAN
        # ====================================================

        if standard_number in seen_numbers:

            raise ValueError(
                (
                    f"Baris {row_number}: "
                    "Nomor Acuan Standar "
                    f"'{standard_number}' "
                    "duplikat di dalam file. "
                    "Nomor tersebut sebelumnya "
                    "sudah digunakan pada baris "
                    f"{seen_numbers[standard_number]}."
                )
            )


        seen_codes[
            code
        ] = row_number


        seen_numbers[
            standard_number
        ] = row_number


# ============================================================
# IMPORT
# ============================================================

def import_standards(
    file_content,
    filename,
    import_mode,
):

    # ========================================================
    # VALIDATE MODE
    # ========================================================

    if (
        import_mode
        not in
        VALID_IMPORT_MODES
    ):

        raise ValueError(
            "Mode import tidak valid."
        )


    # ========================================================
    # READ FILE
    # ========================================================

    dataframe = (
        read_standard_file(
            file_content,
            filename,
        )
    )


    # ========================================================
    # VALIDATE COLUMNS
    # ========================================================

    validate_columns(
        dataframe
    )


    dataframe = (
        dataframe[
            EXPECTED_COLUMNS
        ]
    )


    # ========================================================
    # REMOVE FULL EMPTY ROWS
    # ========================================================

    dataframe = (
        dataframe.dropna(
            how="all"
        )
    )


    if dataframe.empty:

        raise ValueError(
            (
                "File Master Standar "
                "tidak memiliki data."
            )
        )


    # ========================================================
    # VALIDATE ALL FILE FIRST
    # ========================================================

    validate_full_file(
        dataframe
    )


    # ========================================================
    # DATABASE
    # ========================================================

    conn = get_connection()


    inserted_count = 0

    existing_count = 0


    try:

        conn.execute(
            "BEGIN"
        )


        # ====================================================
        # APPEND
        # ====================================================

        if (
            import_mode
            ==
            "append"
        ):

            for (
                index,
                row,
            ) in dataframe.iterrows():

                row_number = (
                    index + 2
                )


                code = (
                    value_to_text(
                        row[
                            "id_standar"
                        ]
                    )
                )


                standard_number = (
                    value_to_text(
                        row[
                            "nomor_acuan_standar"
                        ]
                    )
                )


                standard_title = (
                    value_to_optional_text(
                        row[
                            "judul_acuan_standar"
                        ]
                    )
                )


                # ============================================
                # CHECK ID
                # ============================================

                existing_code = (
                    find_by_code(
                        conn,
                        code,
                    )
                )


                if existing_code:

                    if (
                        existing_code[
                            "standard_number"
                        ]
                        ==
                        standard_number
                        and
                        existing_code[
                            "standard_title"
                        ]
                        ==
                        standard_title
                    ):

                        existing_count += 1

                        continue


                    raise ValueError(
                        (
                            f"Baris {row_number}: "
                            f"ID Standar '{code}' "
                            "sudah tersedia di database "
                            "dengan data yang berbeda."
                        )
                    )


                # ============================================
                # CHECK NOMOR ACUAN
                # ============================================

                existing_number = (
                    find_by_number(
                        conn,
                        standard_number,
                    )
                )


                if existing_number:

                    raise ValueError(
                        (
                            f"Baris {row_number}: "
                            "Nomor Acuan Standar "
                            f"'{standard_number}' "
                            "sudah tersedia dengan ID "
                            f"'{existing_number['standard_code']}'. "
                            "Nomor Acuan Standar tidak boleh duplikat."
                        )
                    )


                # ============================================
                # INSERT
                # ============================================

                conn.execute(
                    """
                    INSERT INTO master_standard (

                        standard_code,

                        standard_number,

                        standard_title

                    )

                    VALUES (
                        ?,
                        ?,
                        ?
                    )
                    """,
                    (
                        code,
                        standard_number,
                        standard_title,
                    ),
                )


                inserted_count += 1


        # ====================================================
        # REPLACE
        # ====================================================

        else:

            # File sudah divalidasi penuh
            # sebelum database lama dihapus.

            conn.execute(
                """
                DELETE FROM master_standard
                """
            )


            for (
                index,
                row,
            ) in dataframe.iterrows():

                code = (
                    value_to_text(
                        row[
                            "id_standar"
                        ]
                    )
                )


                standard_number = (
                    value_to_text(
                        row[
                            "nomor_acuan_standar"
                        ]
                    )
                )


                standard_title = (
                    value_to_optional_text(
                        row[
                            "judul_acuan_standar"
                        ]
                    )
                )


                conn.execute(
                    """
                    INSERT INTO master_standard (

                        standard_code,

                        standard_number,

                        standard_title

                    )

                    VALUES (
                        ?,
                        ?,
                        ?
                    )
                    """,
                    (
                        code,
                        standard_number,
                        standard_title,
                    ),
                )


                inserted_count += 1


        conn.commit()


        return {
            "import_mode":
                import_mode,

            "total_rows":
                int(
                    len(
                        dataframe
                    )
                ),

            "inserted_count":
                inserted_count,

            "existing_count":
                existing_count,
        }


    except Exception:

        conn.rollback()

        raise


    finally:

        conn.close()