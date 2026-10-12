from pathlib import Path
from math import ceil
from urllib.parse import urlencode

from fastapi import (
    APIRouter,
    Request,
    UploadFile,
    File,
    Form,
)

from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)

from fastapi.templating import (
    Jinja2Templates,
)

from app.database import get_connection

from app.services.scope_batch_import import (
    import_scope_batch,
    recalculate_scope_batch,
)

from app.services.scope_import import (
    load_institutions,
    load_product_paths,
    load_standards,
    load_certification_schemes,
    match_institution,
    match_product_path,
    match_standard,
    match_certification_scheme,
)


# ============================================================
# ROUTER / TEMPLATE
# ============================================================

router = APIRouter()

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
# HELPERS
# ============================================================

TERMINAL_BATCH_STATUSES = {
    "COMMITTED",
    "REJECTED",
    "FAILED",
}


def get_batch(
    conn,
    batch_id,
):
    batch = (
        conn.execute(
            """
            SELECT *
            FROM scope_upload_batch
            WHERE batch_id = ?
            """,
            (
                batch_id,
            ),
        )
        .fetchone()
    )

    if batch is None:
        raise ValueError(
            "Batch Ruang Lingkup tidak ditemukan."
        )

    return batch


def ensure_batch_editable(
    conn,
    batch_id,
):
    batch = get_batch(
        conn,
        batch_id,
    )

    if (
        batch[
            "status"
        ]
        in TERMINAL_BATCH_STATUSES
    ):
        raise ValueError(
            (
                "Batch sudah berstatus "
                f"{batch['status']} dan tidak dapat diubah."
            )
        )

    return batch


def pagination_meta(
    total,
    page,
    per_page,
):
    total_pages = max(
        1,
        ceil(
            total
            /
            per_page
        ),
    )

    page = min(
        max(
            1,
            page,
        ),
        total_pages,
    )

    offset = (
        page
        -
        1
    ) * per_page

    start_no = (
        offset
        +
        1
        if total
        else
        0
    )

    end_no = min(
        offset
        +
        per_page,
        total,
    )

    return {
        "page":
            page,

        "per_page":
            per_page,

        "total":
            total,

        "total_pages":
            total_pages,

        "offset":
            offset,

        "start_no":
            start_no,

        "end_no":
            end_no,
    }


def redirect_message(
    url,
    result,
    message,
):
    return RedirectResponse(
        url=(
            url
            +
            "?"
            +
            urlencode(
                {
                    "result":
                        result,

                    "message":
                        message,
                }
            )
        ),
        status_code=303,
    )


# ============================================================
# UPLOAD
# ============================================================

@router.get(
    "/scopes/import",
    response_class=HTMLResponse,
)
def scope_import_page(
    request: Request,
    result: str = "",
    message: str = "",
):
    conn = get_connection()

    try:
        recent_batches = (
            conn.execute(
                """
                SELECT
                    batch_id,
                    batch_code,
                    file_name,
                    import_mode,
                    status,
                    total_rows,
                    valid_count,
                    corrected_count,
                    review_count,
                    rejected_count,
                    uploaded_at

                FROM scope_upload_batch

                ORDER BY
                    batch_id DESC

                LIMIT 5
                """
            )
            .fetchall()
        )

    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="scopes/import.html",
        context={
            "recent_batches":
                recent_batches,

            "result":
                result,

            "message":
                message,
        },
    )


@router.post(
    "/scopes/import"
)
async def scope_import_process(
    file: UploadFile = File(...),
    import_mode: str = Form("REPLACE"),
):
    try:
        if not file.filename:
            raise ValueError(
                "Nama file tidak ditemukan."
            )

        if not file.filename.lower().endswith(
            (
                ".xlsx",
                ".xls",
                ".csv",
            )
        ):
            raise ValueError(
                "Gunakan file XLSX, XLS, atau CSV."
            )

        mode = (
            import_mode
            .strip()
            .upper()
        )

        if mode not in {
            "APPEND",
            "REPLACE",
        }:
            raise ValueError(
                "Mode import tidak valid."
            )

        content = (
            await file.read()
        )

        if not content:
            raise ValueError(
                "File yang di-upload kosong."
            )

        result = import_scope_batch(
            file_content=content,
            filename=file.filename,
            import_mode=mode,
        )

        return RedirectResponse(
            url=(
                f"/scopes/batches/"
                f"{result['batch_id']}/corrections"
            ),
            status_code=303,
        )

    except Exception as exc:
        return redirect_message(
            "/scopes/import",
            "failed",
            str(
                exc
            ),
        )


# ============================================================
# HISTORY
# ============================================================

@router.get(
    "/scopes/history",
    response_class=HTMLResponse,
)
def scope_history(
    request: Request,
    status_filter: str = "",
    search: str = "",
    result: str = "",
    message: str = "",
):
    conn = get_connection()

    try:
        query = """
            SELECT
                batch_id,
                batch_code,
                file_name,
                import_mode,
                status,
                total_rows,
                valid_count,
                corrected_count,
                review_count,
                rejected_count,
                uploaded_at,
                committed_at

            FROM scope_upload_batch

            WHERE 1 = 1
        """

        params = []

        if status_filter.strip():
            query += """
                AND status = ?
            """

            params.append(
                status_filter.strip()
            )

        if search.strip():
            keyword = (
                f"%{search.strip()}%"
            )

            query += """
                AND (
                    LOWER(batch_code)
                    LIKE LOWER(?)

                    OR LOWER(file_name)
                    LIKE LOWER(?)
                )
            """

            params.extend(
                [
                    keyword,
                    keyword,
                ]
            )

        query += """
            ORDER BY
                batch_id DESC
        """

        batches = (
            conn.execute(
                query,
                params,
            )
            .fetchall()
        )

    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="scopes/history.html",
        context={
            "batches":
                batches,

            "status_filter":
                status_filter,

            "search":
                search,

            "result":
                result,

            "message":
                message,
        },
    )


# ============================================================
# BATCH HOME
# ============================================================

@router.get(
    "/scopes/batches/{batch_id}",
    response_class=HTMLResponse,
)
def scope_batch_home(
    request: Request,
    batch_id: int,
):
    return RedirectResponse(
        url=(
            f"/scopes/batches/"
            f"{batch_id}/corrections"
        ),
        status_code=303,
    )


# ============================================================
# LEGACY REVIEW URL -> BATCH WORKFLOW
# ============================================================

@router.get(
    "/scopes/review"
)
def legacy_scope_review(
    batch_id: int | None = None,
):
    conn = get_connection()

    try:
        if batch_id is None:
            row = (
                conn.execute(
                    """
                    SELECT batch_id

                    FROM scope_upload_batch

                    WHERE status NOT IN (
                        'COMMITTED',
                        'REJECTED',
                        'FAILED'
                    )

                    ORDER BY
                        batch_id DESC

                    LIMIT 1
                    """
                )
                .fetchone()
            )

            if row is None:
                return RedirectResponse(
                    url="/scopes/history",
                    status_code=303,
                )

            batch_id = row[
                "batch_id"
            ]

    finally:
        conn.close()

    return RedirectResponse(
        url=(
            f"/scopes/batches/"
            f"{batch_id}/corrections"
        ),
        status_code=303,
    )


# ============================================================
# AUTO CORRECTION PAGE
# ============================================================

@router.get(
    "/scopes/batches/{batch_id}/corrections",
    response_class=HTMLResponse,
)
def scope_corrections(
    request: Request,
    batch_id: int,
    status_filter: str = "",
    page: int = 1,
    per_page: int = 50,
    result: str = "",
    message: str = "",
):
    per_page = (
        per_page
        if per_page in {
            25,
            50,
            100,
        }
        else
        50
    )

    conn = get_connection()

    try:
        batch = get_batch(
            conn,
            batch_id,
        )

        def count_status(
            status_name,
        ):
            return (
                conn.execute(
                    """
                    SELECT COUNT(*) AS total

                    FROM scope_correction_log

                    WHERE batch_id = ?
                    AND approval_status = ?
                    """,
                    (
                        batch_id,
                        status_name,
                    ),
                )
                .fetchone()[
                    "total"
                ]
            )

        pending_count = (
            count_status(
                "PENDING"
            )
        )

        approved_count = (
            count_status(
                "APPROVED"
            )
        )

        rejected_count = (
            count_status(
                "REJECTED"
            )
        )

        manual_count = (
            count_status(
                "MANUAL"
            )
        )

        where = """
            WHERE correction.batch_id = ?
        """

        params = [
            batch_id,
        ]

        if status_filter in {
            "PENDING",
            "APPROVED",
            "REJECTED",
            "MANUAL",
        }:
            where += """
                AND correction.approval_status = ?
            """

            params.append(
                status_filter
            )

        total = (
            conn.execute(
                f"""
                SELECT COUNT(*) AS total

                FROM scope_correction_log AS correction

                {where}
                """,
                params,
            )
            .fetchone()[
                "total"
            ]
        )

        pager = pagination_meta(
            total,
            page,
            per_page,
        )

        corrections = (
            conn.execute(
                f"""
                SELECT
                    correction.*,

                    staging.raw_no_lpk,
                    staging.raw_product_order_no,
                    staging.raw_product_service

                FROM scope_correction_log AS correction

                JOIN scope_staging AS staging
                    ON staging.staging_id
                    =
                    correction.staging_id

                {where}

                ORDER BY
                    correction.row_no ASC,
                    correction.correction_id ASC

                LIMIT ?
                OFFSET ?
                """,
                params
                +
                [
                    pager[
                        "per_page"
                    ],
                    pager[
                        "offset"
                    ],
                ],
            )
            .fetchall()
        )

        unresolved_blocking = (
            conn.execute(
                """
                SELECT COUNT(*) AS total

                FROM scope_review_issue

                WHERE batch_id = ?
                AND is_blocking = 1
                AND decision IS NULL
                """,
                (
                    batch_id,
                ),
            )
            .fetchone()[
                "total"
            ]
        )

    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="scopes/corrections.html",
        context={
            "batch":
                batch,

            "corrections":
                corrections,

            "pending_count":
                pending_count,

            "approved_count":
                approved_count,

            "rejected_count":
                rejected_count,

            "manual_count":
                manual_count,

            "unresolved_blocking":
                unresolved_blocking,

            "status_filter":
                status_filter,

            "pager":
                pager,

            "result":
                result,

            "message":
                message,
        },
    )


# ============================================================
# APPROVE SINGLE CORRECTION
# ============================================================

@router.post(
    "/scopes/batches/{batch_id}/corrections/{correction_id}/approve"
)
def approve_correction(
    batch_id: int,
    correction_id: int,
):
    conn = get_connection()

    try:
        ensure_batch_editable(
            conn,
            batch_id,
        )

        correction = (
            conn.execute(
                """
                SELECT *

                FROM scope_correction_log

                WHERE correction_id = ?
                AND batch_id = ?
                """,
                (
                    correction_id,
                    batch_id,
                ),
            )
            .fetchone()
        )

        if correction is None:
            raise ValueError(
                "Auto-correction tidak ditemukan."
            )

        conn.execute(
            """
            UPDATE scope_correction_log

            SET
                approval_status = 'APPROVED',
                final_value = corrected_value,
                decision_note =
                    'Admin menyetujui hasil auto-correction.',
                decided_at = CURRENT_TIMESTAMP,
                decided_by = 'Admin',
                updated_at = CURRENT_TIMESTAMP

            WHERE correction_id = ?
            """,
            (
                correction_id,
            ),
        )

        recalculate_scope_batch(
            conn,
            batch_id,
        )

        conn.commit()

    except Exception as exc:
        conn.rollback()

        return redirect_message(
            (
                f"/scopes/batches/"
                f"{batch_id}/corrections"
            ),
            "failed",
            str(
                exc
            ),
        )

    finally:
        conn.close()

    return RedirectResponse(
        url=(
            f"/scopes/batches/"
            f"{batch_id}/corrections"
        ),
        status_code=303,
    )


# ============================================================
# REJECT CORRECTION = PAKAI NILAI ASLI
# ============================================================

@router.post(
    "/scopes/batches/{batch_id}/corrections/{correction_id}/reject"
)
def reject_correction(
    batch_id: int,
    correction_id: int,
):
    conn = get_connection()

    try:
        ensure_batch_editable(
            conn,
            batch_id,
        )

        correction = (
            conn.execute(
                """
                SELECT *

                FROM scope_correction_log

                WHERE correction_id = ?
                AND batch_id = ?
                """,
                (
                    correction_id,
                    batch_id,
                ),
            )
            .fetchone()
        )

        if correction is None:
            raise ValueError(
                "Auto-correction tidak ditemukan."
            )

        conn.execute(
            """
            UPDATE scope_correction_log

            SET
                approval_status = 'REJECTED',
                final_value = original_value,
                decision_note =
                    'Admin memilih mempertahankan nilai asli.',
                decided_at = CURRENT_TIMESTAMP,
                decided_by = 'Admin',
                updated_at = CURRENT_TIMESTAMP

            WHERE correction_id = ?
            """,
            (
                correction_id,
            ),
        )

        recalculate_scope_batch(
            conn,
            batch_id,
        )

        conn.commit()

    except Exception as exc:
        conn.rollback()

        return redirect_message(
            (
                f"/scopes/batches/"
                f"{batch_id}/corrections"
            ),
            "failed",
            str(
                exc
            ),
        )

    finally:
        conn.close()

    return RedirectResponse(
        url=(
            f"/scopes/batches/"
            f"{batch_id}/corrections"
        ),
        status_code=303,
    )


# ============================================================
# APPROVE ALL PENDING CORRECTIONS
# ============================================================

@router.post(
    "/scopes/batches/{batch_id}/corrections/approve-all"
)
def approve_all_corrections(
    batch_id: int,
):
    conn = get_connection()

    try:
        ensure_batch_editable(
            conn,
            batch_id,
        )

        conn.execute(
            """
            UPDATE scope_correction_log

            SET
                approval_status = 'APPROVED',
                final_value = corrected_value,
                decision_note =
                    'Admin menyetujui seluruh auto-correction pending.',
                decided_at = CURRENT_TIMESTAMP,
                decided_by = 'Admin',
                updated_at = CURRENT_TIMESTAMP

            WHERE batch_id = ?
            AND approval_status = 'PENDING'
            """,
            (
                batch_id,
            ),
        )

        recalculate_scope_batch(
            conn,
            batch_id,
        )

        conn.commit()

    except Exception as exc:
        conn.rollback()

        return redirect_message(
            (
                f"/scopes/batches/"
                f"{batch_id}/corrections"
            ),
            "failed",
            str(
                exc
            ),
        )

    finally:
        conn.close()

    return RedirectResponse(
        url=(
            f"/scopes/batches/"
            f"{batch_id}/corrections"
        ),
        status_code=303,
    )


# ============================================================
# REVIEW ISSUE HELPERS
# ============================================================

def refresh_staging_row_status(
    conn,
    staging_id,
):
    unresolved_blocking = (
        conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM scope_review_issue
            WHERE staging_id = ?
            AND is_blocking = 1
            AND decision IS NULL
            """,
            (staging_id,),
        )
        .fetchone()["total"]
    )

    unresolved_issue = (
        conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM scope_review_issue
            WHERE staging_id = ?
            AND decision IS NULL
            """,
            (staging_id,),
        )
        .fetchone()["total"]
    )

    pending_correction = (
        conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM scope_correction_log
            WHERE staging_id = ?
            AND approval_status = 'PENDING'
            """,
            (staging_id,),
        )
        .fetchone()["total"]
    )

    if unresolved_issue > 0:
        row_status = "Need Review"
    elif pending_correction > 0:
        row_status = "Corrected"
    else:
        row_status = "Valid"

    conn.execute(
        """
        UPDATE scope_staging
        SET
            row_status = ?,
            blocking_issue_count = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE staging_id = ?
        """,
        (
            row_status,
            unresolved_blocking,
            staging_id,
        ),
    )


def resolve_issue_after_master_update(
    conn,
    issue,
):
    staging = (
        conn.execute(
            """
            SELECT *
            FROM scope_staging
            WHERE staging_id = ?
            """,
            (issue["staging_id"],),
        )
        .fetchone()
    )

    if staging is None:
        raise ValueError(
            "Data staging tidak ditemukan."
        )

    rule_id = issue["rule_id"] or ""
    field_name = issue["field_name"] or ""

    resolved = False
    resolved_value = None
    error_message = None

    if (
        rule_id == "RL-INSTITUTION-MISSING"
        or field_name == "raw_no_lpk"
    ):
        institutions = load_institutions(conn)

        (
            institution_id,
            institution_row,
            institution_message,
        ) = match_institution(
            institutions,
            staging["raw_no_lpk"],
        )

        if institution_id is not None:
            conn.execute(
                """
                UPDATE scope_staging
                SET
                    institution_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE staging_id = ?
                """,
                (
                    institution_id,
                    staging["staging_id"],
                ),
            )

            resolved = True
            resolved_value = staging["raw_no_lpk"]

        else:
            error_message = (
                institution_message
                or
                "Lembaga masih belum ditemukan di Master Lembaga."
            )

    elif (
        rule_id in {
            "RL-PRODUCT-MATCH",
            "RL-PRODUCT-WARNING",
        }
        or field_name == "raw_product_service"
    ):
        product_paths = load_product_paths(conn)

        (
            product_path_id,
            product_error,
            product_warning,
        ) = match_product_path(
            product_paths,
            staging["raw_scheme"],
            staging["raw_category"],
            staging["raw_subcategory"],
            staging["raw_product_service"],
        )

        if product_path_id is not None:
            conn.execute(
                """
                UPDATE scope_staging
                SET
                    product_path_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE staging_id = ?
                """,
                (
                    product_path_id,
                    staging["staging_id"],
                ),
            )

            resolved = True
            resolved_value = (
                f"product_path_id={product_path_id}"
            )

        else:
            error_message = (
                product_error
                or
                product_warning
                or
                "Master Produk masih belum cocok."
            )

    elif (
        rule_id in {
            "RL-STANDARD-MISSING",
            "RL-STANDARD-TITLE",
        }
        or field_name in {
            "raw_standard_number",
            "raw_standard_title",
        }
    ):
        standards = load_standards(conn)

        (
            standard_id,
            standard_row,
            standard_error,
            standard_warning,
        ) = match_standard(
            standards,
            staging["raw_standard_number"],
            staging["raw_standard_title"],
        )

        if standard_id is not None:
            conn.execute(
                """
                UPDATE scope_staging
                SET
                    standard_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE staging_id = ?
                """,
                (
                    standard_id,
                    staging["staging_id"],
                ),
            )

            resolved = True
            resolved_value = staging["raw_standard_number"]

        else:
            error_message = (
                standard_error
                or
                standard_warning
                or
                "Standar masih belum ditemukan di Master Standar."
            )

    elif (
        rule_id in {
            "RL-CERT-SCHEME-MISSING",
            "RL-CERT-SCHEME-AMBIGUOUS",
        }
        or field_name == "raw_certification_scheme"
    ):
        certification_schemes = (
            load_certification_schemes(conn)
        )

        (
            certification_scheme_id,
            certification_error,
            certification_warning,
        ) = match_certification_scheme(
            certification_schemes,
            staging["raw_certification_scheme"],
        )

        if certification_scheme_id is not None:
            conn.execute(
                """
                UPDATE scope_staging
                SET
                    certification_scheme_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE staging_id = ?
                """,
                (
                    certification_scheme_id,
                    staging["staging_id"],
                ),
            )

            resolved = True
            resolved_value = staging["raw_certification_scheme"]

        else:
            error_message = (
                certification_error
                or
                certification_warning
                or
                (
                    "Skema Sertifikasi masih belum ditemukan "
                    "di Master Skema Sertifikasi."
                )
            )

    else:
        error_message = (
            "Jenis masalah ini belum memiliki pemeriksaan ulang otomatis."
        )

    if not resolved:
        raise ValueError(
            error_message
            or
            "Masalah masih belum terselesaikan."
        )

    conn.execute(
        """
        UPDATE scope_review_issue
        SET
            decision = 'RESOLVED',
            resolved_value = ?,
            decision_note =
                'Masalah selesai setelah Master Data diperbarui '
                'dan dilakukan Cek Ulang.',
            resolved_at = CURRENT_TIMESTAMP,
            resolved_by = 'Admin',
            updated_at = CURRENT_TIMESTAMP
        WHERE issue_id = ?
        """,
        (
            resolved_value,
            issue["issue_id"],
        ),
    )

    refresh_staging_row_status(
        conn,
        staging["staging_id"],
    )


# ============================================================
# REVIEW QUEUE
# ============================================================

@router.get(
    "/scopes/batches/{batch_id}/review",
    response_class=HTMLResponse,
)
def scope_review_queue(
    request: Request,
    batch_id: int,
    type_filter: str = "",
    page: int = 1,
    per_page: int = 50,
    result: str = "",
    message: str = "",
):
    per_page = (
        per_page
        if per_page in {
            25,
            50,
            100,
        }
        else
        50
    )

    conn = get_connection()

    try:
        batch = get_batch(
            conn,
            batch_id,
        )

        where = """
            WHERE issue.batch_id = ?
            AND issue.decision IS NULL
        """

        params = [
            batch_id,
        ]

        if type_filter == "blocking":
            where += """
                AND issue.is_blocking = 1
            """

        elif type_filter == "warning":
            where += """
                AND issue.is_blocking = 0
            """

        total = (
            conn.execute(
                f"""
                SELECT COUNT(*) AS total

                FROM scope_review_issue AS issue

                {where}
                """,
                params,
            )
            .fetchone()[
                "total"
            ]
        )

        pager = pagination_meta(
            total,
            page,
            per_page,
        )

        issues = (
            conn.execute(
                f"""
                SELECT
                    issue.*,

                    staging.raw_no_lpk,
                    staging.raw_product_order_no,
                    staging.raw_scheme,
                    staging.raw_category,
                    staging.raw_subcategory,
                    staging.raw_product_service,
                    staging.raw_standard_number,
                    staging.raw_certification_scheme

                FROM scope_review_issue AS issue

                JOIN scope_staging AS staging
                    ON staging.staging_id
                    =
                    issue.staging_id

                {where}

                ORDER BY
                    issue.is_blocking DESC,
                    issue.row_no ASC,
                    issue.issue_id ASC

                LIMIT ?
                OFFSET ?
                """,
                params
                +
                [
                    pager[
                        "per_page"
                    ],
                    pager[
                        "offset"
                    ],
                ],
            )
            .fetchall()
        )

        blocking_count = (
            conn.execute(
                """
                SELECT COUNT(*) AS total

                FROM scope_review_issue

                WHERE batch_id = ?
                AND is_blocking = 1
                AND decision IS NULL
                """,
                (
                    batch_id,
                ),
            )
            .fetchone()[
                "total"
            ]
        )

        warning_count = (
            conn.execute(
                """
                SELECT COUNT(*) AS total

                FROM scope_review_issue

                WHERE batch_id = ?
                AND is_blocking = 0
                AND decision IS NULL
                """,
                (
                    batch_id,
                ),
            )
            .fetchone()[
                "total"
            ]
        )

    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="scopes/review_queue.html",
        context={
            "batch":
                batch,

            "issues":
                issues,

            "blocking_count":
                blocking_count,

            "warning_count":
                warning_count,

            "type_filter":
                type_filter,

            "pager":
                pager,

            "result":
                result,

            "message":
                message,
        },
    )


# ============================================================
# CEK ULANG SETELAH MASTER DIPERBAIKI
# ============================================================

@router.post(
    "/scopes/batches/{batch_id}/review/{issue_id}/recheck"
)
def recheck_review_issue(
    batch_id: int,
    issue_id: int,
):
    conn = get_connection()

    try:
        ensure_batch_editable(
            conn,
            batch_id,
        )

        issue = (
            conn.execute(
                """
                SELECT *
                FROM scope_review_issue
                WHERE issue_id = ?
                AND batch_id = ?
                AND decision IS NULL
                """,
                (
                    issue_id,
                    batch_id,
                ),
            )
            .fetchone()
        )

        if issue is None:
            raise ValueError(
                "Issue review tidak ditemukan atau sudah diselesaikan."
            )

        resolve_issue_after_master_update(
            conn,
            issue,
        )

        recalculate_scope_batch(
            conn,
            batch_id,
        )

        conn.commit()

    except Exception as exc:
        conn.rollback()

        return redirect_message(
            (
                f"/scopes/batches/"
                f"{batch_id}/review"
            ),
            "failed",
            str(exc),
        )

    finally:
        conn.close()

    return redirect_message(
        (
            f"/scopes/batches/"
            f"{batch_id}/review"
        ),
        "success",
        (
            "Masalah berhasil dicek ulang dan sekarang "
            "sudah cocok dengan Master Data."
        ),
    )


# ============================================================
# REJECT ROW FROM REVIEW
# ============================================================

@router.post(
    "/scopes/batches/{batch_id}/review/{issue_id}/reject-row"
)
def reject_review_row(
    batch_id: int,
    issue_id: int,
):
    conn = get_connection()

    try:
        ensure_batch_editable(
            conn,
            batch_id,
        )

        issue = (
            conn.execute(
                """
                SELECT *

                FROM scope_review_issue

                WHERE issue_id = ?
                AND batch_id = ?
                AND decision IS NULL
                """,
                (
                    issue_id,
                    batch_id,
                ),
            )
            .fetchone()
        )

        if issue is None:
            raise ValueError(
                "Issue review tidak ditemukan."
            )

        staging_id = issue[
            "staging_id"
        ]

        conn.execute(
            """
            UPDATE scope_staging

            SET
                is_excluded = 1,
                row_status = 'Rejected',
                review_status = 'REJECTED',
                review_note =
                    'Row ditolak melalui Review Queue.',
                reviewed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP

            WHERE staging_id = ?
            """,
            (
                staging_id,
            ),
        )

        conn.execute(
            """
            UPDATE scope_review_issue

            SET
                decision = 'REJECT_ROW',
                decision_note =
                    'Admin menolak row dari proses import.',
                resolved_at = CURRENT_TIMESTAMP,
                resolved_by = 'Admin',
                updated_at = CURRENT_TIMESTAMP

            WHERE staging_id = ?
            AND decision IS NULL
            """,
            (
                staging_id,
            ),
        )

        conn.execute(
            """
            UPDATE scope_correction_log

            SET
                approval_status = 'REJECTED',
                final_value = original_value,
                decision_note =
                    'Row ditolak melalui Review Queue.',
                decided_at = CURRENT_TIMESTAMP,
                decided_by = 'Admin',
                updated_at = CURRENT_TIMESTAMP

            WHERE staging_id = ?
            AND approval_status = 'PENDING'
            """,
            (
                staging_id,
            ),
        )

        recalculate_scope_batch(
            conn,
            batch_id,
        )

        conn.commit()

    except Exception as exc:
        conn.rollback()

        return redirect_message(
            (
                f"/scopes/batches/"
                f"{batch_id}/review"
            ),
            "failed",
            str(
                exc
            ),
        )

    finally:
        conn.close()

    return RedirectResponse(
        url=(
            f"/scopes/batches/"
            f"{batch_id}/review"
        ),
        status_code=303,
    )


# ============================================================
# PREVIEW
# ============================================================

@router.get(
    "/scopes/batches/{batch_id}/preview",
    response_class=HTMLResponse,
)
def scope_preview(
    request: Request,
    batch_id: int,
    page: int = 1,
    per_page: int = 50,
    result: str = "",
    message: str = "",
):
    per_page = (
        per_page
        if per_page in {
            25,
            50,
            100,
        }
        else
        50
    )

    conn = get_connection()

    try:
        batch = get_batch(
            conn,
            batch_id,
        )

        pending_corrections = (
            conn.execute(
                """
                SELECT COUNT(*) AS total

                FROM scope_correction_log

                WHERE batch_id = ?
                AND approval_status = 'PENDING'
                """,
                (
                    batch_id,
                ),
            )
            .fetchone()[
                "total"
            ]
        )

        blocking_count = (
            conn.execute(
                """
                SELECT COUNT(*) AS total

                FROM scope_review_issue

                WHERE batch_id = ?
                AND is_blocking = 1
                AND decision IS NULL
                """,
                (
                    batch_id,
                ),
            )
            .fetchone()[
                "total"
            ]
        )

        active_count = (
            conn.execute(
                """
                SELECT COUNT(*) AS total

                FROM scope_staging

                WHERE batch_id = ?
                AND is_excluded = 0
                """,
                (
                    batch_id,
                ),
            )
            .fetchone()[
                "total"
            ]
        )

        rejected_count = (
            conn.execute(
                """
                SELECT COUNT(*) AS total

                FROM scope_staging

                WHERE batch_id = ?
                AND is_excluded = 1
                """,
                (
                    batch_id,
                ),
            )
            .fetchone()[
                "total"
            ]
        )

        pager = pagination_meta(
            active_count,
            page,
            per_page,
        )

        rows = (
            conn.execute(
                """
                SELECT
                    staging.staging_id,
                    staging.source_row,
                    staging.raw_no_lpk,
                    staging.resolved_product_order_no,
                    staging.raw_scheme,
                    staging.raw_category,
                    staging.raw_subcategory,
                    staging.raw_product_service,
                    staging.raw_standard_number,
                    staging.raw_standard_title,
                    staging.raw_certification_scheme,
                    staging.row_status,

                    institution.id_lspro,
                    institution.name_lspro,

                    standard.standard_code,

                    cert.certification_scheme_code

                FROM scope_staging AS staging

                LEFT JOIN institution
                    ON institution.institution_id
                    =
                    staging.institution_id

                LEFT JOIN master_standard AS standard
                    ON standard.standard_id
                    =
                    staging.standard_id

                LEFT JOIN master_certification_scheme AS cert
                    ON cert.certification_scheme_id
                    =
                    staging.certification_scheme_id

                WHERE staging.batch_id = ?
                AND staging.is_excluded = 0

                ORDER BY
                    staging.source_row ASC,
                    staging.staging_id ASC

                LIMIT ?
                OFFSET ?
                """,
                (
                    batch_id,
                    pager[
                        "per_page"
                    ],
                    pager[
                        "offset"
                    ],
                ),
            )
            .fetchall()
        )

        can_commit = (
            batch[
                "status"
            ]
            ==
            "READY_TO_COMMIT"
            and
            pending_corrections
            ==
            0
            and
            blocking_count
            ==
            0
        )

    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="scopes/preview.html",
        context={
            "batch":
                batch,

            "rows":
                rows,

            "pending_corrections":
                pending_corrections,

            "blocking_count":
                blocking_count,

            "active_count":
                active_count,

            "rejected_count":
                rejected_count,

            "can_commit":
                can_commit,

            "pager":
                pager,

            "result":
                result,

            "message":
                message,
        },
    )


# ============================================================
# COMMIT
# ============================================================

@router.post(
    "/scopes/batches/{batch_id}/commit"
)
def commit_scope_batch(
    batch_id: int,
):
    conn = get_connection()

    try:
        batch = ensure_batch_editable(
            conn,
            batch_id,
        )

        pending_corrections = (
            conn.execute(
                """
                SELECT COUNT(*) AS total

                FROM scope_correction_log

                WHERE batch_id = ?
                AND approval_status = 'PENDING'
                """,
                (
                    batch_id,
                ),
            )
            .fetchone()[
                "total"
            ]
        )

        blocking_count = (
            conn.execute(
                """
                SELECT COUNT(*) AS total

                FROM scope_review_issue

                WHERE batch_id = ?
                AND is_blocking = 1
                AND decision IS NULL
                """,
                (
                    batch_id,
                ),
            )
            .fetchone()[
                "total"
            ]
        )

        if pending_corrections > 0:
            raise ValueError(
                (
                    "Masih ada "
                    f"{pending_corrections} auto-correction "
                    "yang belum diputuskan."
                )
            )

        if blocking_count > 0:
            raise ValueError(
                (
                    "Masih ada "
                    f"{blocking_count} blocking issue "
                    "yang belum diselesaikan."
                )
            )

        rows = (
            conn.execute(
                """
                SELECT *

                FROM scope_staging

                WHERE batch_id = ?
                AND is_excluded = 0

                ORDER BY
                    source_row ASC,
                    staging_id ASC
                """,
                (
                    batch_id,
                ),
            )
            .fetchall()
        )

        if not rows:
            raise ValueError(
                "Tidak ada data yang dapat di-commit."
            )

        # ====================================================
        # APPEND / REPLACE
        # ====================================================

        institution_ids = sorted(
            {
                row[
                    "institution_id"
                ]
                for row
                in rows
                if row[
                    "institution_id"
                ]
                is not None
            }
        )

        if (
            batch[
                "import_mode"
            ]
            ==
            "REPLACE"
        ):
            for institution_id in institution_ids:
                old_scope_ids = [
                    item[
                        "scope_id"
                    ]
                    for item
                    in conn.execute(
                        """
                        SELECT scope_id

                        FROM scope

                        WHERE institution_id = ?
                        """,
                        (
                            institution_id,
                        ),
                    )
                    .fetchall()
                ]

                if old_scope_ids:
                    placeholders = ",".join(
                        "?"
                        for _
                        in old_scope_ids
                    )

                    conn.execute(
                        f"""
                        DELETE FROM scope_standard
                        WHERE scope_id IN (
                            {placeholders}
                        )
                        """,
                        old_scope_ids,
                    )

                    conn.execute(
                        """
                        DELETE FROM scope
                        WHERE institution_id = ?
                        """,
                        (
                            institution_id,
                        ),
                    )

        scope_map = {}

        for row in rows:
            required = [
                row[
                    "institution_id"
                ],
                row[
                    "product_path_id"
                ],
                row[
                    "standard_id"
                ],
            ]

            if any(
                value is None
                for value
                in required
            ):
                raise ValueError(
                    (
                        "Masih ada hasil matching kosong pada "
                        f"baris sumber {row['source_row']}."
                    )
                )

            scope_key = (
                row[
                    "institution_id"
                ],
                row[
                    "product_path_id"
                ],
                row[
                    "resolved_product_order_no"
                ],
                row[
                    "certification_scheme_id"
                ],
            )

            scope_id = (
                scope_map.get(
                    scope_key
                )
            )

            if scope_id is None:
                existing = (
                    conn.execute(
                        """
                        SELECT scope_id

                        FROM scope

                        WHERE institution_id = ?
                        AND product_path_id = ?
                        AND COALESCE(
                            product_order_no,
                            ''
                        )
                        =
                        COALESCE(
                            ?,
                            ''
                        )
                        AND (
                            certification_scheme_id = ?
                            OR (
                                certification_scheme_id IS NULL
                                AND ? IS NULL
                            )
                        )

                        LIMIT 1
                        """,
                        (
                            row[
                                "institution_id"
                            ],
                            row[
                                "product_path_id"
                            ],
                            row[
                                "resolved_product_order_no"
                            ],
                            row[
                                "certification_scheme_id"
                            ],
                            row[
                                "certification_scheme_id"
                            ],
                        ),
                    )
                    .fetchone()
                )

                if existing:
                    scope_id = (
                        existing[
                            "scope_id"
                        ]
                    )

                else:
                    cursor = conn.execute(
                        """
                        INSERT INTO scope (
                            institution_id,
                            product_path_id,
                            product_order_no,
                            certification_scheme_id,
                            notes
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
                            row[
                                "institution_id"
                            ],
                            row[
                                "product_path_id"
                            ],
                            row[
                                "resolved_product_order_no"
                            ],
                            row[
                                "certification_scheme_id"
                            ],
                            row[
                                "raw_notes"
                            ],
                        ),
                    )

                    scope_id = (
                        cursor.lastrowid
                    )

                scope_map[
                    scope_key
                ] = scope_id

            conn.execute(
                """
                INSERT OR IGNORE INTO scope_standard (
                    scope_id,
                    standard_id
                )
                VALUES (
                    ?,
                    ?
                )
                """,
                (
                    scope_id,
                    row[
                        "standard_id"
                    ],
                ),
            )

        conn.execute(
            """
            UPDATE scope_upload_batch

            SET
                status = 'COMMITTED',
                committed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP

            WHERE batch_id = ?
            """,
            (
                batch_id,
            ),
        )

        conn.commit()

    except Exception as exc:
        conn.rollback()

        return redirect_message(
            (
                f"/scopes/batches/"
                f"{batch_id}/preview"
            ),
            "failed",
            str(
                exc
            ),
        )

    finally:
        conn.close()

    return redirect_message(
        "/scopes/history",
        "success",
        (
            "Batch berhasil di-commit ke "
            "Data Ruang Lingkup."
        ),
    )


# ============================================================
# FINAL DATA LIST
# ============================================================

@router.get(
    "/scopes",
    response_class=HTMLResponse,
)
def scope_list(
    request: Request,
    search: str = "",
):
    conn = get_connection()

    try:
        query = """
            SELECT
                scope.scope_id,
                scope.product_order_no,

                institution.id_lspro,
                institution.name_lspro,

                scheme.scheme_name,

                category.category_name,
                subcategory.subcategory_name,
                product.product_service_name,

                cert.certification_scheme_name,

                GROUP_CONCAT(
                    standard.standard_number,
                    ' || '
                )
                AS standard_numbers

            FROM scope

            JOIN institution
                ON institution.institution_id
                =
                scope.institution_id

            JOIN master_product_path AS path
                ON path.path_id
                =
                scope.product_path_id

            JOIN master_scheme AS scheme
                ON scheme.scheme_id
                =
                path.scheme_id

            LEFT JOIN master_category AS category
                ON category.category_id
                =
                path.category_id

            LEFT JOIN master_subcategory AS subcategory
                ON subcategory.subcategory_id
                =
                path.subcategory_id

            LEFT JOIN master_product_service AS product
                ON product.product_service_id
                =
                path.product_service_id

            LEFT JOIN master_certification_scheme AS cert
                ON cert.certification_scheme_id
                =
                scope.certification_scheme_id

            LEFT JOIN scope_standard
                ON scope_standard.scope_id
                =
                scope.scope_id

            LEFT JOIN master_standard AS standard
                ON standard.standard_id
                =
                scope_standard.standard_id

            WHERE 1 = 1
        """

        params = []

        if search.strip():
            keyword = (
                f"%{search.strip()}%"
            )

            query += """
                AND (
                    LOWER(
                        institution.id_lspro
                    )
                    LIKE LOWER(?)

                    OR LOWER(
                        COALESCE(
                            institution.name_lspro,
                            ''
                        )
                    )
                    LIKE LOWER(?)

                    OR LOWER(
                        COALESCE(
                            product.product_service_name,
                            ''
                        )
                    )
                    LIKE LOWER(?)

                    OR LOWER(
                        COALESCE(
                            standard.standard_number,
                            ''
                        )
                    )
                    LIKE LOWER(?)
                )
            """

            params.extend(
                [
                    keyword,
                    keyword,
                    keyword,
                    keyword,
                ]
            )

        query += """
            GROUP BY
                scope.scope_id

            ORDER BY
                institution.id_lspro,
                CAST(
                    scope.product_order_no
                    AS INTEGER
                ),
                scope.scope_id
        """

        items = (
            conn.execute(
                query,
                params,
            )
            .fetchall()
        )

    finally:
        conn.close()

    return templates.TemplateResponse(
        request=request,
        name="scopes/list.html",
        context={
            "items":
                items,

            "search":
                search,
        },
    )
