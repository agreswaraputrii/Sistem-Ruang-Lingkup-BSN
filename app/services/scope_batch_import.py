from datetime import datetime

from app.database import get_connection
from app.services import scope_import as matcher


# ============================================================
# POLICY SMART MATCHING
# ============================================================

AUTO_MATCH_THRESHOLD = 97
REVIEW_THRESHOLD = 90


# ============================================================
# BASIC HELPERS
# ============================================================

def _text(value):
    return matcher.compact_text(
        value
    )


def _norm(value):
    return matcher.normalize_for_match(
        value
    )


def _without_code(value):
    return matcher.remove_trailing_code(
        value
    )


def _score(source, target):
    return matcher.fuzzy_score(
        source,
        target,
    )


def _next_batch_code(conn):
    today = datetime.now().strftime(
        "%Y%m%d"
    )

    prefix = (
        f"RL-{today}-"
    )

    row = (
        conn.execute(
            """
            SELECT batch_code

            FROM scope_upload_batch

            WHERE batch_code LIKE ?

            ORDER BY batch_id DESC

            LIMIT 1
            """,
            (
                prefix + "%",
            ),
        )
        .fetchone()
    )

    sequence = 1

    if row:
        try:
            sequence = (
                int(
                    row[
                        "batch_code"
                    ]
                    .split("-")[-1]
                )
                + 1
            )

        except Exception:
            sequence = 1

    return (
        f"{prefix}{sequence:03d}"
    )


def _insert_correction(
    conn,
    batch_id,
    staging_id,
    row_no,
    field_name,
    original_value,
    corrected_value,
    rule_id,
    correction_type,
    correction_note,
    confidence,
    auto_approve=False,
):
    approval_status = (
        "APPROVED"
        if auto_approve
        else "PENDING"
    )

    final_value = (
        corrected_value
        if auto_approve
        else None
    )

    decision_note = (
        (
            "Disetujui otomatis karena ID/kode hierarchy "
            "cocok persis dengan Master Data."
        )
        if auto_approve
        else None
    )

    conn.execute(
        """
        INSERT INTO scope_correction_log (
            batch_id,
            staging_id,
            row_no,

            field_name,

            original_value,
            corrected_value,
            final_value,

            rule_id,
            correction_type,
            correction_note,
            confidence,

            approval_status,
            decision_note,
            decided_at,
            decided_by
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
            CASE
                WHEN ? = 'APPROVED'
                THEN CURRENT_TIMESTAMP
                ELSE NULL
            END,
            CASE
                WHEN ? = 'APPROVED'
                THEN 'SYSTEM'
                ELSE NULL
            END
        )
        """,
        (
            batch_id,
            staging_id,
            row_no,

            field_name,

            original_value,
            corrected_value,
            final_value,

            rule_id,
            correction_type,
            correction_note,
            confidence,

            approval_status,
            decision_note,
            approval_status,
            approval_status,
        ),
    )


def _insert_issue(
    conn,
    batch_id,
    staging_id,
    row_no,
    field_name,
    original_value,
    suggested_value,
    rule_id,
    reason,
    confidence=None,
    is_blocking=True,
):
    conn.execute(
        """
        INSERT INTO scope_review_issue (
            batch_id,
            staging_id,
            row_no,

            field_name,
            original_value,
            suggested_value,

            rule_id,
            reason,
            confidence,
            is_blocking
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
            ?
        )
        """,
        (
            batch_id,
            staging_id,
            row_no,

            field_name,
            original_value,
            suggested_value,

            rule_id,
            reason,
            confidence,
            1
            if is_blocking
            else 0,
        ),
    )


def _path_detail(
    conn,
    path_id,
):
    if path_id is None:
        return None

    return (
        conn.execute(
            """
            SELECT
                path.path_id,

                scheme.scheme_name,

                category.category_name,
                category.category_code,

                subcategory.subcategory_name,
                subcategory.subcategory_code,

                product.product_service_name,
                product.product_service_code

            FROM master_product_path AS path

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

            WHERE path.path_id = ?
            """,
            (
                path_id,
            ),
        )
        .fetchone()
    )


def _register_text_correction(
    conn,
    batch_id,
    staging_id,
    row_no,
    field_name,
    source_value,
    canonical_value,
    rule_prefix,
    code_based=False,
):
    source = _text(
        _without_code(
            source_value
        )
    )

    canonical = _text(
        canonical_value
    )

    if (
        source is None
        or
        canonical is None
    ):
        return False

    if source == canonical:
        return False

    if _norm(source) == _norm(
        canonical
    ):
        _insert_correction(
            conn=conn,
            batch_id=batch_id,
            staging_id=staging_id,
            row_no=row_no,
            field_name=field_name,
            original_value=source_value,
            corrected_value=canonical_value,
            rule_id=(
                f"{rule_prefix}-NORMALIZE"
            ),
            correction_type=(
                "NORMALIZATION"
            ),
            correction_note=(
                "Perbedaan kapitalisasi, spasi, "
                "atau penulisan teknis."
            ),
            confidence=100.0,
        )

        return True

    if code_based:
        _insert_correction(
            conn=conn,
            batch_id=batch_id,
            staging_id=staging_id,
            row_no=row_no,
            field_name=field_name,
            original_value=source_value,
            corrected_value=canonical_value,
            rule_id=(
                f"{rule_prefix}-CODE"
            ),
            correction_type=(
                "CODE_MATCH"
            ),
            correction_note=(
                "ID/kode hierarchy cocok persis dengan master. "
                "Nama dinormalisasi otomatis ke nama Master Data."
            ),
            confidence=100.0,
            auto_approve=True,
        )

        return True

    score = _score(
        source,
        canonical,
    )

    if score >= AUTO_MATCH_THRESHOLD:
        _insert_correction(
            conn=conn,
            batch_id=batch_id,
            staging_id=staging_id,
            row_no=row_no,
            field_name=field_name,
            original_value=source_value,
            corrected_value=canonical_value,
            rule_id=(
                f"{rule_prefix}-FUZZY"
            ),
            correction_type=(
                "FUZZY"
            ),
            correction_note=(
                "Nama sangat mirip dengan master "
                "dan memenuhi threshold auto-correct."
            ),
            confidence=score,
        )

        return True

    return False


# ============================================================
# BATCH RECALCULATION
# ============================================================

def recalculate_scope_batch(
    conn,
    batch_id,
):
    valid_count = (
        conn.execute(
            """
            SELECT COUNT(*) AS total

            FROM scope_staging

            WHERE batch_id = ?
            AND is_excluded = 0
            AND row_status = 'Valid'
            """,
            (
                batch_id,
            ),
        )
        .fetchone()[
            "total"
        ]
    )

    corrected_count = (
        conn.execute(
            """
            SELECT COUNT(*) AS total

            FROM scope_staging

            WHERE batch_id = ?
            AND is_excluded = 0
            AND row_status = 'Corrected'
            """,
            (
                batch_id,
            ),
        )
        .fetchone()[
            "total"
        ]
    )

    review_count = (
        conn.execute(
            """
            SELECT COUNT(*) AS total

            FROM scope_staging

            WHERE batch_id = ?
            AND is_excluded = 0
            AND row_status = 'Need Review'
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

    if pending_corrections > 0:
        status = (
            "WAITING_CORRECTION_APPROVAL"
        )

    elif unresolved_blocking > 0:
        status = (
            "NEED_REVIEW"
        )

    else:
        status = (
            "READY_TO_COMMIT"
        )

    conn.execute(
        """
        UPDATE scope_upload_batch

        SET
            valid_count = ?,
            corrected_count = ?,
            review_count = ?,
            rejected_count = ?,
            status = ?,
            processed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP

        WHERE batch_id = ?
        """,
        (
            valid_count,
            corrected_count,
            review_count,
            rejected_count,
            status,
            batch_id,
        ),
    )

    return {
        "status":
            status,

        "valid_count":
            valid_count,

        "corrected_count":
            corrected_count,

        "review_count":
            review_count,

        "rejected_count":
            rejected_count,

        "pending_corrections":
            pending_corrections,

        "unresolved_blocking":
            unresolved_blocking,
    }


# ============================================================
# MAIN BATCH IMPORT
# ============================================================

def import_scope_batch(
    file_content,
    filename,
    import_mode,
):
    """
    Batch-based import untuk Ruang Lingkup.

    Perbedaan utama dari flow staging lama:
    - Tidak menghapus staging batch sebelumnya.
    - Setiap upload memiliki batch sendiri.
    - Auto-correction dicatat terpisah.
    - Masalah ambigu masuk Review Queue.
    - Hasil upload belum menjadi data aktif.
    """

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
            "Mode import harus APPEND atau REPLACE."
        )

    # Policy baru lebih konservatif.
    matcher.FUZZY_AUTO_MATCH_THRESHOLD = (
        AUTO_MATCH_THRESHOLD
    )

    matcher.FUZZY_SUGGESTION_THRESHOLD = (
        REVIEW_THRESHOLD
    )

    dataframe = matcher.read_scope_file(
        file_content,
        filename,
    )

    if dataframe.empty:
        raise ValueError(
            "File Ruang Lingkup tidak memiliki data."
        )

    conn = get_connection()

    batch_id = None

    try:
        institutions = (
            matcher.load_institutions(
                conn
            )
        )

        product_paths = (
            matcher.load_product_paths(
                conn
            )
        )

        standards = (
            matcher.load_standards(
                conn
            )
        )

        certification_schemes = (
            matcher.load_certification_schemes(
                conn
            )
        )

        if not institutions:
            raise ValueError(
                "Master Lembaga masih kosong."
            )

        if not product_paths:
            raise ValueError(
                "Master Produk masih kosong."
            )

        if not standards:
            raise ValueError(
                "Master Standar masih kosong."
            )

        if not certification_schemes:
            raise ValueError(
                "Master Skema Sertifikasi masih kosong."
            )

        conn.execute(
            "BEGIN"
        )

        batch_code = _next_batch_code(
            conn
        )

        cursor = conn.execute(
            """
            INSERT INTO scope_upload_batch (
                batch_code,
                file_name,
                import_mode,
                status,
                total_rows
            )
            VALUES (
                ?,
                ?,
                ?,
                'PROCESSING',
                ?
            )
            """,
            (
                batch_code,
                filename,
                mode,
                int(
                    len(
                        dataframe
                    )
                ),
            ),
        )

        batch_id = (
            cursor.lastrowid
        )

        contexts = {}

        inserted_count = 0
        skipped_count = 0

        for _, row in dataframe.iterrows():
            source_row = int(
                row[
                    "_source_row"
                ]
            )

            raw_no_lpk = (
                matcher.value_to_text(
                    row[
                        "no_lpk"
                    ]
                )
            )

            raw_product_order_no = (
                matcher.value_to_text(
                    row[
                        "product_order_no"
                    ]
                )
            )

            raw_scheme = (
                matcher.value_to_text(
                    row[
                        "scheme"
                    ]
                )
            )

            raw_category = (
                matcher.value_to_text(
                    row[
                        "category"
                    ]
                )
            )

            raw_subcategory = (
                matcher.value_to_text(
                    row[
                        "subcategory"
                    ]
                )
            )

            raw_product_service = (
                matcher.value_to_text(
                    row[
                        "product_service"
                    ]
                )
            )

            raw_standard_number = (
                matcher.value_to_text(
                    row[
                        "standard_number"
                    ]
                )
            )

            raw_standard_title = (
                matcher.value_to_text(
                    row[
                        "standard_title"
                    ]
                )
            )

            raw_certification_scheme = (
                matcher.value_to_text(
                    row[
                        "certification_scheme"
                    ]
                )
            )

            raw_notes = (
                matcher.value_to_text(
                    row[
                        "notes"
                    ]
                )
            )

            context_key = (
                matcher.make_context_key(
                    raw_no_lpk
                )
            )

            if matcher.is_structural_row(
                row
            ):
                skipped_count += 1

                if context_key:
                    contexts.pop(
                        context_key,
                        None,
                    )

                continue

            previous_context = (
                contexts.get(
                    context_key
                )
                if context_key
                else None
            )

            (
                resolved,
                continuation,
            ) = matcher.resolve_row_context(
                row,
                previous_context,
            )

            resolved_product_order_no = (
                matcher.compact_text(
                    resolved[
                        "product_order_no"
                    ]
                )
            )

            errors = []
            warnings = []

            # ------------------------------------------------
            # LEMBAGA
            # ------------------------------------------------

            (
                institution_id,
                institution_row,
                institution_message,
            ) = matcher.match_institution(
                institutions,
                raw_no_lpk,
            )

            if institution_id is None:
                errors.append(
                    (
                        "raw_no_lpk",
                        raw_no_lpk,
                        "RL-INSTITUTION-MISSING",
                        institution_message,
                    )
                )

            elif institution_message:
                warnings.append(
                    (
                        "raw_no_lpk",
                        raw_no_lpk,
                        "RL-INSTITUTION-STATUS",
                        institution_message,
                    )
                )

            # ------------------------------------------------
            # NOMOR URUT PRODUK
            # ------------------------------------------------

            if resolved_product_order_no is None:
                errors.append(
                    (
                        "raw_product_order_no",
                        raw_product_order_no,
                        "RL-PRODUCT-ORDER-REQUIRED",
                        (
                            "No. Urut Produk kosong dan tidak "
                            "dapat diwarisi dari baris sebelumnya."
                        ),
                    )
                )

            # ------------------------------------------------
            # MASTER PRODUK
            # ------------------------------------------------

            (
                product_path_id,
                product_error,
                product_warning,
            ) = matcher.match_product_path(
                product_paths,
                resolved[
                    "scheme"
                ],
                resolved[
                    "category"
                ],
                resolved[
                    "subcategory"
                ],
                resolved[
                    "product_service"
                ],
            )

            if product_error:
                errors.append(
                    (
                        "raw_product_service",
                        raw_product_service,
                        "RL-PRODUCT-MATCH",
                        product_error,
                    )
                )

            if product_warning:
                warnings.append(
                    (
                        "raw_product_service",
                        raw_product_service,
                        "RL-PRODUCT-WARNING",
                        product_warning,
                    )
                )

            # ------------------------------------------------
            # MASTER STANDAR
            # ------------------------------------------------

            (
                standard_id,
                standard_row,
                standard_error,
                standard_warning,
            ) = matcher.match_standard(
                standards,
                raw_standard_number,
                raw_standard_title,
            )

            if standard_error:
                errors.append(
                    (
                        "raw_standard_number",
                        raw_standard_number,
                        "RL-STANDARD-MISSING",
                        standard_error,
                    )
                )

            if standard_warning:
                warnings.append(
                    (
                        "raw_standard_title",
                        raw_standard_title,
                        "RL-STANDARD-TITLE",
                        standard_warning,
                    )
                )

            # ------------------------------------------------
            # MASTER SKEMA SERTIFIKASI
            # ------------------------------------------------

            (
                certification_scheme_id,
                certification_error,
                certification_warning,
            ) = matcher.match_certification_scheme(
                certification_schemes,
                resolved[
                    "certification_scheme"
                ],
            )

            if certification_error:
                errors.append(
                    (
                        "raw_certification_scheme",
                        raw_certification_scheme,
                        "RL-CERT-SCHEME-MISSING",
                        certification_error,
                    )
                )

            if certification_warning:
                warnings.append(
                    (
                        "raw_certification_scheme",
                        raw_certification_scheme,
                        "RL-CERT-SCHEME-AMBIGUOUS",
                        certification_warning,
                    )
                )

            validation_status = (
                "ERROR"
                if errors
                else
                (
                    "WARNING"
                    if warnings
                    else
                    "VALID"
                )
            )

            messages = []

            if errors:
                messages.append(
                    "ERROR: "
                    +
                    " | ".join(
                        item[3]
                        for item
                        in errors
                    )
                )

            if warnings:
                messages.append(
                    "WARNING: "
                    +
                    " | ".join(
                        item[3]
                        for item
                        in warnings
                    )
                )

            if (
                continuation
                and
                not messages
            ):
                messages.append(
                    (
                        "Baris standar lanjutan. "
                        "Konteks produk diwarisi dari "
                        "baris sebelumnya."
                    )
                )

            validation_message = (
                " || ".join(
                    messages
                )
                if messages
                else
                "Data cocok dengan seluruh master."
            )

            cursor = conn.execute(
                """
                INSERT INTO scope_staging (
                    batch_id,
                    source_row,

                    raw_no_lpk,
                    raw_product_order_no,
                    resolved_product_order_no,

                    raw_scheme,
                    raw_category,
                    raw_subcategory,
                    raw_product_service,

                    raw_standard_number,
                    raw_standard_title,

                    raw_certification_scheme,
                    raw_notes,

                    institution_id,
                    product_path_id,
                    standard_id,
                    certification_scheme_id,

                    validation_status,
                    validation_message,

                    review_status,
                    review_note,

                    row_status,
                    is_excluded,
                    blocking_issue_count,
                    processed_at,

                    reviewed_at
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
                    ?,
                    ?,
                    ?,

                    ?,
                    ?,

                    'PENDING',
                    NULL,

                    'Valid',
                    0,
                    0,
                    CURRENT_TIMESTAMP,

                    NULL
                )
                """,
                (
                    batch_id,
                    source_row,

                    raw_no_lpk,
                    raw_product_order_no,
                    resolved_product_order_no,

                    raw_scheme,
                    raw_category,
                    raw_subcategory,
                    raw_product_service,

                    raw_standard_number,
                    raw_standard_title,

                    raw_certification_scheme,
                    raw_notes,

                    institution_id,
                    product_path_id,
                    standard_id,
                    certification_scheme_id,

                    validation_status,
                    validation_message,
                ),
            )

            staging_id = (
                cursor.lastrowid
            )

            inserted_count += 1

            # ------------------------------------------------
            # BLOCKING ISSUES
            # ------------------------------------------------

            for (
                field_name,
                original_value,
                rule_id,
                reason,
            ) in errors:
                _insert_issue(
                    conn=conn,
                    batch_id=batch_id,
                    staging_id=staging_id,
                    row_no=source_row,
                    field_name=field_name,
                    original_value=original_value,
                    suggested_value=None,
                    rule_id=rule_id,
                    reason=reason,
                    confidence=None,
                    is_blocking=True,
                )

            # ------------------------------------------------
            # WARNING ISSUES
            # ------------------------------------------------

            for (
                field_name,
                original_value,
                rule_id,
                reason,
            ) in warnings:
                # Warning tertentu aman ditangani otomatis.
                #
                # Jika ID/kode hierarchy sudah cocok persis dengan
                # Master Produk, perbedaan penulisan nama bukan
                # masalah yang memerlukan review manual.
                #
                # Contoh:
                # "Peralatan kesehatan non elektromedik"
                # vs
                # "Peralatan Kesehatan Non-Elektromedik"
                #
                # ID tetap menjadi sumber kebenaran.
                auto_correct_product_warning = (
                    rule_id
                    ==
                    "RL-PRODUCT-WARNING"
                    and
                    (
                        "ID Kategori cocok, tetapi nama berbeda"
                        in reason

                        or

                        "ID Sub Kategori cocok, tetapi nama berbeda"
                        in reason

                        or

                        "ID Jenis Produk/Proses/Jasa cocok, tetapi nama berbeda"
                        in reason

                        or

                        "dicocokkan dengan"
                        in reason
                    )
                )

                if auto_correct_product_warning:
                    continue

                _insert_issue(
                    conn=conn,
                    batch_id=batch_id,
                    staging_id=staging_id,
                    row_no=source_row,
                    field_name=field_name,
                    original_value=original_value,
                    suggested_value=None,
                    rule_id=rule_id,
                    reason=reason,
                    confidence=None,
                    is_blocking=(
                        rule_id
                        ==
                        "RL-CERT-SCHEME-AMBIGUOUS"
                    ),
                )

            # ------------------------------------------------
            # CORRECTION LOG DARI MASTER PRODUK
            # ------------------------------------------------

            correction_count = 0

            path_detail = _path_detail(
                conn,
                product_path_id,
            )

            if path_detail:
                correction_count += (
                    1
                    if _register_text_correction(
                        conn=conn,
                        batch_id=batch_id,
                        staging_id=staging_id,
                        row_no=source_row,
                        field_name="raw_scheme",
                        source_value=resolved[
                            "scheme"
                        ],
                        canonical_value=path_detail[
                            "scheme_name"
                        ],
                        rule_prefix="RL-SCHEME",
                        code_based=False,
                    )
                    else 0
                )

                correction_count += (
                    1
                    if _register_text_correction(
                        conn=conn,
                        batch_id=batch_id,
                        staging_id=staging_id,
                        row_no=source_row,
                        field_name="raw_category",
                        source_value=resolved[
                            "category"
                        ],
                        canonical_value=path_detail[
                            "category_name"
                        ],
                        rule_prefix="RL-CATEGORY",
                        code_based=True,
                    )
                    else 0
                )

                correction_count += (
                    1
                    if _register_text_correction(
                        conn=conn,
                        batch_id=batch_id,
                        staging_id=staging_id,
                        row_no=source_row,
                        field_name="raw_subcategory",
                        source_value=resolved[
                            "subcategory"
                        ],
                        canonical_value=path_detail[
                            "subcategory_name"
                        ],
                        rule_prefix="RL-SUBCATEGORY",
                        code_based=True,
                    )
                    else 0
                )

                correction_count += (
                    1
                    if _register_text_correction(
                        conn=conn,
                        batch_id=batch_id,
                        staging_id=staging_id,
                        row_no=source_row,
                        field_name="raw_product_service",
                        source_value=resolved[
                            "product_service"
                        ],
                        canonical_value=path_detail[
                            "product_service_name"
                        ],
                        rule_prefix="RL-PRODUCT",
                        code_based=(
                            matcher.extract_local_code(
                                resolved[
                                    "product_service"
                                ]
                            )
                            is not None
                        ),
                    )
                    else 0
                )

            # ------------------------------------------------
            # STANDARD TITLE CANONICALIZATION
            # ------------------------------------------------

            if (
                standard_row
                and
                _text(
                    standard_row[
                        "standard_title"
                    ]
                )
            ):
                correction_count += (
                    1
                    if _register_text_correction(
                        conn=conn,
                        batch_id=batch_id,
                        staging_id=staging_id,
                        row_no=source_row,
                        field_name="raw_standard_title",
                        source_value=raw_standard_title,
                        canonical_value=standard_row[
                            "standard_title"
                        ],
                        rule_prefix="RL-STANDARD-TITLE",
                        code_based=True,
                    )
                    else 0
                )

            blocking_count = (
                conn.execute(
                    """
                    SELECT COUNT(*) AS total

                    FROM scope_review_issue

                    WHERE staging_id = ?
                    AND is_blocking = 1
                    AND decision IS NULL
                    """,
                    (
                        staging_id,
                    ),
                )
                .fetchone()[
                    "total"
                ]
            )

            issue_count = (
                conn.execute(
                    """
                    SELECT COUNT(*) AS total

                    FROM scope_review_issue

                    WHERE staging_id = ?
                    AND decision IS NULL
                    """,
                    (
                        staging_id,
                    ),
                )
                .fetchone()[
                    "total"
                ]
            )

            if blocking_count > 0:
                row_status = (
                    "Need Review"
                )

            elif issue_count > 0:
                row_status = (
                    "Need Review"
                )

            elif correction_count > 0:
                row_status = (
                    "Corrected"
                )

            else:
                row_status = (
                    "Valid"
                )

            conn.execute(
                """
                UPDATE scope_staging

                SET
                    row_status = ?,
                    blocking_issue_count = ?

                WHERE staging_id = ?
                """,
                (
                    row_status,
                    blocking_count,
                    staging_id,
                ),
            )

            # ------------------------------------------------
            # UPDATE CONTEXT
            # ------------------------------------------------

            if context_key:
                if (
                    not continuation
                    and
                    (
                        matcher.compact_text(
                            resolved[
                                "product_service"
                            ]
                        )
                        is not None
                        or
                        matcher.compact_text(
                            resolved[
                                "scheme"
                            ]
                        )
                        is not None
                    )
                ):
                    contexts[
                        context_key
                    ] = resolved

                elif (
                    continuation
                    and
                    previous_context
                ):
                    contexts[
                        context_key
                    ] = previous_context

        conn.execute(
            """
            UPDATE scope_upload_batch

            SET
                total_rows = ?,
                notes = ?,
                updated_at = CURRENT_TIMESTAMP

            WHERE batch_id = ?
            """,
            (
                inserted_count,
                (
                    f"{skipped_count} baris struktur/"
                    "separator dilewati."
                ),
                batch_id,
            ),
        )

        summary = recalculate_scope_batch(
            conn,
            batch_id,
        )

        conn.commit()

        return {
            "batch_id":
                batch_id,

            "batch_code":
                batch_code,

            "file_name":
                filename,

            "import_mode":
                mode,

            "inserted_count":
                inserted_count,

            "skipped_count":
                skipped_count,

            **summary,
        }

    except Exception as exc:
        conn.rollback()

        if batch_id is not None:
            try:
                conn.execute(
                    """
                    UPDATE scope_upload_batch

                    SET
                        status = 'FAILED',
                        notes = ?,
                        updated_at = CURRENT_TIMESTAMP

                    WHERE batch_id = ?
                    """,
                    (
                        str(
                            exc
                        ),
                        batch_id,
                    ),
                )

                conn.commit()

            except Exception:
                conn.rollback()

        raise

    finally:
        conn.close()
