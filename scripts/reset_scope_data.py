from app.database import get_connection


# ============================================================
# RESET DATA RUANG LINGKUP
# ============================================================
# File ini HANYA menghapus data Ruang Lingkup dan workflow-nya.
# Master Lembaga, Master Produk, Master Standar, dan
# Master Skema Sertifikasi TIDAK dihapus.
#
# Karena reset dimaksudkan benar-benar dari awal,
# master_alias juga ikut dikosongkan.
# ============================================================


SCOPE_TABLES_DELETE_ORDER = [
    "scope_version_standard",
    "scope_version_item",
    "scope_version",
    "scope_standard",
    "scope",
    "scope_correction_log",
    "scope_review_issue",
    "scope_staging",
    "scope_upload_batch",
    "master_alias",
]


def table_exists(conn, table_name):
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = ?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def count_rows(conn, table_name):
    return conn.execute(
        f"SELECT COUNT(*) AS total FROM {table_name}"
    ).fetchone()["total"]


def reset_scope_data():
    conn = get_connection()

    try:
        print()
        print("=" * 60)
        print("RESET DATA RUANG LINGKUP")
        print("=" * 60)

        print()
        print("Data sebelum reset:")

        for table_name in SCOPE_TABLES_DELETE_ORDER:
            if table_exists(conn, table_name):
                total = count_rows(
                    conn,
                    table_name,
                )

                print(
                    f"- {table_name}: {total}"
                )

        # Foreign key dinonaktifkan sementara agar semua
        # tabel workflow dapat dibersihkan dengan aman.
        conn.execute(
            "PRAGMA foreign_keys = OFF"
        )

        conn.execute(
            "BEGIN"
        )

        for table_name in SCOPE_TABLES_DELETE_ORDER:
            if table_exists(
                conn,
                table_name,
            ):
                conn.execute(
                    f"DELETE FROM {table_name}"
                )

        # Reset AUTOINCREMENT agar batch_id, staging_id,
        # scope_id, dll. kembali mulai dari 1.
        sequence_tables = [
            table_name
            for table_name
            in SCOPE_TABLES_DELETE_ORDER
            if table_exists(
                conn,
                table_name,
            )
        ]

        for table_name in sequence_tables:
            conn.execute(
                """
                DELETE FROM sqlite_sequence
                WHERE name = ?
                """,
                (
                    table_name,
                ),
            )

        conn.commit()

        conn.execute(
            "PRAGMA foreign_keys = ON"
        )

        print()
        print("Data setelah reset:")

        all_zero = True

        for table_name in SCOPE_TABLES_DELETE_ORDER:
            if table_exists(
                conn,
                table_name,
            ):
                total = count_rows(
                    conn,
                    table_name,
                )

                print(
                    f"- {table_name}: {total}"
                )

                if total != 0:
                    all_zero = False

        print()

        if all_zero:
            print(
                "RESET BERHASIL."
            )
            print(
                "Data Ruang Lingkup, staging, correction, "
                "review, history batch, versioning, dan alias "
                "sudah kosong."
            )
        else:
            print(
                "PERINGATAN: Masih ada tabel yang belum kosong."
            )

        print()
        print(
            "Master Lembaga / Produk / Standar / "
            "Skema Sertifikasi tetap dipertahankan."
        )
        print("=" * 60)

    except Exception:
        conn.rollback()

        try:
            conn.execute(
                "PRAGMA foreign_keys = ON"
            )
        except Exception:
            pass

        raise

    finally:
        conn.close()


if __name__ == "__main__":
    reset_scope_data()
