import io

import pandas as pd

from app.database import (
    get_connection,
)


# ============================================================
# CONFIG
# ============================================================

SHEET_NAME = (
    "Master Skema Sertifikasi"
)


EXPECTED_COLUMNS = [
    "id_skema_sertifikasi",
    "skema_sertifikasi",
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
# VALIDATE CODE FORMAT
# ============================================================

def validate_code_format(
    code,
    row_number,
):

    if not code:

        raise ValueError(
            (
                f"Baris {row_number}: "
                "ID Skema Sertifikasi wajib diisi."
            )
        )


    code_text = str(
        code
    )


    if not code_text.startswith(
        "SKM-"
    ):

        raise ValueError(
            (
                f"Baris {row_number}: "
                f"ID Skema Sertifikasi '{code_text}' "
                "tidak valid. "
                "Format yang benar adalah "
                "SKM-XXXX, contoh SKM-0001."
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
                f"ID Skema Sertifikasi '{code_text}' "
                "tidak valid. "
                "Setelah 'SKM-' harus terdiri "
                "dari tepat 4 digit angka."
            )
        )


    if not number_part.isdigit():

        raise ValueError(
            (
                f"Baris {row_number}: "
                f"ID Skema Sertifikasi '{code_text}' "
                "tidak valid. "
                "Bagian setelah 'SKM-' "
                "harus berupa angka."
            )
        )


# ============================================================
# READ FILE
# ============================================================

def read_certification_scheme_file(
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
                    "Sheet Master Skema Sertifikasi "
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
                "Format Master Skema Sertifikasi "
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
                "id_skema_sertifikasi"
            ]
        )
    )


    name = (
        value_to_text(
            row[
                "skema_sertifikasi"
            ]
        )
    )


    validate_code_format(
        code,
        row_number,
    )


    if not name:

        raise ValueError(
            (
                f"Baris {row_number}: "
                "Nama Skema Sertifikasi "
                "wajib diisi."
            )
        )


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
                certification_scheme_id,
                certification_scheme_code,
                certification_scheme_name

            FROM master_certification_scheme

            WHERE certification_scheme_code = ?

            LIMIT 1
            """,
            (
                code,
            ),
        )
        .fetchone()
    )


# ============================================================
# FIND BY NAME
# ============================================================

def find_by_name(
    conn,
    name,
):

    return (
        conn.execute(
            """
            SELECT
                certification_scheme_id,
                certification_scheme_code,
                certification_scheme_name

            FROM master_certification_scheme

            WHERE certification_scheme_name = ?

            LIMIT 1
            """,
            (
                name,
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

    seen_names = {}


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
                    "id_skema_sertifikasi"
                ]
            )
        )


        name = (
            value_to_text(
                row[
                    "skema_sertifikasi"
                ]
            )
        )


        # ====================================================
        # DUPLICATE CODE IN FILE
        # ====================================================

        if code in seen_codes:

            raise ValueError(
                (
                    f"Baris {row_number}: "
                    f"ID Skema Sertifikasi '{code}' "
                    "duplikat di dalam file. "
                    "ID tersebut sebelumnya sudah digunakan "
                    f"pada baris {seen_codes[code]}."
                )
            )


        # ====================================================
        # DUPLICATE NAME IN FILE
        # ====================================================

        if name in seen_names:

            raise ValueError(
                (
                    f"Baris {row_number}: "
                    f"Nama Skema Sertifikasi '{name}' "
                    "duplikat di dalam file. "
                    "Nama tersebut sebelumnya sudah digunakan "
                    f"pada baris {seen_names[name]}."
                )
            )


        seen_codes[
            code
        ] = row_number


        seen_names[
            name
        ] = row_number


# ============================================================
# IMPORT
# ============================================================

def import_certification_schemes(
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
        read_certification_scheme_file(
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
                "File Master Skema Sertifikasi "
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
        #
        # Check existing DB before INSERT.
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
                            "id_skema_sertifikasi"
                        ]
                    )
                )


                name = (
                    value_to_text(
                        row[
                            "skema_sertifikasi"
                        ]
                    )
                )


                existing_code = (
                    find_by_code(
                        conn,
                        code,
                    )
                )


                existing_name = (
                    find_by_name(
                        conn,
                        name,
                    )
                )


                # =============================================
                # SAME CODE + SAME NAME
                #
                # Consider as existing.
                # =============================================

                if existing_code:

                    if (
                        existing_code[
                            "certification_scheme_name"
                        ]
                        ==
                        name
                    ):

                        existing_count += 1

                        continue


                    raise ValueError(
                        (
                            f"Baris {row_number}: "
                            f"ID Skema Sertifikasi '{code}' "
                            "sudah digunakan oleh "
                            f"'{existing_code['certification_scheme_name']}'."
                        )
                    )


                # =============================================
                # SAME NAME + DIFFERENT CODE
                # =============================================

                if existing_name:

                    raise ValueError(
                        (
                            f"Baris {row_number}: "
                            f"Nama Skema Sertifikasi '{name}' "
                            "sudah tersedia dengan ID "
                            f"'{existing_name['certification_scheme_code']}'."
                        )
                    )


                conn.execute(
                    """
                    INSERT INTO master_certification_scheme (
                        certification_scheme_code,
                        certification_scheme_name
                    )

                    VALUES (
                        ?,
                        ?
                    )
                    """,
                    (
                        code,
                        name,
                    ),
                )


                inserted_count += 1


        # ====================================================
        # REPLACE
        #
        # File sudah tervalidasi sepenuhnya sebelum DELETE.
        # ====================================================

        elif (
            import_mode
            ==
            "replace"
        ):

            conn.execute(
                """
                DELETE FROM master_certification_scheme
                """
            )


            for (
                index,
                row,
            ) in dataframe.iterrows():

                code = (
                    value_to_text(
                        row[
                            "id_skema_sertifikasi"
                        ]
                    )
                )


                name = (
                    value_to_text(
                        row[
                            "skema_sertifikasi"
                        ]
                    )
                )


                conn.execute(
                    """
                    INSERT INTO master_certification_scheme (
                        certification_scheme_code,
                        certification_scheme_name
                    )

                    VALUES (
                        ?,
                        ?
                    )
                    """,
                    (
                        code,
                        name,
                    ),
                )


                inserted_count += 1


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

            "existing_count":
                existing_count,
        }


    except Exception:

        conn.rollback()

        raise


    finally:

        conn.close()