from app.database import get_connection


# ============================================================
# HELPER
# ============================================================

def table_exists(conn, table_name):
    result = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = ?
        """,
        (table_name,),
    ).fetchone()

    return result is not None


def get_table_columns(conn, table_name):
    rows = conn.execute(
        f"""
        PRAGMA table_info({table_name})
        """
    ).fetchall()

    return {
        row["name"]: row
        for row in rows
    }



def add_column_if_missing(
    conn,
    table_name,
    column_name,
    column_definition,
):
    """
    Menambahkan kolom baru secara aman ke tabel existing.
    SQLite tidak mendukung ADD COLUMN IF NOT EXISTS,
    jadi pengecekan dilakukan melalui PRAGMA table_info.
    """
    if not table_exists(
        conn,
        table_name,
    ):
        return

    columns = get_table_columns(
        conn,
        table_name,
    )

    if column_name in columns:
        return

    print(
        f"Menambahkan kolom {column_name} "
        f"ke {table_name}..."
    )

    conn.execute(
        f"""
        ALTER TABLE {table_name}
        ADD COLUMN {column_name} {column_definition}
        """
    )


def get_unique_backup_table_name(conn, base_name):
    """
    Membuat nama tabel backup yang tidak bentrok.

    Contoh:
    scope_legacy_backup
    scope_legacy_backup_2
    scope_legacy_backup_3
    """
    if not table_exists(conn, base_name):
        return base_name

    counter = 2

    while table_exists(
        conn,
        f"{base_name}_{counter}",
    ):
        counter += 1

    return f"{base_name}_{counter}"


# ============================================================
# MIGRATION MASTER SUBCATEGORY
# ============================================================

def migrate_master_subcategory(conn):
    if not table_exists(
        conn,
        "master_subcategory",
    ):
        return

    columns = get_table_columns(
        conn,
        "master_subcategory",
    )

    # Struktur baru sudah tersedia.
    if "scheme_id" in columns:
        return

    print(
        "Migrasi master_subcategory..."
    )

    conn.execute(
        """
        ALTER TABLE master_subcategory
        RENAME TO master_subcategory_old
        """
    )

    conn.execute(
        """
        CREATE TABLE master_subcategory (
            subcategory_id INTEGER PRIMARY KEY AUTOINCREMENT,
            scheme_id INTEGER,
            category_id INTEGER,
            subcategory_code TEXT,
            subcategory_name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (scheme_id)
                REFERENCES master_scheme(scheme_id)
                ON DELETE SET NULL,

            FOREIGN KEY (category_id)
                REFERENCES master_category(category_id)
                ON DELETE SET NULL
        )
        """
    )

    conn.execute(
        """
        INSERT INTO master_subcategory (
            subcategory_id,
            scheme_id,
            category_id,
            subcategory_code,
            subcategory_name,
            created_at,
            updated_at
        )
        SELECT
            old.subcategory_id,
            category.scheme_id,
            old.category_id,
            old.subcategory_code,
            old.subcategory_name,
            old.created_at,
            old.updated_at
        FROM master_subcategory_old AS old
        LEFT JOIN master_category AS category
            ON category.category_id = old.category_id
        """
    )

    conn.execute(
        """
        DROP TABLE master_subcategory_old
        """
    )


# ============================================================
# MIGRATION MASTER PRODUCT / SERVICE
# ============================================================

def migrate_master_product_service(conn):
    if not table_exists(
        conn,
        "master_product_service",
    ):
        return

    columns = get_table_columns(
        conn,
        "master_product_service",
    )

    # Struktur baru sudah tersedia.
    if (
        "scheme_id" in columns
        and
        "category_id" in columns
    ):
        return

    print(
        "Migrasi master_product_service..."
    )

    conn.execute(
        """
        ALTER TABLE master_product_service
        RENAME TO master_product_service_old
        """
    )

    conn.execute(
        """
        CREATE TABLE master_product_service (
            product_service_id INTEGER PRIMARY KEY AUTOINCREMENT,
            scheme_id INTEGER,
            category_id INTEGER,
            subcategory_id INTEGER,
            product_service_code TEXT,
            product_service_name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (scheme_id)
                REFERENCES master_scheme(scheme_id)
                ON DELETE SET NULL,

            FOREIGN KEY (category_id)
                REFERENCES master_category(category_id)
                ON DELETE SET NULL,

            FOREIGN KEY (subcategory_id)
                REFERENCES master_subcategory(subcategory_id)
                ON DELETE SET NULL
        )
        """
    )

    conn.execute(
        """
        INSERT INTO master_product_service (
            product_service_id,
            scheme_id,
            category_id,
            subcategory_id,
            product_service_code,
            product_service_name,
            created_at,
            updated_at
        )
        SELECT
            old.product_service_id,
            subcategory.scheme_id,
            subcategory.category_id,
            old.subcategory_id,
            old.product_service_code,
            old.product_service_name,
            old.created_at,
            old.updated_at
        FROM master_product_service_old AS old
        LEFT JOIN master_subcategory AS subcategory
            ON subcategory.subcategory_id = old.subcategory_id
        """
    )

    conn.execute(
        """
        DROP TABLE master_product_service_old
        """
    )


# ============================================================
# MIGRATION MASTER STANDARD
# ============================================================

def migrate_master_standard(conn):
    """
    Aturan baru:
    - standard_code unik
    - standard_number unik
    - standard_title boleh kosong, tetapi tidak NULL

    Untuk database existing, uniqueness nomor dijaga dengan
    UNIQUE INDEX ux_master_standard_number.
    """

    if not table_exists(
        conn,
        "master_standard",
    ):
        return

    # Ubah NULL title (jika pernah ada) menjadi string kosong.
    conn.execute(
        """
        UPDATE master_standard
        SET standard_title = ''
        WHERE standard_title IS NULL
        """
    )

    duplicates = conn.execute(
        """
        SELECT
            standard_number,
            COUNT(*) AS total
        FROM master_standard
        GROUP BY standard_number
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    ).fetchone()

    if duplicates:
        raise ValueError(
            "Master Standar masih memiliki Nomor Acuan Standar "
            f"duplikat: '{duplicates['standard_number']}'. "
            "Hapus/perbaiki duplikat sebelum menjalankan init_db."
        )

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        ux_master_standard_number
        ON master_standard(standard_number)
        """
    )


# ============================================================
# MIGRATION SCOPE LAMA
# ============================================================

def migrate_scope(conn):
    """
    Versi lama scope masih menyimpan:
    scheme/category/subcategory/product_service/standard
    sebagai teks.

    Karena struktur final memakai foreign key ke master,
    data lama tidak dipaksakan masuk agar tidak salah mapping.
    Jika struktur lama ditemukan, tabel lama disimpan sebagai
    backup dan tabel scope final dibuat ulang.
    """

    if not table_exists(
        conn,
        "scope",
    ):
        return

    columns = get_table_columns(
        conn,
        "scope",
    )

    # Struktur final sudah tersedia.
    if (
        "product_path_id" in columns
        and
        "certification_scheme_id" in columns
        and
        "scheme" not in columns
    ):
        return

    backup_name = get_unique_backup_table_name(
        conn,
        "scope_legacy_backup",
    )

    print(
        "Migrasi scope lama..."
    )
    print(
        f"- Data scope lama disimpan di tabel: {backup_name}"
    )

    conn.execute(
        f"""
        ALTER TABLE scope
        RENAME TO {backup_name}
        """
    )


# ============================================================
# MIGRATION SCOPE STAGING LAMA
# ============================================================

def migrate_scope_staging(conn):
    """
    Struktur staging lama memakai:
    - CORRECT / WARNING / BLOCKED
    - is_approved / is_rejected
    - beberapa kolom raw belum dipisahkan.

    Agar data mentah tidak hilang, data staging lama disimpan
    sebagai backup. Staging final kemudian dibuat baru.
    """

    if not table_exists(
        conn,
        "scope_staging",
    ):
        return

    columns = get_table_columns(
        conn,
        "scope_staging",
    )

    final_columns = {
        "raw_product_order_no",
        "raw_scheme",
        "raw_category",
        "raw_subcategory",
        "raw_product_service",
        "raw_standard_number",
        "raw_standard_title",
        "raw_certification_scheme",
        "raw_notes",
        "product_path_id",
        "standard_id",
        "certification_scheme_id",
        "validation_status",
        "review_status",
    }

    # Struktur final sudah ada, tetapi versi awal belum
    # memiliki resolved_product_order_no.
    # Tambahkan kolom tanpa membuat backup ulang.
    if final_columns.issubset(
        set(columns.keys())
    ):
        if (
            "resolved_product_order_no"
            not in columns
        ):
            print(
                "Menambahkan resolved_product_order_no "
                "ke scope_staging..."
            )

            conn.execute(
                """
                ALTER TABLE scope_staging
                ADD COLUMN resolved_product_order_no TEXT
                """
            )

        return

    backup_name = get_unique_backup_table_name(
        conn,
        "scope_staging_legacy_backup",
    )

    print(
        "Migrasi scope_staging lama..."
    )
    print(
        f"- Data staging lama disimpan di tabel: {backup_name}"
    )

    conn.execute(
        f"""
        ALTER TABLE scope_staging
        RENAME TO {backup_name}
        """
    )


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
                source_status TEXT NOT NULL DEFAULT 'AVAILABLE',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
                total_source INTEGER NOT NULL DEFAULT 0,
                inserted_count INTEGER NOT NULL DEFAULT 0,
                updated_count INTEGER NOT NULL DEFAULT 0,
                unchanged_count INTEGER NOT NULL DEFAULT 0,
                missing_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
                is_locked INTEGER NOT NULL DEFAULT 0,
                locked_at TEXT,
                locked_by TEXT,

                CHECK (
                    is_locked IN (0, 1)
                )
            )
            """
        )

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
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (institution_id)
                    REFERENCES institution(institution_id)
                    ON DELETE CASCADE,

                UNIQUE (
                    institution_id,
                    amendment_no
                )
            )
            """
        )

        # ====================================================
        # MASTER SKEMA / JENIS AKREDITASI
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS master_scheme (
                scheme_id INTEGER PRIMARY KEY AUTOINCREMENT,
                scheme_code TEXT,
                scheme_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                UNIQUE (
                    scheme_code,
                    scheme_name
                )
            )
            """
        )

        # ====================================================
        # MASTER KATEGORI
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS master_category (
                category_id INTEGER PRIMARY KEY AUTOINCREMENT,
                scheme_id INTEGER,
                category_code TEXT,
                category_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (scheme_id)
                    REFERENCES master_scheme(scheme_id)
                    ON DELETE SET NULL
            )
            """
        )

        # ====================================================
        # MIGRATION SUBCATEGORY LAMA
        # ====================================================

        migrate_master_subcategory(
            conn
        )

        # ====================================================
        # MASTER SUB KATEGORI
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS master_subcategory (
                subcategory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                scheme_id INTEGER,
                category_id INTEGER,
                subcategory_code TEXT,
                subcategory_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (scheme_id)
                    REFERENCES master_scheme(scheme_id)
                    ON DELETE SET NULL,

                FOREIGN KEY (category_id)
                    REFERENCES master_category(category_id)
                    ON DELETE SET NULL
            )
            """
        )

        # ====================================================
        # MIGRATION PRODUCT SERVICE LAMA
        # ====================================================

        migrate_master_product_service(
            conn
        )

        # ====================================================
        # MASTER PRODUK / PROSES / JASA
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS master_product_service (
                product_service_id INTEGER PRIMARY KEY AUTOINCREMENT,
                scheme_id INTEGER,
                category_id INTEGER,
                subcategory_id INTEGER,
                product_service_code TEXT,
                product_service_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (scheme_id)
                    REFERENCES master_scheme(scheme_id)
                    ON DELETE SET NULL,

                FOREIGN KEY (category_id)
                    REFERENCES master_category(category_id)
                    ON DELETE SET NULL,

                FOREIGN KEY (subcategory_id)
                    REFERENCES master_subcategory(subcategory_id)
                    ON DELETE SET NULL
            )
            """
        )

        # ====================================================
        # MASTER PRODUCT PATH
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS master_product_path (
                path_id INTEGER PRIMARY KEY AUTOINCREMENT,
                scheme_id INTEGER NOT NULL,
                category_id INTEGER,
                subcategory_id INTEGER,
                product_service_id INTEGER,

                category_status TEXT NOT NULL DEFAULT 'MISSING',
                subcategory_status TEXT NOT NULL DEFAULT 'MISSING',
                product_service_status TEXT NOT NULL DEFAULT 'MISSING',

                source_row INTEGER,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (scheme_id)
                    REFERENCES master_scheme(scheme_id)
                    ON DELETE CASCADE,

                FOREIGN KEY (category_id)
                    REFERENCES master_category(category_id)
                    ON DELETE SET NULL,

                FOREIGN KEY (subcategory_id)
                    REFERENCES master_subcategory(subcategory_id)
                    ON DELETE SET NULL,

                FOREIGN KEY (product_service_id)
                    REFERENCES master_product_service(product_service_id)
                    ON DELETE SET NULL,

                CHECK (
                    category_status IN (
                        'VALUE',
                        'NOT_APPLICABLE',
                        'MISSING'
                    )
                ),

                CHECK (
                    subcategory_status IN (
                        'VALUE',
                        'NOT_APPLICABLE',
                        'MISSING'
                    )
                ),

                CHECK (
                    product_service_status IN (
                        'VALUE',
                        'NOT_APPLICABLE',
                        'MISSING'
                    )
                )
            )
            """
        )

        # ====================================================
        # MASTER SKEMA SERTIFIKASI
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS master_certification_scheme (
                certification_scheme_id INTEGER PRIMARY KEY AUTOINCREMENT,
                certification_scheme_code TEXT UNIQUE,
                certification_scheme_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # ====================================================
        # MASTER STANDAR
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS master_standard (
                standard_id INTEGER PRIMARY KEY AUTOINCREMENT,
                standard_code TEXT UNIQUE,
                standard_number TEXT NOT NULL UNIQUE,
                standard_title TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        migrate_master_standard(
            conn
        )

        # ====================================================
        # MIGRATION RUANG LINGKUP SEMENTARA
        # ====================================================

        migrate_scope(
            conn
        )

        migrate_scope_staging(
            conn
        )

        # ====================================================
        # RUANG LINGKUP FINAL
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scope (
                scope_id INTEGER PRIMARY KEY AUTOINCREMENT,

                institution_id INTEGER NOT NULL,
                product_path_id INTEGER NOT NULL,
                product_order_no TEXT,
                certification_scheme_id INTEGER,
                notes TEXT,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (institution_id)
                    REFERENCES institution(institution_id)
                    ON DELETE RESTRICT,

                FOREIGN KEY (product_path_id)
                    REFERENCES master_product_path(path_id)
                    ON DELETE RESTRICT,

                FOREIGN KEY (certification_scheme_id)
                    REFERENCES master_certification_scheme(
                        certification_scheme_id
                    )
                    ON DELETE SET NULL
            )
            """
        )

        # ====================================================
        # RELASI RUANG LINGKUP - STANDAR
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scope_standard (
                scope_standard_id INTEGER PRIMARY KEY AUTOINCREMENT,

                scope_id INTEGER NOT NULL,
                standard_id INTEGER NOT NULL,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (scope_id)
                    REFERENCES scope(scope_id)
                    ON DELETE CASCADE,

                FOREIGN KEY (standard_id)
                    REFERENCES master_standard(standard_id)
                    ON DELETE RESTRICT,

                UNIQUE (
                    scope_id,
                    standard_id
                )
            )
            """
        )

        # ====================================================
        # STAGING RUANG LINGKUP
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scope_staging (
                staging_id INTEGER PRIMARY KEY AUTOINCREMENT,

                source_row INTEGER,

                -- RAW DARI FILE
                raw_no_lpk TEXT,
                raw_product_order_no TEXT,

                -- Nilai No. Urut Produk yang dipakai saat commit.
                -- Untuk baris lanjutan standar, nilainya dapat
                -- diwarisi dari baris produk sebelumnya.
                resolved_product_order_no TEXT,

                raw_scheme TEXT,
                raw_category TEXT,
                raw_subcategory TEXT,
                raw_product_service TEXT,
                raw_standard_number TEXT,
                raw_standard_title TEXT,
                raw_certification_scheme TEXT,
                raw_notes TEXT,

                -- HASIL MATCHING KE MASTER
                institution_id INTEGER,
                product_path_id INTEGER,
                standard_id INTEGER,
                certification_scheme_id INTEGER,

                -- STATUS VALIDASI
                validation_status TEXT NOT NULL DEFAULT 'ERROR',
                validation_message TEXT,

                -- STATUS REVIEW
                review_status TEXT NOT NULL DEFAULT 'PENDING',
                review_note TEXT,

                reviewed_at TEXT,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (institution_id)
                    REFERENCES institution(institution_id)
                    ON DELETE SET NULL,

                FOREIGN KEY (product_path_id)
                    REFERENCES master_product_path(path_id)
                    ON DELETE SET NULL,

                FOREIGN KEY (standard_id)
                    REFERENCES master_standard(standard_id)
                    ON DELETE SET NULL,

                FOREIGN KEY (certification_scheme_id)
                    REFERENCES master_certification_scheme(
                        certification_scheme_id
                    )
                    ON DELETE SET NULL,

                CHECK (
                    validation_status IN (
                        'VALID',
                        'WARNING',
                        'ERROR'
                    )
                ),

                CHECK (
                    review_status IN (
                        'PENDING',
                        'APPROVED',
                        'REJECTED'
                    )
                )
            )
            """
        )


        # ====================================================
        # WORKFLOW BATCH RUANG LINGKUP
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scope_upload_batch (
                batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_code TEXT UNIQUE,

                file_name TEXT NOT NULL,
                import_mode TEXT NOT NULL DEFAULT 'REPLACE',

                status TEXT NOT NULL DEFAULT 'UPLOADED',

                total_rows INTEGER NOT NULL DEFAULT 0,
                valid_count INTEGER NOT NULL DEFAULT 0,
                corrected_count INTEGER NOT NULL DEFAULT 0,
                review_count INTEGER NOT NULL DEFAULT 0,
                rejected_count INTEGER NOT NULL DEFAULT 0,

                notes TEXT,
                rejection_reason TEXT,

                uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                processed_at TEXT,
                committed_at TEXT,
                rejected_at TEXT,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                CHECK (
                    import_mode IN (
                        'APPEND',
                        'REPLACE'
                    )
                ),

                CHECK (
                    status IN (
                        'UPLOADED',
                        'PROCESSING',
                        'WAITING_CORRECTION_APPROVAL',
                        'NEED_REVIEW',
                        'READY_TO_COMMIT',
                        'COMMITTED',
                        'REJECTED',
                        'FAILED'
                    )
                )
            )
            """
        )

        # ====================================================
        # KOLOM WORKFLOW PADA SCOPE_STAGING
        # ====================================================

        add_column_if_missing(
            conn,
            "scope_staging",
            "batch_id",
            "INTEGER",
        )

        add_column_if_missing(
            conn,
            "scope_staging",
            "row_status",
            "TEXT NOT NULL DEFAULT 'NEED_REVIEW'",
        )

        add_column_if_missing(
            conn,
            "scope_staging",
            "is_excluded",
            "INTEGER NOT NULL DEFAULT 0",
        )

        add_column_if_missing(
            conn,
            "scope_staging",
            "blocking_issue_count",
            "INTEGER NOT NULL DEFAULT 0",
        )

        add_column_if_missing(
            conn,
            "scope_staging",
            "processed_at",
            "TEXT",
        )

        # ====================================================
        # LOG AUTO-CORRECTION / MANUAL CORRECTION
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scope_correction_log (
                correction_id INTEGER PRIMARY KEY AUTOINCREMENT,

                batch_id INTEGER NOT NULL,
                staging_id INTEGER NOT NULL,
                row_no INTEGER,

                field_name TEXT NOT NULL,

                original_value TEXT,
                corrected_value TEXT,
                final_value TEXT,

                rule_id TEXT,
                correction_type TEXT NOT NULL DEFAULT 'AUTO',
                correction_note TEXT,
                confidence REAL,

                approval_status TEXT NOT NULL DEFAULT 'PENDING',
                decision_note TEXT,

                decided_at TEXT,
                decided_by TEXT,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (batch_id)
                    REFERENCES scope_upload_batch(batch_id)
                    ON DELETE CASCADE,

                FOREIGN KEY (staging_id)
                    REFERENCES scope_staging(staging_id)
                    ON DELETE CASCADE,

                CHECK (
                    correction_type IN (
                        'AUTO',
                        'MANUAL',
                        'ALIAS',
                        'NORMALIZATION',
                        'EXACT',
                        'CODE_MATCH',
                        'FUZZY'
                    )
                ),

                CHECK (
                    approval_status IN (
                        'PENDING',
                        'APPROVED',
                        'REJECTED',
                        'MANUAL'
                    )
                )
            )
            """
        )

        # ====================================================
        # REVIEW ISSUE
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scope_review_issue (
                issue_id INTEGER PRIMARY KEY AUTOINCREMENT,

                batch_id INTEGER NOT NULL,
                staging_id INTEGER NOT NULL,
                row_no INTEGER,

                field_name TEXT,
                original_value TEXT,
                suggested_value TEXT,

                rule_id TEXT,
                reason TEXT,

                confidence REAL,
                is_blocking INTEGER NOT NULL DEFAULT 1,

                decision TEXT,
                resolved_value TEXT,
                decision_note TEXT,

                resolved_at TEXT,
                resolved_by TEXT,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (batch_id)
                    REFERENCES scope_upload_batch(batch_id)
                    ON DELETE CASCADE,

                FOREIGN KEY (staging_id)
                    REFERENCES scope_staging(staging_id)
                    ON DELETE CASCADE,

                CHECK (
                    is_blocking IN (
                        0,
                        1
                    )
                ),

                CHECK (
                    decision IS NULL
                    OR decision IN (
                        'ACCEPT_SUGGESTION',
                        'USE_ORIGINAL',
                        'MANUAL',
                        'REJECT_ROW',
                        'RESOLVED'
                    )
                )
            )
            """
        )

        # ====================================================
        # ALIAS MASTER
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS master_alias (
                alias_id INTEGER PRIMARY KEY AUTOINCREMENT,

                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,

                alias_text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,

                source TEXT NOT NULL DEFAULT 'MANUAL_REVIEW',

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                UNIQUE (
                    entity_type,
                    normalized_text
                )
            )
            """
        )

        # ====================================================
        # VERSIONING RUANG LINGKUP
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scope_version (
                version_id INTEGER PRIMARY KEY AUTOINCREMENT,

                institution_id INTEGER NOT NULL,
                version_no INTEGER NOT NULL,
                batch_id INTEGER,

                is_active INTEGER NOT NULL DEFAULT 1,

                effective_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (institution_id)
                    REFERENCES institution(institution_id)
                    ON DELETE RESTRICT,

                FOREIGN KEY (batch_id)
                    REFERENCES scope_upload_batch(batch_id)
                    ON DELETE SET NULL,

                UNIQUE (
                    institution_id,
                    version_no
                ),

                CHECK (
                    is_active IN (
                        0,
                        1
                    )
                )
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scope_version_item (
                version_item_id INTEGER PRIMARY KEY AUTOINCREMENT,

                version_id INTEGER NOT NULL,

                product_path_id INTEGER NOT NULL,
                product_order_no TEXT,
                certification_scheme_id INTEGER,
                notes TEXT,

                source_staging_id INTEGER,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (version_id)
                    REFERENCES scope_version(version_id)
                    ON DELETE CASCADE,

                FOREIGN KEY (product_path_id)
                    REFERENCES master_product_path(path_id)
                    ON DELETE RESTRICT,

                FOREIGN KEY (certification_scheme_id)
                    REFERENCES master_certification_scheme(
                        certification_scheme_id
                    )
                    ON DELETE SET NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scope_version_standard (
                version_standard_id INTEGER PRIMARY KEY AUTOINCREMENT,

                version_item_id INTEGER NOT NULL,
                standard_id INTEGER NOT NULL,

                sequence_no INTEGER NOT NULL DEFAULT 1,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (version_item_id)
                    REFERENCES scope_version_item(version_item_id)
                    ON DELETE CASCADE,

                FOREIGN KEY (standard_id)
                    REFERENCES master_standard(standard_id)
                    ON DELETE RESTRICT,

                UNIQUE (
                    version_item_id,
                    standard_id
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
            ON institution(id_lspro)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_institution_status
            ON institution(status_accreditation)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_institution_source_status
            ON institution(source_status)
            """
        )

        # ====================================================
        # INDEX AMANDEMEN
        # ====================================================

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_amendment_institution
            ON institution_amendment(institution_id)
            """
        )

        # ====================================================
        # INDEX MASTER CATEGORY
        # ====================================================

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_master_category_scheme
            ON master_category(scheme_id)
            """
        )

        # ====================================================
        # INDEX MASTER SUBCATEGORY
        # ====================================================

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_master_subcategory_scheme
            ON master_subcategory(scheme_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_master_subcategory_category
            ON master_subcategory(category_id)
            """
        )

        # ====================================================
        # INDEX MASTER PRODUCT / SERVICE
        # ====================================================

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_master_product_scheme
            ON master_product_service(scheme_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_master_product_category
            ON master_product_service(category_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_master_product_subcategory
            ON master_product_service(subcategory_id)
            """
        )

        # ====================================================
        # INDEX PRODUCT PATH
        # ====================================================

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_product_path_scheme
            ON master_product_path(scheme_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_product_path_category
            ON master_product_path(category_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_product_path_subcategory
            ON master_product_path(subcategory_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_product_path_product
            ON master_product_path(product_service_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_product_path_status
            ON master_product_path(
                category_status,
                subcategory_status,
                product_service_status
            )
            """
        )

        # ====================================================
        # INDEX MASTER STANDAR
        # ====================================================

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_master_standard_number
            ON master_standard(standard_number)
            """
        )

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
            ux_master_standard_number
            ON master_standard(standard_number)
            """
        )

        # ====================================================
        # INDEX RUANG LINGKUP
        # ====================================================

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_institution
            ON scope(institution_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_product_path
            ON scope(product_path_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_certification_scheme
            ON scope(certification_scheme_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_product_order
            ON scope(
                institution_id,
                product_order_no
            )
            """
        )

        # ====================================================
        # INDEX SCOPE STANDARD
        # ====================================================

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_standard_scope
            ON scope_standard(scope_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_standard_standard
            ON scope_standard(standard_id)
            """
        )

        # ====================================================
        # INDEX STAGING
        # ====================================================

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_staging_validation
            ON scope_staging(validation_status)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_staging_review
            ON scope_staging(review_status)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_staging_institution
            ON scope_staging(institution_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_staging_product_path
            ON scope_staging(product_path_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_staging_standard
            ON scope_staging(standard_id)
            """
        )


        # ====================================================
        # INDEX WORKFLOW RUANG LINGKUP
        # ====================================================

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_batch_status
            ON scope_upload_batch(status)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_staging_batch
            ON scope_staging(batch_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_staging_row_status
            ON scope_staging(
                batch_id,
                row_status
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_correction_batch
            ON scope_correction_log(batch_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_correction_pending
            ON scope_correction_log(
                batch_id,
                approval_status
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_review_batch
            ON scope_review_issue(batch_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_review_blocking
            ON scope_review_issue(
                batch_id,
                is_blocking,
                decision
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_master_alias_lookup
            ON master_alias(
                entity_type,
                normalized_text
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_version_institution
            ON scope_version(
                institution_id,
                version_no
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_version_active
            ON scope_version(
                institution_id,
                is_active
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_version_item_version
            ON scope_version_item(version_id)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_scope_version_standard_item
            ON scope_version_standard(version_item_id)
            """
        )

        # ====================================================
        # COMMIT
        # ====================================================

        conn.commit()

        print()
        print(
            "========================================"
        )
        print(
            "DATABASE BERHASIL DIPERBARUI"
        )
        print(
            "========================================"
        )
        print()

        print(
            "Tabel tersedia:"
        )
        print(
            "- institution"
        )
        print(
            "- sync_history"
        )
        print(
            "- sync_lock"
        )
        print(
            "- institution_amendment"
        )
        print(
            "- master_scheme"
        )
        print(
            "- master_category"
        )
        print(
            "- master_subcategory"
        )
        print(
            "- master_product_service"
        )
        print(
            "- master_product_path"
        )
        print(
            "- master_certification_scheme"
        )
        print(
            "- master_standard"
        )
        print(
            "- scope"
        )
        print(
            "- scope_standard"
        )
        print(
            "- scope_staging"
        )
        print(
            "- scope_upload_batch"
        )
        print(
            "- scope_correction_log"
        )
        print(
            "- scope_review_issue"
        )
        print(
            "- master_alias"
        )
        print(
            "- scope_version"
        )
        print(
            "- scope_version_item"
        )
        print(
            "- scope_version_standard"
        )
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
