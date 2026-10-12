from pathlib import Path

from urllib.parse import urlencode

from io import BytesIO, StringIO

import csv


from fastapi import (
    APIRouter,
    Request,
    UploadFile,
    File,
    Form,
    HTTPException,
)


from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    StreamingResponse,
)


from fastapi.templating import (
    Jinja2Templates,
)


from openpyxl import Workbook

from openpyxl.styles import Font


from app.database import (
    get_connection,
)


from app.services.standard_import import (
    import_standards,
)


# ============================================================
# ROUTER
# ============================================================

router = APIRouter()


# ============================================================
# TEMPLATE
# ============================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)


templates = Jinja2Templates(
    directory=str(
        BASE_DIR / "templates"
    )
)


# ============================================================
# COLUMNS
# ============================================================

STANDARD_COLUMNS = [
    "id_standar",
    "nomor_acuan_standar",
    "judul_acuan_standar",
]


# ============================================================
# FORMAT CODE
# ============================================================

def format_standard_code(
    number,
):

    return (
        f"STD-{int(number):04d}"
    )


# ============================================================
# VALIDATE CODE
# ============================================================

def validate_standard_code(
    code,
):

    if not code:

        raise ValueError(
            "ID Standar wajib diisi."
        )


    code_text = str(
        code
    )


    if not code_text.startswith(
        "STD-"
    ):

        raise ValueError(
            (
                "Format ID Standar tidak valid. "
                "Gunakan format STD-XXXX, "
                "contoh STD-0001."
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
        or
        not number_part.isdigit()
    ):

        raise ValueError(
            (
                "Format ID Standar tidak valid. "
                "Gunakan format STD-XXXX, "
                "contoh STD-0001."
            )
        )


# ============================================================
# VALIDATE NUMBER
# ============================================================

def validate_standard_number(
    standard_number,
):

    if not standard_number:

        raise ValueError(
            "Nomor Acuan Standar wajib diisi."
        )


# ============================================================
# VALIDATE TITLE
# ============================================================

def validate_standard_title(
    standard_title,
):

    if not standard_title:

        raise ValueError(
            "Judul Acuan Standar wajib diisi."
        )


# ============================================================
# GENERATE NEXT CODE
# ============================================================

def generate_next_standard_code(
    conn,
):

    rows = (
        conn.execute(
            """
            SELECT
                standard_code

            FROM master_standard

            WHERE standard_code IS NOT NULL
            """
        )
        .fetchall()
    )


    max_number = 0


    for row in rows:

        code = (
            row[
                "standard_code"
            ]
        )


        if code is None:

            continue


        code_text = str(
            code
        )


        if not code_text.startswith(
            "STD-"
        ):

            continue


        number_part = (
            code_text[4:]
        )


        if not number_part.isdigit():

            continue


        number = int(
            number_part
        )


        if number > max_number:

            max_number = number


    next_number = (
        max_number + 1
    )


    return (
        format_standard_code(
            next_number
        )
    )


# ============================================================
# FIND DUPLICATE CODE
# ============================================================

def find_duplicate_code(
    conn,
    code,
    exclude_id=None,
):

    query = """
        SELECT
            standard_id,
            standard_code,
            standard_number,
            standard_title

        FROM master_standard

        WHERE standard_code = ?
    """


    params = [
        code,
    ]


    if exclude_id is not None:

        query += """
            AND standard_id != ?
        """

        params.append(
            exclude_id
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
# FIND DUPLICATE STANDARD NUMBER
# ============================================================

def find_duplicate_number(
    conn,
    standard_number,
    exclude_id=None,
):

    query = """
        SELECT
            standard_id,
            standard_code,
            standard_number,
            standard_title

        FROM master_standard

        WHERE standard_number = ?
    """


    params = [
        standard_number,
    ]


    if exclude_id is not None:

        query += """
            AND standard_id != ?
        """

        params.append(
            exclude_id
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
# LIST
# ============================================================

@router.get(
    "/standards",
    response_class=HTMLResponse,
)
def standard_list(
    request: Request,
    search: str = "",
    result: str = "",
    message: str = "",
):

    conn = get_connection()


    try:

        query = """
            SELECT
                standard_id,
                standard_code,
                standard_number,
                standard_title

            FROM master_standard

            WHERE 1 = 1
        """


        params = []


        if search.strip():

            query += """
                AND (
                    LOWER(
                        standard_code
                    )
                    LIKE LOWER(?)

                    OR LOWER(
                        standard_number
                    )
                    LIKE LOWER(?)

                    OR LOWER(
                        standard_title
                    )
                    LIKE LOWER(?)
                )
            """


            keyword = (
                f"%{search.strip()}%"
            )


            params.extend(
                [
                    keyword,
                    keyword,
                    keyword,
                ]
            )


        query += """
            ORDER BY
                CAST(
                    SUBSTR(
                        standard_code,
                        5
                    )
                    AS INTEGER
                ),
                standard_number,
                standard_title
        """


        items = (
            conn.execute(
                query,
                params,
            )
            .fetchall()
        )


        total = (
            conn.execute(
                """
                SELECT COUNT(*) AS total

                FROM master_standard
                """
            )
            .fetchone()["total"]
        )


    finally:

        conn.close()


    return templates.TemplateResponse(
        request=request,

        name="standards/list.html",

        context={
            "items":
                items,

            "search":
                search,

            "result":
                result,

            "message":
                message,

            "total":
                total,
        },
    )


# ============================================================
# CREATE PAGE
# ============================================================

@router.get(
    "/standards/create",
    response_class=HTMLResponse,
)
def standard_create_page(
    request: Request,
    status: str = "",
    message: str = "",
):

    conn = get_connection()


    try:

        next_code = (
            generate_next_standard_code(
                conn
            )
        )


    finally:

        conn.close()


    return templates.TemplateResponse(
        request=request,

        name="standards/create.html",

        context={
            "status":
                status,

            "message":
                message,

            "next_code":
                next_code,
        },
    )


# ============================================================
# CREATE PROCESS
# ============================================================

@router.post(
    "/standards/create"
)
def standard_create_process(
    standard_number: str = Form(...),
    standard_title: str = Form(...),
):

    conn = get_connection()


    try:

        validate_standard_number(
            standard_number
        )


        validate_standard_title(
            standard_title
        )


        conn.execute(
            "BEGIN"
        )


        # ====================================================
        # GENERATE CODE FROM DATABASE
        # ====================================================

        standard_code = (
            generate_next_standard_code(
                conn
            )
        )


        validate_standard_code(
            standard_code
        )


        # ====================================================
        # DUPLICATE NUMBER + TITLE
        # ====================================================

# ====================================================
# DUPLICATE NOMOR ACUAN
# ====================================================

        duplicate_number = (
            find_duplicate_number(
                conn,
                standard_number,
            )
        )


        if duplicate_number:

            raise ValueError(
                (
                    "Nomor Acuan Standar "
                    f"'{standard_number}' "
                    "sudah tersedia dengan ID "
                    f"'{duplicate_number['standard_code']}'. "
                    "Nomor Acuan Standar tidak boleh duplikat."
                )
            )

        # ====================================================
        # DUPLICATE CODE
        # ====================================================

        duplicate_code = (
            find_duplicate_code(
                conn,
                standard_code,
            )
        )


        if duplicate_code:

            raise ValueError(
                (
                    "ID Standar "
                    f"'{standard_code}' "
                    "sudah digunakan. "
                    "Silakan coba simpan kembali."
                )
            )


        # ====================================================
        # INSERT
        # ====================================================

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
                standard_code,
                standard_number,
                standard_title,
            ),
        )


        conn.commit()


    except Exception as exc:

        conn.rollback()


        query = urlencode(
            {
                "status":
                    "failed",

                "message":
                    str(
                        exc
                    ),
            }
        )


        return RedirectResponse(
            url=(
                "/standards/create?"
                + query
            ),

            status_code=303,
        )


    finally:

        conn.close()


    query = urlencode(
        {
            "result":
                "success",

            "message":
                (
                    "Data Master Standar "
                    "berhasil ditambahkan."
                ),
        }
    )


    return RedirectResponse(
        url=(
            "/standards?"
            + query
        ),

        status_code=303,
    )


# ============================================================
# EDIT PAGE
# ============================================================

@router.get(
    "/standards/{standard_id}/edit",
    response_class=HTMLResponse,
)
def standard_edit_page(
    request: Request,
    standard_id: int,
    status: str = "",
    message: str = "",
):

    conn = get_connection()


    try:

        item = (
            conn.execute(
                """
                SELECT
                    standard_id,
                    standard_code,
                    standard_number,
                    standard_title

                FROM master_standard

                WHERE standard_id = ?
                """,
                (
                    standard_id,
                ),
            )
            .fetchone()
        )


        if item is None:

            raise HTTPException(
                status_code=404,

                detail=(
                    "Data Master Standar "
                    "tidak ditemukan."
                ),
            )


    finally:

        conn.close()


    return templates.TemplateResponse(
        request=request,

        name="standards/edit.html",

        context={
            "item":
                item,

            "status":
                status,

            "message":
                message,
        },
    )


# ============================================================
# EDIT PROCESS
# ============================================================

@router.post(
    "/standards/{standard_id}/edit"
)
def standard_edit_process(
    standard_id: int,
    standard_number: str = Form(...),
    standard_title: str = Form(...),
):

    conn = get_connection()


    try:

        existing = (
            conn.execute(
                """
                SELECT
                    standard_id,
                    standard_code

                FROM master_standard

                WHERE standard_id = ?
                """,
                (
                    standard_id,
                ),
            )
            .fetchone()
        )


        if existing is None:

            raise HTTPException(
                status_code=404,

                detail=(
                    "Data Master Standar "
                    "tidak ditemukan."
                ),
            )


        validate_standard_number(
            standard_number
        )


        validate_standard_title(
            standard_title
        )


        duplicate_pair = (
            find_duplicate_pair(
                conn,
                standard_number,
                standard_title,
                exclude_id=(
                    standard_id
                ),
            )
        )


        if duplicate_pair:

            raise ValueError(
                (
                    "Kombinasi Nomor Acuan Standar "
                    "dan Judul Acuan Standar "
                    "sudah digunakan oleh ID "
                    f"'{duplicate_pair['standard_code']}'."
                )
            )


        conn.execute(
            """
            UPDATE master_standard

            SET
                standard_number = ?,
                standard_title = ?,
                updated_at = CURRENT_TIMESTAMP

            WHERE standard_id = ?
            """,
            (
                standard_number,
                standard_title,
                standard_id,
            ),
        )


        conn.commit()


    except HTTPException:

        conn.rollback()

        raise


    except Exception as exc:

        conn.rollback()


        query = urlencode(
            {
                "status":
                    "failed",

                "message":
                    str(
                        exc
                    ),
            }
        )


        return RedirectResponse(
            url=(
                f"/standards/{standard_id}/edit?"
                + query
            ),

            status_code=303,
        )


    finally:

        conn.close()


    query = urlencode(
        {
            "result":
                "success",

            "message":
                (
                    "Data Master Standar "
                    "berhasil diperbarui."
                ),
        }
    )


    return RedirectResponse(
        url=(
            "/standards?"
            + query
        ),

        status_code=303,
    )


# ============================================================
# DELETE
# ============================================================

@router.post(
    "/standards/{standard_id}/delete"
)
def standard_delete(
    standard_id: int,
):

    conn = get_connection()


    try:

        existing = (
            conn.execute(
                """
                SELECT
                    standard_id,
                    standard_code

                FROM master_standard

                WHERE standard_id = ?
                """,
                (
                    standard_id,
                ),
            )
            .fetchone()
        )


        if existing is None:

            raise ValueError(
                (
                    "Data Master Standar "
                    "tidak ditemukan."
                )
            )


        conn.execute(
            """
            DELETE FROM master_standard

            WHERE standard_id = ?
            """,
            (
                standard_id,
            ),
        )


        conn.commit()


        result = "success"

        message = (
            "Data Master Standar "
            "berhasil dihapus."
        )


    except Exception as exc:

        conn.rollback()


        result = "failed"

        message = str(
            exc
        )


    finally:

        conn.close()


    query = urlencode(
        {
            "result":
                result,

            "message":
                message,
        }
    )


    return RedirectResponse(
        url=(
            "/standards?"
            + query
        ),

        status_code=303,
    )


# ============================================================
# IMPORT PAGE
# ============================================================

@router.get(
    "/standards/import",
    response_class=HTMLResponse,
)
def standard_import_page(
    request: Request,
    status: str = "",
    message: str = "",
    import_mode: str = "",
    total_rows: int = 0,
    inserted_count: int = 0,
    existing_count: int = 0,
):

    success_message = None

    error_message = None

    import_result = None


    if status == "success":

        success_message = (
            message

            or

            "Master Standar berhasil di-import."
        )


        import_result = {
            "import_mode":
                import_mode,

            "total_rows":
                total_rows,

            "inserted_count":
                inserted_count,

            "existing_count":
                existing_count,
        }


    elif status == "failed":

        error_message = (
            message

            or

            "Import Master Standar gagal."
        )


    return templates.TemplateResponse(
        request=request,

        name="standards/import.html",

        context={
            "success_message":
                success_message,

            "error_message":
                error_message,

            "import_result":
                import_result,
        },
    )


# ============================================================
# IMPORT PROCESS
# ============================================================

@router.post(
    "/standards/import"
)
async def standard_import_process(
    file: UploadFile = File(...),
    import_mode: str = Form(...),
):

    try:

        if not file.filename:

            raise ValueError(
                "Nama file tidak ditemukan."
            )


        filename_lower = (
            file.filename.lower()
        )


        allowed_extensions = (
            ".xlsx",
            ".xls",
            ".csv",
        )


        if not filename_lower.endswith(
            allowed_extensions
        ):

            raise ValueError(
                (
                    "Format file tidak didukung. "
                    "Gunakan .xlsx, .xls, atau .csv."
                )
            )


        file_content = (
            await file.read()
        )


        if not file_content:

            raise ValueError(
                "File yang di-upload kosong."
            )


        result = (
            import_standards(
                file_content=(
                    file_content
                ),
                filename=(
                    file.filename
                ),
                import_mode=(
                    import_mode
                ),
            )
        )


        mode_name = (
            "Upload Ulang Semua Data"

            if import_mode
            ==
            "replace"

            else

            "Tambah Data"
        )


        query = urlencode(
            {
                "status":
                    "success",

                "message":
                    (
                        "Import berhasil menggunakan "
                        f"mode {mode_name}."
                    ),

                "import_mode":
                    result[
                        "import_mode"
                    ],

                "total_rows":
                    result[
                        "total_rows"
                    ],

                "inserted_count":
                    result[
                        "inserted_count"
                    ],

                "existing_count":
                    result[
                        "existing_count"
                    ],
            }
        )


        return RedirectResponse(
            url=(
                "/standards/import?"
                + query
            ),

            status_code=303,
        )


    except Exception as exc:

        query = urlencode(
            {
                "status":
                    "failed",

                "message":
                    str(
                        exc
                    ),
            }
        )


        return RedirectResponse(
            url=(
                "/standards/import?"
                + query
            ),

            status_code=303,
        )


# ============================================================
# DOWNLOAD TEMPLATE
# ============================================================

@router.get(
    "/standards/template"
)
def download_standard_template():

    workbook = Workbook()

    worksheet = (
        workbook.active
    )

    worksheet.title = (
        "Master Standar"
    )


    for (
        column_index,
        column_name,
    ) in enumerate(
        STANDARD_COLUMNS,
        start=1,
    ):

        cell = worksheet.cell(
            row=1,
            column=(
                column_index
            ),
            value=(
                column_name
            ),
        )


        cell.font = Font(
            bold=True
        )


    worksheet.freeze_panes = (
        "A2"
    )


    worksheet.column_dimensions[
        "A"
    ].width = 18


    worksheet.column_dimensions[
        "B"
    ].width = 35


    worksheet.column_dimensions[
        "C"
    ].width = 80


    output = BytesIO()


    workbook.save(
        output
    )


    output.seek(
        0
    )


    return StreamingResponse(
        output,

        media_type=(
            "application/"
            "vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),

        headers={
            "Content-Disposition":
                (
                    "attachment; "
                    "filename=Template_Master_Standar.xlsx"
                )
        },
    )


# ============================================================
# EXPORT XLSX
# ============================================================

@router.get(
    "/standards/export/xlsx"
)
def export_standard_xlsx():

    conn = get_connection()


    try:

        rows = (
            conn.execute(
                """
                SELECT
                    standard_code,
                    standard_number,
                    standard_title

                FROM master_standard

                ORDER BY
                    CAST(
                        SUBSTR(
                            standard_code,
                            5
                        )
                        AS INTEGER
                    ),
                    standard_number,
                    standard_title
                """
            )
            .fetchall()
        )


    finally:

        conn.close()


    workbook = Workbook()

    worksheet = (
        workbook.active
    )

    worksheet.title = (
        "Master Standar"
    )


    for (
        column_index,
        column_name,
    ) in enumerate(
        STANDARD_COLUMNS,
        start=1,
    ):

        cell = worksheet.cell(
            row=1,
            column=(
                column_index
            ),
            value=(
                column_name
            ),
        )


        cell.font = Font(
            bold=True
        )


    for (
        row_index,
        row,
    ) in enumerate(
        rows,
        start=2,
    ):

        worksheet.cell(
            row=row_index,
            column=1,
            value=(
                row[
                    "standard_code"
                ]
            ),
        )


        worksheet.cell(
            row=row_index,
            column=2,
            value=(
                row[
                    "standard_number"
                ]
            ),
        )


        worksheet.cell(
            row=row_index,
            column=3,
            value=(
                row[
                    "standard_title"
                ]
            ),
        )


    worksheet.freeze_panes = (
        "A2"
    )


    worksheet.auto_filter.ref = (
        worksheet.dimensions
    )


    worksheet.column_dimensions[
        "A"
    ].width = 18


    worksheet.column_dimensions[
        "B"
    ].width = 35


    worksheet.column_dimensions[
        "C"
    ].width = 80


    output = BytesIO()


    workbook.save(
        output
    )


    output.seek(
        0
    )


    return StreamingResponse(
        output,

        media_type=(
            "application/"
            "vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),

        headers={
            "Content-Disposition":
                (
                    "attachment; "
                    "filename=Master_Standar.xlsx"
                )
        },
    )


# ============================================================
# EXPORT CSV
# ============================================================

@router.get(
    "/standards/export/csv"
)
def export_standard_csv():

    conn = get_connection()


    try:

        rows = (
            conn.execute(
                """
                SELECT
                    standard_code,
                    standard_number,
                    standard_title

                FROM master_standard

                ORDER BY
                    CAST(
                        SUBSTR(
                            standard_code,
                            5
                        )
                        AS INTEGER
                    ),
                    standard_number,
                    standard_title
                """
            )
            .fetchall()
        )


    finally:

        conn.close()


    output = StringIO(
        newline=""
    )


    writer = csv.writer(
        output
    )


    writer.writerow(
        STANDARD_COLUMNS
    )


    for row in rows:

        writer.writerow(
            [
                row[
                    "standard_code"
                ],

                row[
                    "standard_number"
                ],

                row[
                    "standard_title"
                ],
            ]
        )


    csv_content = (
        "\ufeff"
        +
        output.getvalue()
    )


    return StreamingResponse(
        iter(
            [
                csv_content.encode(
                    "utf-8"
                )
            ]
        ),

        media_type=(
            "text/csv; charset=utf-8"
        ),

        headers={
            "Content-Disposition":
                (
                    "attachment; "
                    "filename=Master_Standar.csv"
                )
        },
    )