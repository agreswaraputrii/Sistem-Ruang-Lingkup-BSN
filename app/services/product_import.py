import io

import pandas as pd

from app.database import (
    get_connection,
)


# ============================================================
# CONFIG
# ============================================================

SHEET_NAME = (
    "Master Data Produk (Clean)"
)


EXPECTED_COLUMNS = [
    "skema",
    "id_skema",
    "kategori",
    "id_kategori",
    "sub_kategori",
    "id_sub_kategori",
    "jenis",
    "id_jenis",
]


VALID_IMPORT_MODES = {
    "append",
    "replace",
}


# ============================================================
# STATUS
# ============================================================

STATUS_VALUE = "VALUE"

STATUS_NOT_APPLICABLE = (
    "NOT_APPLICABLE"
)

STATUS_MISSING = "MISSING"


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
# DETECT STATUS
# ============================================================

def detect_status(
    value,
):

    if is_missing(
        value
    ):

        return STATUS_MISSING


    if (
        isinstance(
            value,
            str,
        )
        and
        value == "-"
    ):

        return (
            STATUS_NOT_APPLICABLE
        )


    return STATUS_VALUE


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
# READ FILE
# ============================================================

def read_product_file(
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
                    "Sheet Master Produk "
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
            "Gunakan .xlsx, .xls, "
            "atau .csv."
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
                "Format Master Produk "
                "tidak sesuai. "
                "Kolom berikut "
                "tidak ditemukan: "
            )
            +
            ", ".join(
                missing_columns
            )
        )


# ============================================================
# VALIDATE NAME + ID STATUS
# ============================================================

def validate_pair_status(
    row_number,
    level_name,
    name_value,
    code_value,
):

    name_status = (
        detect_status(
            name_value
        )
    )


    code_status = (
        detect_status(
            code_value
        )
    )


    if (
        name_status
        !=
        code_status
    ):

        raise ValueError(
            (
                f"Baris {row_number}: "
                f"status {level_name} "
                "tidak konsisten. "
                f"Nilai nama = "
                f"{repr(name_value)}, "
                f"nilai ID = "
                f"{repr(code_value)}. "
                "Nama dan ID harus "
                "sama-sama berisi nilai, "
                "sama-sama '-', "
                "atau sama-sama kosong."
            )
        )


# ============================================================
# VALIDATE ROW
# ============================================================

def validate_row(
    row,
    row_number,
):

    # ========================================================
    # SKEMA
    # ========================================================

    scheme_status = (
        detect_status(
            row[
                "skema"
            ]
        )
    )


    scheme_code_status = (
        detect_status(
            row[
                "id_skema"
            ]
        )
    )


    if (
        scheme_status
        !=
        STATUS_VALUE
    ):

        raise ValueError(
            (
                f"Baris {row_number}: "
                "kolom skema "
                "wajib memiliki nilai."
            )
        )


    if (
        scheme_code_status
        !=
        STATUS_VALUE
    ):

        raise ValueError(
            (
                f"Baris {row_number}: "
                "kolom id_skema "
                "wajib memiliki nilai."
            )
        )


    # ========================================================
    # CATEGORY
    # ========================================================

    validate_pair_status(
        row_number,
        "kategori",
        row[
            "kategori"
        ],
        row[
            "id_kategori"
        ],
    )


    # ========================================================
    # SUBCATEGORY
    # ========================================================

    validate_pair_status(
        row_number,
        "sub_kategori",
        row[
            "sub_kategori"
        ],
        row[
            "id_sub_kategori"
        ],
    )


    # ========================================================
    # PRODUCT SERVICE
    # ========================================================

    validate_pair_status(
        row_number,
        "jenis",
        row[
            "jenis"
        ],
        row[
            "id_jenis"
        ],
    )


# ============================================================
# GET OR CREATE SCHEME
# ============================================================

def get_or_create_scheme(
    conn,
    scheme_code,
    scheme_name,
):

    existing = (
        conn.execute(
            """
            SELECT scheme_id

            FROM master_scheme

            WHERE scheme_code = ?
            AND scheme_name = ?
            """,
            (
                scheme_code,
                scheme_name,
            ),
        )
        .fetchone()
    )


    if existing:

        return existing[
            "scheme_id"
        ]


    cursor = conn.execute(
        """
        INSERT INTO master_scheme (
            scheme_code,
            scheme_name
        )

        VALUES (
            ?,
            ?
        )
        """,
        (
            scheme_code,
            scheme_name,
        ),
    )


    return cursor.lastrowid


# ============================================================
# GET OR CREATE CATEGORY
# ============================================================

def get_or_create_category(
    conn,
    scheme_id,
    category_code,
    category_name,
):

    existing = (
        conn.execute(
            """
            SELECT category_id

            FROM master_category

            WHERE scheme_id = ?
            AND category_code = ?
            AND category_name = ?
            """,
            (
                scheme_id,
                category_code,
                category_name,
            ),
        )
        .fetchone()
    )


    if existing:

        return existing[
            "category_id"
        ]


    cursor = conn.execute(
        """
        INSERT INTO master_category (
            scheme_id,
            category_code,
            category_name
        )

        VALUES (
            ?,
            ?,
            ?
        )
        """,
        (
            scheme_id,
            category_code,
            category_name,
        ),
    )


    return cursor.lastrowid


# ============================================================
# GET OR CREATE SUBCATEGORY
# ============================================================

def get_or_create_subcategory(
    conn,
    scheme_id,
    category_id,
    subcategory_code,
    subcategory_name,
):

    if category_id is None:

        existing = (
            conn.execute(
                """
                SELECT subcategory_id

                FROM master_subcategory

                WHERE scheme_id = ?

                AND category_id IS NULL

                AND subcategory_code = ?

                AND subcategory_name = ?
                """,
                (
                    scheme_id,
                    subcategory_code,
                    subcategory_name,
                ),
            )
            .fetchone()
        )


    else:

        existing = (
            conn.execute(
                """
                SELECT subcategory_id

                FROM master_subcategory

                WHERE scheme_id = ?

                AND category_id = ?

                AND subcategory_code = ?

                AND subcategory_name = ?
                """,
                (
                    scheme_id,
                    category_id,
                    subcategory_code,
                    subcategory_name,
                ),
            )
            .fetchone()
        )


    if existing:

        return existing[
            "subcategory_id"
        ]


    cursor = conn.execute(
        """
        INSERT INTO master_subcategory (
            scheme_id,
            category_id,
            subcategory_code,
            subcategory_name
        )

        VALUES (
            ?,
            ?,
            ?,
            ?
        )
        """,
        (
            scheme_id,
            category_id,
            subcategory_code,
            subcategory_name,
        ),
    )


    return cursor.lastrowid


# ============================================================
# GET OR CREATE PRODUCT SERVICE
# ============================================================

def get_or_create_product_service(
    conn,
    scheme_id,
    category_id,
    subcategory_id,
    product_service_code,
    product_service_name,
):

    query = """
        SELECT product_service_id

        FROM master_product_service

        WHERE scheme_id = ?

        AND product_service_code = ?

        AND product_service_name = ?
    """


    params = [
        scheme_id,
        product_service_code,
        product_service_name,
    ]


    if category_id is None:

        query += """
            AND category_id IS NULL
        """

    else:

        query += """
            AND category_id = ?
        """

        params.append(
            category_id
        )


    if subcategory_id is None:

        query += """
            AND subcategory_id IS NULL
        """

    else:

        query += """
            AND subcategory_id = ?
        """

        params.append(
            subcategory_id
        )


    existing = (
        conn.execute(
            query,
            params,
        )
        .fetchone()
    )


    if existing:

        return existing[
            "product_service_id"
        ]


    cursor = conn.execute(
        """
        INSERT INTO master_product_service (
            scheme_id,
            category_id,
            subcategory_id,
            product_service_code,
            product_service_name
        )

        VALUES (
            ?,
            ?,
            ?,
            ?,
            ?
        )
        """,
        (
            scheme_id,
            category_id,
            subcategory_id,
            product_service_code,
            product_service_name,
        ),
    )


    return cursor.lastrowid


# ============================================================
# CHECK DUPLICATE ID JENIS
#
# UNIQUE:
#
# SKEMA
# + KATEGORI
# + SUB KATEGORI
# + ID JENIS
# ============================================================

def find_duplicate_product_code(
    conn,
    scheme_id,
    category_id,
    subcategory_id,
    product_service_code,
):

    query = """
        SELECT
            path.path_id,

            product.product_service_code,
            product.product_service_name

        FROM master_product_path AS path


        JOIN master_product_service AS product

            ON product.product_service_id
            =
            path.product_service_id


        WHERE path.scheme_id = ?

        AND path.product_service_status = 'VALUE'

        AND product.product_service_code = ?
    """


    params = [
        scheme_id,
        product_service_code,
    ]


    # ========================================================
    # CATEGORY
    # ========================================================

    if category_id is None:

        query += """
            AND path.category_id IS NULL
        """

    else:

        query += """
            AND path.category_id = ?
        """

        params.append(
            category_id
        )


    # ========================================================
    # SUBCATEGORY
    # ========================================================

    if subcategory_id is None:

        query += """
            AND path.subcategory_id IS NULL
        """

    else:

        query += """
            AND path.subcategory_id = ?
        """

        params.append(
            subcategory_id
        )


    query += """
        LIMIT 1
    """


    return (
        conn.execute(
            query,
            params,
        )
        .fetchone()
    )


# ============================================================
# PATH EXISTS
# ============================================================

def path_exists(
    conn,
    scheme_id,
    category_id,
    subcategory_id,
    product_service_id,
    category_status,
    subcategory_status,
    product_service_status,
):

    conditions = [
        "scheme_id = ?",
        "category_status = ?",
        "subcategory_status = ?",
        "product_service_status = ?",
    ]


    params = [
        scheme_id,
        category_status,
        subcategory_status,
        product_service_status,
    ]


    # ========================================================
    # CATEGORY
    # ========================================================

    if category_id is None:

        conditions.append(
            "category_id IS NULL"
        )

    else:

        conditions.append(
            "category_id = ?"
        )

        params.append(
            category_id
        )


    # ========================================================
    # SUBCATEGORY
    # ========================================================

    if subcategory_id is None:

        conditions.append(
            "subcategory_id IS NULL"
        )

    else:

        conditions.append(
            "subcategory_id = ?"
        )

        params.append(
            subcategory_id
        )


    # ========================================================
    # PRODUCT SERVICE
    # ========================================================

    if product_service_id is None:

        conditions.append(
            "product_service_id IS NULL"
        )

    else:

        conditions.append(
            "product_service_id = ?"
        )

        params.append(
            product_service_id
        )


    query = (
        """
        SELECT path_id

        FROM master_product_path

        WHERE
        """
        +
        " AND ".join(
            conditions
        )
        +
        """
        LIMIT 1
        """
    )


    existing = (
        conn.execute(
            query,
            params,
        )
        .fetchone()
    )


    return (
        existing is not None
    )


# ============================================================
# IMPORT
# ============================================================

def import_products(
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
    # READ
    # ========================================================

    dataframe = (
        read_product_file(
            file_content,
            filename,
        )
    )


    validate_columns(
        dataframe
    )


    dataframe = (
        dataframe[
            EXPECTED_COLUMNS
        ]
    )


    # ========================================================
    # REMOVE FULL EMPTY ROW
    # ========================================================

    dataframe = (
        dataframe.dropna(
            how="all"
        )
    )


    # ========================================================
    # VALIDATE ALL ROWS FIRST
    # ========================================================

    for (
        index,
        row,
    ) in dataframe.iterrows():

        validate_row(
            row,
            index + 2,
        )


    # ========================================================
    # DATABASE
    # ========================================================

    conn = get_connection()


    inserted_path_count = 0

    existing_path_count = 0


    try:

        conn.execute(
            "BEGIN"
        )


        # ====================================================
        # REPLACE
        # ====================================================

        if (
            import_mode
            ==
            "replace"
        ):

            conn.execute(
                """
                DELETE FROM master_product_path
                """
            )


            conn.execute(
                """
                DELETE FROM master_product_service
                """
            )


            conn.execute(
                """
                DELETE FROM master_subcategory
                """
            )


            conn.execute(
                """
                DELETE FROM master_category
                """
            )


            conn.execute(
                """
                DELETE FROM master_scheme
                """
            )


        # ====================================================
        # LOOP
        # ====================================================

        for (
            index,
            row,
        ) in dataframe.iterrows():

            source_row = (
                index + 2
            )


            # =================================================
            # SCHEME
            # =================================================

            scheme_name = (
                value_to_text(
                    row[
                        "skema"
                    ]
                )
            )


            scheme_code = (
                value_to_text(
                    row[
                        "id_skema"
                    ]
                )
            )


            scheme_id = (
                get_or_create_scheme(
                    conn,
                    scheme_code,
                    scheme_name,
                )
            )


            # =================================================
            # CATEGORY
            # =================================================

            category_status = (
                detect_status(
                    row[
                        "kategori"
                    ]
                )
            )


            category_id = None


            if (
                category_status
                ==
                STATUS_VALUE
            ):

                category_id = (
                    get_or_create_category(
                        conn,
                        scheme_id,
                        value_to_text(
                            row[
                                "id_kategori"
                            ]
                        ),
                        value_to_text(
                            row[
                                "kategori"
                            ]
                        ),
                    )
                )


            # =================================================
            # SUBCATEGORY
            # =================================================

            subcategory_status = (
                detect_status(
                    row[
                        "sub_kategori"
                    ]
                )
            )


            subcategory_id = None


            if (
                subcategory_status
                ==
                STATUS_VALUE
            ):

                subcategory_id = (
                    get_or_create_subcategory(
                        conn,
                        scheme_id,
                        category_id,
                        value_to_text(
                            row[
                                "id_sub_kategori"
                            ]
                        ),
                        value_to_text(
                            row[
                                "sub_kategori"
                            ]
                        ),
                    )
                )


            # =================================================
            # PRODUCT SERVICE
            # =================================================

            product_service_status = (
                detect_status(
                    row[
                        "jenis"
                    ]
                )
            )


            product_service_id = None


            if (
                product_service_status
                ==
                STATUS_VALUE
            ):

                product_service_code = (
                    value_to_text(
                        row[
                            "id_jenis"
                        ]
                    )
                )


                product_service_name = (
                    value_to_text(
                        row[
                            "jenis"
                        ]
                    )
                )


                # =============================================
                # DUPLICATE ID JENIS
                # =============================================

                duplicate = (
                    find_duplicate_product_code(
                        conn=conn,

                        scheme_id=(
                            scheme_id
                        ),

                        category_id=(
                            category_id
                        ),

                        subcategory_id=(
                            subcategory_id
                        ),

                        product_service_code=(
                            product_service_code
                        ),
                    )
                )


                if duplicate:

                    raise ValueError(
                        (
                            f"Baris {source_row}: "
                            f"ID Jenis "
                            f"'{product_service_code}' "
                            "sudah digunakan pada "
                            "Skema/Kategori/Sub Kategori "
                            "yang sama oleh Jenis "
                            f"'{duplicate['product_service_name']}'. "
                            "Gunakan ID Jenis "
                            "yang berbeda."
                        )
                    )


                product_service_id = (
                    get_or_create_product_service(
                        conn,
                        scheme_id,
                        category_id,
                        subcategory_id,
                        product_service_code,
                        product_service_name,
                    )
                )


            # =================================================
            # CHECK PATH
            # =================================================

            exists = (
                path_exists(
                    conn,
                    scheme_id,
                    category_id,
                    subcategory_id,
                    product_service_id,
                    category_status,
                    subcategory_status,
                    product_service_status,
                )
            )


            if exists:

                existing_path_count += 1

                continue


            # =================================================
            # INSERT PATH
            # =================================================

            conn.execute(
                """
                INSERT INTO master_product_path (
                    scheme_id,
                    category_id,
                    subcategory_id,
                    product_service_id,
                    category_status,
                    subcategory_status,
                    product_service_status,
                    source_row
                )

                VALUES (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (
                    scheme_id,
                    category_id,
                    subcategory_id,
                    product_service_id,

                    category_status,
                    subcategory_status,
                    product_service_status,

                    source_row,
                ),
            )


            inserted_path_count += 1


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

            "inserted_path_count":
                inserted_path_count,

            "existing_path_count":
                existing_path_count,
        }


    except Exception:

        conn.rollback()

        raise


    finally:

        conn.close()