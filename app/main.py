from pathlib import Path

from urllib.parse import urlencode


from fastapi import (
    FastAPI,
    Request,
    HTTPException,
)


from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)


from fastapi.templating import (
    Jinja2Templates,
)


from fastapi.staticfiles import (
    StaticFiles,
)


from app.database import (
    get_connection,
)


from app.services.institution_sync import (
    sync_institutions,
    get_sync_lock_status,
    SyncBusyError,
)


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title=(
        "Sistem Database "
        "Lembaga Sertifikasi"
    )
)


# ============================================================
# PATH
# ============================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
)


TEMPLATE_DIR = (
    BASE_DIR
    / "templates"
)


STATIC_DIR = (
    BASE_DIR
    / "static"
)


# ============================================================
# TEMPLATE
# ============================================================

templates = Jinja2Templates(
    directory=str(
        TEMPLATE_DIR
    )
)


# ============================================================
# STATIC
# ============================================================

app.mount(
    "/static",

    StaticFiles(
        directory=str(
            STATIC_DIR
        )
    ),

    name="static",
)


# ============================================================
# DASHBOARD
# ============================================================

@app.get(
    "/",
    response_class=HTMLResponse,
)
def dashboard(
    request: Request,
):

    conn = get_connection()

    try:

        total_institution = (
            conn.execute(
                """
                SELECT COUNT(*) AS total

                FROM institution

                WHERE source_status =
                    'AVAILABLE'
                """
            )
            .fetchone()["total"]
        )


        active_count = (
            conn.execute(
                """
                SELECT COUNT(*) AS total

                FROM institution

                WHERE source_status =
                    'AVAILABLE'

                AND LOWER(
                    status_accreditation
                ) = 'active'
                """
            )
            .fetchone()["total"]
        )


        withdrawn_count = (
            conn.execute(
                """
                SELECT COUNT(*) AS total

                FROM institution

                WHERE source_status =
                    'AVAILABLE'

                AND LOWER(
                    status_accreditation
                ) = 'withdrawn'
                """
            )
            .fetchone()["total"]
        )


        total_amendment = (
            conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM institution_amendment
                """
            )
            .fetchone()["total"]
        )


        last_sync = (
            conn.execute(
                """
                SELECT *

                FROM sync_history

                ORDER BY sync_id DESC

                LIMIT 1
                """
            )
            .fetchone()
        )


    finally:

        conn.close()


    sync_lock = (
        get_sync_lock_status()
    )


    return templates.TemplateResponse(
        request=request,

        name="dashboard.html",

        context={
            "total_institution":
                total_institution,

            "active_count":
                active_count,

            "withdrawn_count":
                withdrawn_count,

            "total_amendment":
                total_amendment,

            "last_sync":
                last_sync,

            "sync_lock":
                sync_lock,
        },
    )


# ============================================================
# SYNC MASTER LEMBAGA
# ============================================================

@app.post(
    "/institutions/sync"
)
def sync_master_institutions():

    try:

        result = (
            sync_institutions()
        )


        message = (
            f"Total {result['total_source']} | "
            f"Baru {result['inserted_count']} | "
            f"Diperbarui {result['updated_count']} | "
            f"Tidak berubah {result['unchanged_count']} | "
            f"Hilang dari sumber "
            f"{result['missing_count']}"
        )


        query = urlencode(
            {
                "sync":
                    "success",

                "message":
                    message,
            }
        )


        return RedirectResponse(
            url=(
                "/institutions?"
                + query
            ),

            status_code=303,
        )


    except SyncBusyError as exc:

        query = urlencode(
            {
                "sync":
                    "busy",

                "message":
                    str(exc),
            }
        )


        return RedirectResponse(
            url=(
                "/institutions?"
                + query
            ),

            status_code=303,
        )


    except Exception as exc:

        query = urlencode(
            {
                "sync":
                    "failed",

                "message":
                    str(exc),
            }
        )


        return RedirectResponse(
            url=(
                "/institutions?"
                + query
            ),

            status_code=303,
        )


# ============================================================
# MASTER LEMBAGA
# ============================================================

@app.get(
    "/institutions",
    response_class=HTMLResponse,
)
def institution_list(
    request: Request,

    search: str = "",

    status: str = "",

    sync: str = "",

    message: str = "",
):

    conn = get_connection()

    try:

        query = """
            SELECT
                institution.*,

                COUNT(
                    institution_amendment.amendment_id
                ) AS amendment_count

            FROM institution

            LEFT JOIN institution_amendment
                ON institution.institution_id
                =
                institution_amendment.institution_id

            WHERE institution.source_status =
                'AVAILABLE'
        """


        params = []


        # ====================================================
        # SEARCH
        # ====================================================

        if search.strip():

            query += """
                AND (
                    LOWER(
                        institution.id_lspro
                    ) LIKE LOWER(?)

                    OR LOWER(
                        institution.name_lspro
                    ) LIKE LOWER(?)

                    OR LOWER(
                        institution.kab_kota
                    ) LIKE LOWER(?)

                    OR LOWER(
                        institution.propinsi
                    ) LIKE LOWER(?)

                    OR LOWER(
                        institution.cp
                    ) LIKE LOWER(?)
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
                    keyword,
                    keyword,
                ]
            )


        # ====================================================
        # STATUS
        # ====================================================

        if status.strip():

            query += """
                AND LOWER(
                    institution.status_accreditation
                ) = LOWER(?)
            """


            params.append(
                status.strip()
            )


        # ====================================================
        # GROUP & ORDER
        # ====================================================

        query += """
            GROUP BY
                institution.institution_id

            ORDER BY
                institution.id_lspro
        """


        institutions = (
            conn.execute(
                query,
                params,
            )
            .fetchall()
        )


        last_sync = (
            conn.execute(
                """
                SELECT *

                FROM sync_history

                ORDER BY sync_id DESC

                LIMIT 1
                """
            )
            .fetchone()
        )


    finally:

        conn.close()


    sync_lock = (
        get_sync_lock_status()
    )


    return templates.TemplateResponse(
        request=request,

        name=(
            "institutions/list.html"
        ),

        context={
            "institutions":
                institutions,

            "search":
                search,

            "status":
                status,

            "sync":
                sync,

            "message":
                message,

            "last_sync":
                last_sync,

            "sync_lock":
                sync_lock,
        },
    )


# ============================================================
# DETAIL LEMBAGA
# ============================================================

@app.get(
    "/institutions/{institution_id}",
    response_class=HTMLResponse,
)
def institution_detail(
    request: Request,

    institution_id: int,
):

    conn = get_connection()

    try:

        institution = (
            conn.execute(
                """
                SELECT *

                FROM institution

                WHERE institution_id = ?
                """,
                (
                    institution_id,
                ),
            )
            .fetchone()
        )


        if institution is None:

            raise HTTPException(
                status_code=404,

                detail=(
                    "Data lembaga "
                    "tidak ditemukan."
                ),
            )


        amendments = (
            conn.execute(
                """
                SELECT *

                FROM institution_amendment

                WHERE institution_id = ?

                ORDER BY
                    amendment_no ASC
                """,
                (
                    institution_id,
                ),
            )
            .fetchall()
        )


        amendment_count = len(
            amendments
        )


        latest_amendment = (
            amendments[-1]
            if amendments
            else None
        )


    finally:

        conn.close()


    return templates.TemplateResponse(
        request=request,

        name=(
            "institutions/detail.html"
        ),

        context={
            "institution":
                institution,

            "amendments":
                amendments,

            "amendment_count":
                amendment_count,

            "latest_amendment":
                latest_amendment,
        },
    )