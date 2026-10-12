from app.database import get_connection
from app.services.scope_batch_import import recalculate_scope_batch


AUTO_RESOLVE_PATTERNS = [
    "ID Kategori cocok, tetapi nama berbeda",
    "ID Sub Kategori cocok, tetapi nama berbeda",
    "ID Jenis Produk/Proses/Jasa cocok, tetapi nama berbeda",
]


def main():
    conn = get_connection()

    try:
        batch_ids = [
            row["batch_id"]
            for row in conn.execute(
                """
                SELECT DISTINCT batch_id
                FROM scope_review_issue
                WHERE decision IS NULL
                AND rule_id = 'RL-PRODUCT-WARNING'
                """
            ).fetchall()
            if row["batch_id"] is not None
        ]

        resolved_issues = 0
        approved_corrections = 0

        issues = conn.execute(
            """
            SELECT
                issue_id,
                batch_id,
                staging_id,
                reason
            FROM scope_review_issue
            WHERE decision IS NULL
            AND rule_id = 'RL-PRODUCT-WARNING'
            """
        ).fetchall()

        for issue in issues:
            reason = issue["reason"] or ""

            if not any(
                pattern in reason
                for pattern in AUTO_RESOLVE_PATTERNS
            ):
                continue

            conn.execute(
                """
                UPDATE scope_review_issue
                SET
                    decision = 'RESOLVED',
                    resolved_value = 'AUTO_CODE_MATCH',
                    decision_note =
                        'Diselesaikan otomatis karena ID/kode hierarchy '
                        'cocok dengan Master Produk.',
                    resolved_at = CURRENT_TIMESTAMP,
                    resolved_by = 'SYSTEM',
                    updated_at = CURRENT_TIMESTAMP
                WHERE issue_id = ?
                """,
                (issue["issue_id"],),
            )

            resolved_issues += 1

            cursor = conn.execute(
                """
                UPDATE scope_correction_log
                SET
                    approval_status = 'APPROVED',
                    final_value = corrected_value,
                    decision_note =
                        'Disetujui otomatis karena ID/kode hierarchy '
                        'cocok dengan Master Data.',
                    decided_at = CURRENT_TIMESTAMP,
                    decided_by = 'SYSTEM',
                    updated_at = CURRENT_TIMESTAMP
                WHERE staging_id = ?
                AND approval_status = 'PENDING'
                AND correction_type = 'CODE_MATCH'
                """,
                (issue["staging_id"],),
            )

            approved_corrections += max(
                cursor.rowcount,
                0,
            )

            unresolved_issue = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM scope_review_issue
                WHERE staging_id = ?
                AND decision IS NULL
                """,
                (issue["staging_id"],),
            ).fetchone()["total"]

            unresolved_blocking = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM scope_review_issue
                WHERE staging_id = ?
                AND is_blocking = 1
                AND decision IS NULL
                """,
                (issue["staging_id"],),
            ).fetchone()["total"]

            pending_correction = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM scope_correction_log
                WHERE staging_id = ?
                AND approval_status = 'PENDING'
                """,
                (issue["staging_id"],),
            ).fetchone()["total"]

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
                    issue["staging_id"],
                ),
            )

        for batch_id in batch_ids:
            recalculate_scope_batch(
                conn,
                batch_id,
            )

        conn.commit()

        print("=" * 60)
        print("AUTO-CORRECT EXISTING CODE MATCH SELESAI")
        print("=" * 60)
        print(f"Issue resolved       : {resolved_issues}")
        print(f"Correction approved  : {approved_corrections}")
        print(f"Batch recalculated   : {len(batch_ids)}")
        print("=" * 60)

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
