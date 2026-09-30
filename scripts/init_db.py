from app.database import get_connection


# ============================================================
# CREATE DATABASE
# ============================================================

def init_database():

    conn = get_connection()

    try:

        # ====================================================
        # MASTER LEMBAGA
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS institution (
                institution_id INTEGER PRIMARY KEY AUTOINCREMENT,

                id_lspro TEXT NOT NULL UNIQUE,

                name_lspro TEXT,

                date_start_accreditation TEXT,

                date_end_accreditation TEXT,

                status_accreditation TEXT,

                address TEXT,

                kab_kota TEXT,

                propinsi TEXT,

                kode_pos TEXT,

                telp TEXT,

                fax TEXT,

                email TEXT,

                cp TEXT,

                no_hp_cp TEXT,

                source_status TEXT
                    NOT NULL
                    DEFAULT 'AVAILABLE',

                created_at TEXT
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                updated_at TEXT
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                synced_at TEXT
            )
            """
        )


        # ====================================================
        # RIWAYAT SINKRONISASI
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_history (
                sync_id INTEGER PRIMARY KEY AUTOINCREMENT,

                source_type TEXT NOT NULL,

                sync_status TEXT NOT NULL,

                total_source INTEGER
                    NOT NULL
                    DEFAULT 0,

                inserted_count INTEGER
                    NOT NULL
                    DEFAULT 0,

                updated_count INTEGER
                    NOT NULL
                    DEFAULT 0,

                unchanged_count INTEGER
                    NOT NULL
                    DEFAULT 0,

                missing_count INTEGER
                    NOT NULL
                    DEFAULT 0,

                error_message TEXT,

                started_at TEXT
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                finished_at TEXT
            )
            """
        )


        # ====================================================
        # SYNC LOCK
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_lock (
                lock_name TEXT PRIMARY KEY,

                is_locked INTEGER
                    NOT NULL
                    DEFAULT 0,

                locked_at TEXT,

                locked_by TEXT,

                CHECK (
                    is_locked IN (0, 1)
                )
            )
            """
        )


        # ====================================================
        # DEFAULT SYNC LOCK
        # ====================================================

        conn.execute(
            """
            INSERT OR IGNORE INTO sync_lock (
                lock_name,
                is_locked
            )

            VALUES (
                'MASTER_LEMBAGA',
                0
            )
            """
        )


        # ====================================================
        # AMANDEMEN LEMBAGA
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS institution_amendment (
                amendment_id INTEGER PRIMARY KEY AUTOINCREMENT,

                institution_id INTEGER NOT NULL,

                amendment_no INTEGER NOT NULL,

                amendment_date TEXT,

                description TEXT,

                created_at TEXT
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                updated_at TEXT
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (
                    institution_id
                )
                REFERENCES institution(
                    institution_id
                )
                ON DELETE CASCADE,

                UNIQUE (
                    institution_id,
                    amendment_no
                )
            )
            """
        )


        # ====================================================
        # INDEX MASTER LEMBAGA
        # ====================================================

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_institution_id_lspro

            ON institution(
                id_lspro
            )
            """
        )


        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_institution_status

            ON institution(
                status_accreditation
            )
            """
        )


        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_institution_source_status

            ON institution(
                source_status
            )
            """
        )


        # ====================================================
        # INDEX AMANDEMEN
        # ====================================================

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_amendment_institution

            ON institution_amendment(
                institution_id
            )
            """
        )


        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_amendment_number

            ON institution_amendment(
                amendment_no
            )
            """
        )


        # ====================================================
        # COMMIT
        # ====================================================

        conn.commit()


        print()
        print("========================================")
        print("DATABASE BERHASIL DIPERBARUI")
        print("========================================")
        print()

        print("Tabel tersedia:")
        print("- institution")
        print("- sync_history")
        print("- sync_lock")
        print("- institution_amendment")
        print()


    except Exception:

        conn.rollback()

        raise


    finally:

        conn.close()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    init_database()