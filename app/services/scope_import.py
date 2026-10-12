import io
import re
import unicodedata

import pandas as pd

from rapidfuzz import fuzz

from app.database import get_connection


# ============================================================
# KONFIGURASI FORMAT FILE
# ============================================================

CANONICAL_COLUMNS = {
    "no_lpk": "No. LPK",
    "product_order_no": "No. Urut Produk",
    "scheme": "Skema",
    "category": "Kategori",
    "subcategory": "Sub Kategori",
    "product_service": "Jenis Produk/ Proses/Jasa",
    "standard_number": "Nomor Acuan Standar",
    "standard_title": "Judul Acuan Standar",
    "certification_scheme": "Skema Sertifikasi",
    "notes": "Catatan",
}


REQUIRED_CANONICAL_COLUMNS = {
    "no_lpk",
    "product_order_no",
    "scheme",
    "category",
    "subcategory",
    "product_service",
    "standard_number",
    "standard_title",
    "certification_scheme",
}


# ============================================================
# HELPER NILAI
# ============================================================

def is_missing(value):
    if value is None:
        return True

    try:
        return bool(
            pd.isna(value)
        )

    except Exception:
        return False


def value_to_text(value):
    """
    Mengubah nilai Excel/CSV menjadi teks tanpa melakukan
    semantic cleaning pada data mentah.

    Nilai string dikembalikan sebagaimana dibaca pandas.
    """
    if is_missing(value):
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
                int(value)
            )

    return str(value)


def compact_text(value):
    """
    Cleaning teknis ringan untuk nilai kerja/resolved.
    Tidak digunakan untuk mengganti raw value di staging.
    """
    text = value_to_text(value)

    if text is None:
        return None

    text = (
        text
        .replace("\u00a0", " ")
        .replace("\t", " ")
        .replace("\r", " ")
        .replace("\n", " ")
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    if text == "":
        return None

    return text


def normalize_for_match(value):
    """
    Normalisasi hanya untuk proses pencocokan.

    Data asli tetap disimpan pada raw_*.
    """
    text = compact_text(value)

    if text is None:
        return ""

    text = unicodedata.normalize(
        "NFKC",
        text,
    )

    text = (
        text
        .replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text.casefold()


def is_dash_value(value):
    text = compact_text(value)

    if text is None:
        return False

    normalized = (
        text
        .replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
        .strip()
    )

    return normalized == "-"


def hierarchy_state(value):
    """
    Status harus konsisten dengan Master Produk:
    VALUE / NOT_APPLICABLE / MISSING
    """
    if compact_text(value) is None:
        return (
            "MISSING",
            "",
        )

    if is_dash_value(value):
        return (
            "NOT_APPLICABLE",
            "",
        )

    return (
        "VALUE",
        normalize_for_match(value),
    )


# ============================================================
# HELPER HEADER
# ============================================================

def normalize_header(value):
    text = compact_text(value)

    if text is None:
        return ""

    text = unicodedata.normalize(
        "NFKC",
        text,
    )

    text = text.casefold()

    # Spasi di sekitar slash tidak dianggap berbeda.
    text = re.sub(
        r"\s*/\s*",
        "/",
        text,
    )

    # Spasi berlebih tidak dianggap berbeda.
    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


HEADER_ALIASES = {
    normalize_header(
        "No. LPK"
    ): "no_lpk",

    normalize_header(
        "No LPK"
    ): "no_lpk",

    normalize_header(
        "No. Urut Produk"
    ): "product_order_no",

    normalize_header(
        "No Urut Produk"
    ): "product_order_no",

    normalize_header(
        "Skema"
    ): "scheme",

    normalize_header(
        "Kategori"
    ): "category",

    normalize_header(
        "Sub Kategori"
    ): "subcategory",

    normalize_header(
        "Subkategori"
    ): "subcategory",

    normalize_header(
        "Jenis Produk/ Proses/Jasa"
    ): "product_service",

    normalize_header(
        "Jenis Produk/Proses/Jasa"
    ): "product_service",

    normalize_header(
        "Nomor Acuan Standar"
    ): "standard_number",

    normalize_header(
        "Judul Acuan Standar"
    ): "standard_title",

    normalize_header(
        "Skema Sertifikasi"
    ): "certification_scheme",

    normalize_header(
        "Catatan"
    ): "notes",
}


def find_header_row(raw_dataframe):
    """
    Mencari posisi header karena file sumber dapat memiliki
    baris kosong sebelum header.

    File contoh pengguna memiliki satu baris kosong sebelum
    header utama.
    """
    max_scan = min(
        len(raw_dataframe),
        30,
    )

    for row_index in range(
        max_scan
    ):
        found = set()

        for value in (
            raw_dataframe
            .iloc[row_index]
            .tolist()
        ):
            canonical = (
                HEADER_ALIASES.get(
                    normalize_header(value)
                )
            )

            if canonical:
                found.add(
                    canonical
                )

        if (
            REQUIRED_CANONICAL_COLUMNS
            .issubset(found)
        ):
            return row_index

    return None


def build_canonical_dataframe(
    raw_dataframe,
    header_row,
):
    header_values = (
        raw_dataframe
        .iloc[header_row]
        .tolist()
    )

    data = (
        raw_dataframe
        .iloc[
            header_row + 1:
        ]
        .copy()
    )

    data.columns = [
        value_to_text(value)
        or
        f"Unnamed_{index}"

        for index, value
        in enumerate(
            header_values
        )
    ]

    data = (
        data
        .dropna(
            how="all"
        )
        .reset_index(
            drop=True
        )
    )

    canonical_sources = {}

    for column in data.columns:
        canonical = (
            HEADER_ALIASES.get(
                normalize_header(column)
            )
        )

        if canonical is None:
            continue

        if canonical in canonical_sources:
            raise ValueError(
                (
                    "Header file ambigu. "
                    f"Kolom '{CANONICAL_COLUMNS[canonical]}' "
                    "terdeteksi lebih dari satu kali."
                )
            )

        canonical_sources[
            canonical
        ] = column

    missing = [
        CANONICAL_COLUMNS[column]

        for column
        in REQUIRED_CANONICAL_COLUMNS

        if column
        not in canonical_sources
    ]

    if missing:
        raise ValueError(
            (
                "Format file Ruang Lingkup tidak sesuai. "
                "Kolom berikut tidak ditemukan: "
                +
                ", ".join(
                    missing
                )
            )
        )

    result = pd.DataFrame()

    for canonical in (
        "no_lpk",
        "product_order_no",
        "scheme",
        "category",
        "subcategory",
        "product_service",
        "standard_number",
        "standard_title",
        "certification_scheme",
    ):
        result[
            canonical
        ] = data[
            canonical_sources[
                canonical
            ]
        ]

    if "notes" in canonical_sources:
        result[
            "notes"
        ] = data[
            canonical_sources[
                "notes"
            ]
        ]

    else:
        result[
            "notes"
        ] = None

    # Nomor baris Excel nyata.
    # header_row menggunakan indeks 0.
    # Data pertama berada pada header_row + 2 secara indeks,
    # lalu +1 untuk nomor baris manusia.
    result[
        "_source_row"
    ] = [
        header_row
        + 2
        + index

        for index
        in range(
            len(result)
        )
    ]

    return result


# ============================================================
# READ EXCEL / CSV
# ============================================================

def read_scope_file(
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

        workbook = pd.ExcelFile(
            stream
        )

        selected = None

        for sheet_name in (
            workbook.sheet_names
        ):
            raw = pd.read_excel(
                workbook,
                sheet_name=(
                    sheet_name
                ),
                header=None,
                dtype=object,
            )

            header_row = (
                find_header_row(
                    raw
                )
            )

            if header_row is not None:
                selected = (
                    raw,
                    header_row,
                )

                break

        if selected is None:
            raise ValueError(
                (
                    "Tidak ditemukan sheet dengan format "
                    "Ruang Lingkup yang sesuai."
                )
            )

        return (
            build_canonical_dataframe(
                selected[0],
                selected[1],
            )
        )

    # ========================================================
    # CSV
    # ========================================================

    if filename_lower.endswith(
        ".csv"
    ):
        raw = pd.read_csv(
            io.BytesIO(
                file_content
            ),
            header=None,
            dtype=object,
        )

        header_row = (
            find_header_row(
                raw
            )
        )

        if header_row is None:
            raise ValueError(
                (
                    "Header Ruang Lingkup "
                    "tidak ditemukan pada file CSV."
                )
            )

        return (
            build_canonical_dataframe(
                raw,
                header_row,
            )
        )

    raise ValueError(
        (
            "Format file tidak didukung. "
            "Gunakan .xlsx, .xls, atau .csv."
        )
    )


# ============================================================
# DETEKSI BARIS STRUKTURAL / BUKAN DATA
# ============================================================

def is_structural_row(row):
    """
    Baris judul kelompok atau separator tidak dimasukkan
    ke staging.

    Contoh pada file sementara:
    "Kelompok Produk : Process Certification (28)"
    tidak memiliki standar maupun jenis produk.
    """
    standard_number = compact_text(
        row[
            "standard_number"
        ]
    )

    product_service = compact_text(
        row[
            "product_service"
        ]
    )

    certification_scheme = compact_text(
        row[
            "certification_scheme"
        ]
    )

    scheme = compact_text(
        row[
            "scheme"
        ]
    )

    category = compact_text(
        row[
            "category"
        ]
    )

    subcategory = compact_text(
        row[
            "subcategory"
        ]
    )

    return (
        standard_number is None
        and
        product_service is None
        and
        certification_scheme is None
        and
        scheme is None
        and
        category is None
        and
        subcategory is None
    )


# ============================================================
# LOAD MASTER LEMBAGA
# ============================================================

def load_institutions(conn):
    rows = conn.execute(
        """
        SELECT
            institution_id,
            id_lspro,
            source_status
        FROM institution
        """
    ).fetchall()

    result = {}

    for row in rows:
        key = normalize_for_match(
            row[
                "id_lspro"
            ]
        )

        result[
            key
        ] = row

    return result


def extract_lpk_number(value):
    text = compact_text(value)

    if text is None:
        return None

    # Contoh:
    # 001
    # 1
    # LPK 001
    # LSPR-001-IDN
    match = re.search(
        r"(\d+)",
        text,
    )

    if not match:
        return None

    return (
        match
        .group(1)
        .zfill(3)
    )


def match_institution(
    institutions,
    raw_no_lpk,
):
    raw_clean = compact_text(
        raw_no_lpk
    )

    if raw_clean is None:
        return (
            None,
            None,
            "No. LPK kosong.",
        )

    candidates = [
        raw_clean,
    ]

    lpk_number = (
        extract_lpk_number(
            raw_clean
        )
    )

    if lpk_number:
        candidates.extend(
            [
                f"LSPR-{lpk_number}-IDN",
                f"LPK-{lpk_number}",
                lpk_number,
            ]
        )

    for candidate in candidates:
        row = institutions.get(
            normalize_for_match(
                candidate
            )
        )

        if row:
            warning = None

            if (
                row[
                    "source_status"
                ]
                !=
                "AVAILABLE"
            ):
                warning = (
                    "Lembaga ditemukan, tetapi "
                    f"source_status = "
                    f"'{row['source_status']}'."
                )

            return (
                row[
                    "institution_id"
                ],
                row,
                warning,
            )

    return (
        None,
        None,
        (
            f"No. LPK '{raw_clean}' "
            "tidak ditemukan di Master Lembaga."
        ),
    )


# ============================================================
# MATCHING HIERARKI MASTER PRODUK
# ============================================================

FUZZY_AUTO_MATCH_THRESHOLD = 90
FUZZY_SUGGESTION_THRESHOLD = 80


def canonical_code_part(value):
    """
    Menyamakan kode untuk matching tanpa mengubah data master.

    04  -> 4
    004 -> 4
    99  -> 99
    """
    text = compact_text(
        value
    )

    if text is None:
        return None

    text = text.strip()

    if text.isdigit():
        return str(
            int(
                text
            )
        )

    return text.casefold()


def extract_code_chain(value):
    """
    Mengambil kode hierarki dari tanda kurung paling akhir.

    Contoh:
    Peralatan dan Permesinan (04)
        -> ["4"]

    Peralatan Permesinan Lainnya (04.99)
        -> ["4", "99"]
    """
    text = compact_text(
        value
    )

    if text is None:
        return []

    match = re.search(
        r"\(\s*([A-Za-z0-9_-]+(?:\s*\.\s*[A-Za-z0-9_-]+)*)\s*\)\s*$",
        text,
    )

    if not match:
        return []

    return [
        canonical_code_part(
            part
        )
        for part
        in re.split(
            r"\s*\.\s*",
            match.group(1),
        )
        if canonical_code_part(
            part
        )
        is not None
    ]


def extract_local_code(value):
    parts = extract_code_chain(
        value
    )

    if not parts:
        return None

    return parts[-1]


def remove_trailing_code(value):
    """
    Kode di akhir dibuang hanya untuk perbandingan nama.

    Nilai raw di scope_staging tetap utuh.
    """
    text = compact_text(
        value
    )

    if text is None:
        return None

    cleaned = re.sub(
        r"\s*\(\s*[A-Za-z0-9_-]+(?:\s*\.\s*[A-Za-z0-9_-]+)*\s*\)\s*$",
        "",
        text,
    ).strip()

    return cleaned or None


def normalized_name_without_code(value):
    return normalize_for_match(
        remove_trailing_code(
            value
        )
    )


def fuzzy_score(
    source,
    target,
):
    source_key = normalize_for_match(
        source
    )

    target_key = normalize_for_match(
        target
    )

    if (
        not source_key
        or
        not target_key
    ):
        return 0.0

    if source_key == target_key:
        return 100.0

    return float(
        fuzz.WRatio(
            source_key,
            target_key,
        )
    )


def choose_fuzzy_candidate(
    source_value,
    candidates,
    value_getter,
    entity_label,
):
    """
    Pilih kandidat berdasarkan nama.

    Return:
    (
        selected_candidate,
        warning_message,
        error_message
    )

    >= 90:
        otomatis dipilih + WARNING

    80-89:
        tidak otomatis dipilih, ERROR dengan kandidat

    < 80:
        ERROR tidak ditemukan
    """
    source_text = compact_text(
        source_value
    )

    if source_text is None:
        return (
            None,
            None,
            f"{entity_label} kosong.",
        )

    if not candidates:
        return (
            None,
            None,
            f"Tidak ada kandidat {entity_label} pada parent yang sesuai.",
        )

    scored = []

    for candidate in candidates:
        target = value_getter(
            candidate
        )

        score = fuzzy_score(
            source_text,
            target,
        )

        scored.append(
            (
                score,
                candidate,
                target,
            )
        )

    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    best_score, best_candidate, best_target = (
        scored[0]
    )

    # Exact
    if best_score == 100:
        return (
            best_candidate,
            None,
            None,
        )

    # Auto fuzzy
    if (
        best_score
        >=
        FUZZY_AUTO_MATCH_THRESHOLD
    ):
        return (
            best_candidate,
            (
                f"{entity_label} '{source_text}' "
                f"dicocokkan dengan '{best_target}' "
                f"(kemiripan {best_score:.0f}%)."
            ),
            None,
        )

    # Kandidat cukup dekat, tetapi jangan auto-match
    if (
        best_score
        >=
        FUZZY_SUGGESTION_THRESHOLD
    ):
        return (
            None,
            None,
            (
                f"{entity_label} '{source_text}' belum cukup yakin "
                f"untuk auto-match. Kandidat terdekat "
                f"'{best_target}' ({best_score:.0f}%). "
                "Perlu review."
            ),
        )

    return (
        None,
        None,
        (
            f"{entity_label} '{source_text}' tidak ditemukan. "
            f"Kandidat terdekat '{best_target}' "
            f"hanya {best_score:.0f}%."
        ),
    )


def validate_dynamic_code_hierarchy(
    category,
    subcategory,
    product_service,
):
    """
    Validasi kode dilakukan berdasarkan level parent yang
    benar-benar aktif.

    Contoh yang didukung:

    1) Lengkap
       Kategori     (26)
       Sub Kategori (26.02)
       Jenis        (26.02.03)

    2) Tanpa Kategori
       Kategori     -
       Sub Kategori (05)
       Jenis        (05.02)

    3) Tanpa Sub Kategori
       Kategori     (27)
       Sub Kategori -
       Jenis        (27.03)

    4) Langsung Skema -> Jenis
       Kategori     -
       Sub Kategori -
       Jenis        tanpa kode / dengan kode tunggal
    """
    errors = []

    active_parent_codes = []

    # --------------------------------------------------------
    # KATEGORI
    # --------------------------------------------------------

    category_status, _ = hierarchy_state(
        category
    )

    category_chain = extract_code_chain(
        category
    )

    if (
        category_status
        ==
        "VALUE"
        and
        category_chain
    ):
        category_prefix = (
            category_chain[:-1]
        )

        if category_prefix:
            errors.append(
                (
                    "Kode Kategori seharusnya berupa kode level "
                    "Kategori saja, tetapi ditemukan "
                    f"({'.'.join(category_chain)})."
                )
            )

        active_parent_codes.append(
            category_chain[-1]
        )

    # --------------------------------------------------------
    # SUB KATEGORI
    # --------------------------------------------------------

    subcategory_status, _ = hierarchy_state(
        subcategory
    )

    subcategory_chain = extract_code_chain(
        subcategory
    )

    if (
        subcategory_status
        ==
        "VALUE"
        and
        subcategory_chain
    ):
        subcategory_prefix = (
            subcategory_chain[:-1]
        )

        if (
            subcategory_prefix
            and
            subcategory_prefix
            !=
            active_parent_codes
        ):
            errors.append(
                (
                    "Kode Sub Kategori tidak konsisten dengan "
                    "parent aktif. "
                    f"Parent={'.'.join(active_parent_codes) or '-'}, "
                    f"Sub Kategori={'.'.join(subcategory_chain)}."
                )
            )

        active_parent_codes.append(
            subcategory_chain[-1]
        )

    # --------------------------------------------------------
    # JENIS PRODUK / PROSES / JASA
    # --------------------------------------------------------

    product_status, _ = hierarchy_state(
        product_service
    )

    product_chain = extract_code_chain(
        product_service
    )

    if (
        product_status
        ==
        "VALUE"
        and
        product_chain
    ):
        product_prefix = (
            product_chain[:-1]
        )

        if (
            product_prefix
            and
            product_prefix
            !=
            active_parent_codes
        ):
            errors.append(
                (
                    "Kode Jenis Produk/Proses/Jasa tidak "
                    "konsisten dengan parent aktif. "
                    f"Parent={'.'.join(active_parent_codes) or '-'}, "
                    f"Jenis={'.'.join(product_chain)}."
                )
            )

    return errors


# ============================================================
# LOAD MASTER PRODUCT PATH
# ============================================================

def load_product_paths(conn):
    """
    Memuat seluruh hierarchy Master Produk.

    Path final dapat berbentuk:
    - Skema -> Jenis
    - Skema -> Kategori -> Jenis
    - Skema -> Sub Kategori -> Jenis
    - Skema -> Kategori -> Sub Kategori -> Jenis
    """
    return conn.execute(
        """
        SELECT
            path.path_id,

            scheme.scheme_id,
            scheme.scheme_code,
            scheme.scheme_name,

            category.category_id,
            category.category_code,
            category.category_name,

            subcategory.subcategory_id,
            subcategory.subcategory_code,
            subcategory.subcategory_name,

            product.product_service_id,
            product.product_service_code,
            product.product_service_name,

            path.category_status,
            path.subcategory_status,
            path.product_service_status

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

        ORDER BY
            path.path_id ASC
        """
    ).fetchall()


def unique_rows_by_id(
    rows,
    id_field,
):
    result = {}

    for row in rows:
        row_id = row[
            id_field
        ]

        if row_id is not None:
            result[
                row_id
            ] = row

    return list(
        result.values()
    )


def resolve_scheme(
    product_paths,
    raw_scheme,
):
    """
    Skema di Ruang Lingkup tidak memiliki kode.
    Karena itu matching dilakukan berdasarkan nama
    exact/fuzzy.
    """
    schemes = unique_rows_by_id(
        product_paths,
        "scheme_id",
    )

    selected, warning, error = (
        choose_fuzzy_candidate(
            raw_scheme,
            schemes,
            lambda row: row[
                "scheme_name"
            ],
            "Skema",
        )
    )

    if selected is None:
        return (
            None,
            [],
            warning,
            error,
        )

    scheme_id = selected[
        "scheme_id"
    ]

    filtered = [
        row
        for row
        in product_paths
        if row[
            "scheme_id"
        ]
        ==
        scheme_id
    ]

    return (
        scheme_id,
        filtered,
        warning,
        error,
    )


def resolve_category(
    candidate_paths,
    raw_category,
):
    """
    Kategori:
    - jika "-" / kosong -> cocokkan status path
    - jika VALUE + punya kode -> utamakan category_code
    - jika VALUE tanpa kode -> fallback exact/fuzzy nama
    """
    status, _ = hierarchy_state(
        raw_category
    )

    if status != "VALUE":
        filtered = [
            row
            for row
            in candidate_paths
            if row[
                "category_status"
            ]
            ==
            status
        ]

        if not filtered:
            return (
                None,
                [],
                None,
                (
                    "Status Kategori "
                    f"'{status}' tidak tersedia pada "
                    "Skema yang dipilih."
                ),
            )

        return (
            None,
            filtered,
            None,
            None,
        )

    categories = unique_rows_by_id(
        [
            row
            for row
            in candidate_paths
            if row[
                "category_status"
            ]
            ==
            "VALUE"
        ],
        "category_id",
    )

    category_code = extract_local_code(
        raw_category
    )

    # --------------------------------------------------------
    # MATCH BY CODE
    # --------------------------------------------------------

    if category_code is not None:
        matched = [
            row
            for row
            in categories
            if canonical_code_part(
                row[
                    "category_code"
                ]
            )
            ==
            category_code
        ]

        if not matched:
            return (
                None,
                [],
                None,
                (
                    f"Kategori dengan ID '{category_code}' "
                    "tidak ditemukan pada Skema yang dipilih."
                ),
            )

        selected = matched[0]

        warning = None

        source_name = (
            remove_trailing_code(
                raw_category
            )
        )

        master_name = (
            selected[
                "category_name"
            ]
        )

        if (
            normalize_for_match(
                source_name
            )
            !=
            normalize_for_match(
                master_name
            )
        ):
            score = fuzzy_score(
                source_name,
                master_name,
            )

            warning = (
                "ID Kategori cocok, tetapi nama berbeda: "
                f"'{source_name}' vs '{master_name}' "
                f"(kemiripan {score:.0f}%)."
            )

        category_id = selected[
            "category_id"
        ]

        filtered = [
            row
            for row
            in candidate_paths
            if row[
                "category_id"
            ]
            ==
            category_id
        ]

        return (
            category_id,
            filtered,
            warning,
            None,
        )

    # --------------------------------------------------------
    # FALLBACK NAME
    # --------------------------------------------------------

    selected, warning, error = (
        choose_fuzzy_candidate(
            remove_trailing_code(
                raw_category
            ),
            categories,
            lambda row: row[
                "category_name"
            ],
            "Kategori",
        )
    )

    if selected is None:
        return (
            None,
            [],
            warning,
            error,
        )

    category_id = selected[
        "category_id"
    ]

    filtered = [
        row
        for row
        in candidate_paths
        if row[
            "category_id"
        ]
        ==
        category_id
    ]

    return (
        category_id,
        filtered,
        warning,
        error,
    )


def resolve_subcategory(
    candidate_paths,
    raw_subcategory,
):
    """
    Sub Kategori bersifat dinamis.

    Jika kategori = "-", maka:
        Sub Kategori (05)
        dicari langsung di bawah Skema.

    Jika kategori VALUE, maka:
        Sub Kategori (26.02)
        mengambil local code = 02 dan dicari hanya
        di bawah category_id yang sudah terpilih.
    """
    status, _ = hierarchy_state(
        raw_subcategory
    )

    if status != "VALUE":
        filtered = [
            row
            for row
            in candidate_paths
            if row[
                "subcategory_status"
            ]
            ==
            status
        ]

        if not filtered:
            return (
                None,
                [],
                None,
                (
                    "Status Sub Kategori "
                    f"'{status}' tidak tersedia pada "
                    "parent yang dipilih."
                ),
            )

        return (
            None,
            filtered,
            None,
            None,
        )

    subcategories = unique_rows_by_id(
        [
            row
            for row
            in candidate_paths
            if row[
                "subcategory_status"
            ]
            ==
            "VALUE"
        ],
        "subcategory_id",
    )

    subcategory_code = extract_local_code(
        raw_subcategory
    )

    # --------------------------------------------------------
    # MATCH BY CODE
    # --------------------------------------------------------

    if subcategory_code is not None:
        matched = [
            row
            for row
            in subcategories
            if canonical_code_part(
                row[
                    "subcategory_code"
                ]
            )
            ==
            subcategory_code
        ]

        if not matched:
            return (
                None,
                [],
                None,
                (
                    f"Sub Kategori dengan ID "
                    f"'{subcategory_code}' tidak ditemukan "
                    "pada parent yang dipilih."
                ),
            )

        selected = matched[0]

        warning = None

        source_name = (
            remove_trailing_code(
                raw_subcategory
            )
        )

        master_name = (
            selected[
                "subcategory_name"
            ]
        )

        if (
            normalize_for_match(
                source_name
            )
            !=
            normalize_for_match(
                master_name
            )
        ):
            score = fuzzy_score(
                source_name,
                master_name,
            )

            warning = (
                "ID Sub Kategori cocok, tetapi nama berbeda: "
                f"'{source_name}' vs '{master_name}' "
                f"(kemiripan {score:.0f}%)."
            )

        subcategory_id = selected[
            "subcategory_id"
        ]

        filtered = [
            row
            for row
            in candidate_paths
            if row[
                "subcategory_id"
            ]
            ==
            subcategory_id
        ]

        return (
            subcategory_id,
            filtered,
            warning,
            None,
        )

    # --------------------------------------------------------
    # FALLBACK NAME
    # --------------------------------------------------------

    selected, warning, error = (
        choose_fuzzy_candidate(
            remove_trailing_code(
                raw_subcategory
            ),
            subcategories,
            lambda row: row[
                "subcategory_name"
            ],
            "Sub Kategori",
        )
    )

    if selected is None:
        return (
            None,
            [],
            warning,
            error,
        )

    subcategory_id = selected[
        "subcategory_id"
    ]

    filtered = [
        row
        for row
        in candidate_paths
        if row[
            "subcategory_id"
        ]
        ==
        subcategory_id
    ]

    return (
        subcategory_id,
        filtered,
        warning,
        error,
    )


def resolve_product_service(
    candidate_paths,
    raw_product_service,
):
    """
    Jenis Produk/Proses/Jasa:

    - Jika memiliki kode, gunakan local code terakhir.
      Contoh:
        Jasa boga (05.02) -> product_service_code = 02
        Produk X (26.02.03) -> product_service_code = 03

    - Jika tidak memiliki kode, exact/fuzzy nama dilakukan
      hanya di dalam parent aktif yang sudah dipilih.
    """
    status, _ = hierarchy_state(
        raw_product_service
    )

    if status != "VALUE":
        filtered = [
            row
            for row
            in candidate_paths
            if row[
                "product_service_status"
            ]
            ==
            status
        ]

        if not filtered:
            return (
                None,
                [],
                None,
                (
                    "Status Jenis Produk/Proses/Jasa "
                    f"'{status}' tidak tersedia pada "
                    "parent yang dipilih."
                ),
            )

        return (
            None,
            filtered,
            None,
            None,
        )

    products = unique_rows_by_id(
        [
            row
            for row
            in candidate_paths
            if row[
                "product_service_status"
            ]
            ==
            "VALUE"
        ],
        "product_service_id",
    )

    product_code = extract_local_code(
        raw_product_service
    )

    # --------------------------------------------------------
    # MATCH BY CODE JIKA ADA
    # --------------------------------------------------------

    if product_code is not None:
        matched = [
            row
            for row
            in products
            if canonical_code_part(
                row[
                    "product_service_code"
                ]
            )
            ==
            product_code
        ]

        if not matched:
            return (
                None,
                [],
                None,
                (
                    "Jenis Produk/Proses/Jasa dengan ID "
                    f"'{product_code}' tidak ditemukan "
                    "pada parent yang dipilih."
                ),
            )

        selected = matched[0]

        warning = None

        source_name = (
            remove_trailing_code(
                raw_product_service
            )
        )

        master_name = (
            selected[
                "product_service_name"
            ]
        )

        if (
            normalize_for_match(
                source_name
            )
            !=
            normalize_for_match(
                master_name
            )
        ):
            score = fuzzy_score(
                source_name,
                master_name,
            )

            warning = (
                "ID Jenis Produk/Proses/Jasa cocok, tetapi "
                "nama berbeda: "
                f"'{source_name}' vs '{master_name}' "
                f"(kemiripan {score:.0f}%)."
            )

        product_service_id = (
            selected[
                "product_service_id"
            ]
        )

        filtered = [
            row
            for row
            in candidate_paths
            if row[
                "product_service_id"
            ]
            ==
            product_service_id
        ]

        return (
            product_service_id,
            filtered,
            warning,
            None,
        )

    # --------------------------------------------------------
    # MATCH BY NAME
    # --------------------------------------------------------

    selected, warning, error = (
        choose_fuzzy_candidate(
            remove_trailing_code(
                raw_product_service
            ),
            products,
            lambda row: row[
                "product_service_name"
            ],
            "Jenis Produk/Proses/Jasa",
        )
    )

    if selected is None:
        return (
            None,
            [],
            warning,
            error,
        )

    product_service_id = (
        selected[
            "product_service_id"
        ]
    )

    filtered = [
        row
        for row
        in candidate_paths
        if row[
            "product_service_id"
        ]
        ==
        product_service_id
    ]

    return (
        product_service_id,
        filtered,
        warning,
        error,
    )


def match_product_path(
    product_paths,
    scheme,
    category,
    subcategory,
    product_service,
):
    """
    Matching dinamis berdasarkan parent yang aktif.

    Contoh:
    1. Produk -> Kategori -> Sub Kategori -> Jenis
    2. Jasa -> Kategori -> Jenis
    3. Usaha Pariwisata -> Sub Kategori -> Jenis
    4. Organik -> Jenis
    """
    hierarchy_errors = (
        validate_dynamic_code_hierarchy(
            category,
            subcategory,
            product_service,
        )
    )

    if hierarchy_errors:
        return (
            None,
            " | ".join(
                hierarchy_errors
            ),
            None,
        )

    warnings = []

    # ========================================================
    # 1. SKEMA
    # ========================================================

    (
        scheme_id,
        candidates,
        scheme_warning,
        scheme_error,
    ) = resolve_scheme(
        product_paths,
        scheme,
    )

    if scheme_error:
        return (
            None,
            scheme_error,
            None,
        )

    if scheme_warning:
        warnings.append(
            scheme_warning
        )

    # ========================================================
    # 2. KATEGORI
    # ========================================================

    (
        category_id,
        candidates,
        category_warning,
        category_error,
    ) = resolve_category(
        candidates,
        category,
    )

    if category_error:
        return (
            None,
            category_error,
            (
                " | ".join(
                    warnings
                )
                if warnings
                else None
            ),
        )

    if category_warning:
        warnings.append(
            category_warning
        )

    # ========================================================
    # 3. SUB KATEGORI
    # ========================================================

    (
        subcategory_id,
        candidates,
        subcategory_warning,
        subcategory_error,
    ) = resolve_subcategory(
        candidates,
        subcategory,
    )

    if subcategory_error:
        return (
            None,
            subcategory_error,
            (
                " | ".join(
                    warnings
                )
                if warnings
                else None
            ),
        )

    if subcategory_warning:
        warnings.append(
            subcategory_warning
        )

    # ========================================================
    # 4. JENIS PRODUK / PROSES / JASA
    # ========================================================

    (
        product_service_id,
        candidates,
        product_warning,
        product_error,
    ) = resolve_product_service(
        candidates,
        product_service,
    )

    if product_error:
        return (
            None,
            product_error,
            (
                " | ".join(
                    warnings
                )
                if warnings
                else None
            ),
        )

    if product_warning:
        warnings.append(
            product_warning
        )

    # ========================================================
    # 5. PATH FINAL
    # ========================================================

    if not candidates:
        return (
            None,
            (
                "Hierarchy berhasil dicocokkan, tetapi "
                "master_product_path tidak ditemukan."
            ),
            (
                " | ".join(
                    warnings
                )
                if warnings
                else None
            ),
        )

    ordered = sorted(
        candidates,
        key=lambda row: row[
            "path_id"
        ],
    )

    selected = ordered[0]

    if len(ordered) > 1:
        warnings.append(
            (
                "Ditemukan beberapa master_product_path "
                "untuk hierarchy yang sama. Sistem "
                f"menggunakan path_id {selected['path_id']}."
            )
        )

    return (
        selected[
            "path_id"
        ],
        None,
        (
            " | ".join(
                warnings
            )
            if warnings
            else None
        ),
    )


# ============================================================
# LOAD MASTER STANDAR
# ============================================================

def load_standards(conn):
    rows = conn.execute(
        """
        SELECT
            standard_id,
            standard_code,
            standard_number,
            standard_title
        FROM master_standard
        """
    ).fetchall()

    result = {}

    for row in rows:
        key = normalize_for_match(
            row[
                "standard_number"
            ]
        )

        # standard_number sudah UNIQUE.
        result[
            key
        ] = row

    return result


def match_standard(
    standards,
    raw_standard_number,
    raw_standard_title,
):
    standard_number = (
        compact_text(
            raw_standard_number
        )
    )

    if standard_number is None:
        return (
            None,
            None,
            "Nomor Acuan Standar kosong.",
            None,
        )

    row = standards.get(
        normalize_for_match(
            standard_number
        )
    )

    if row is None:
        return (
            None,
            None,
            (
                "Nomor Acuan Standar "
                f"'{standard_number}' "
                "tidak ditemukan di Master Standar."
            ),
            None,
        )

    warning = None

    master_title = compact_text(
        row[
            "standard_title"
        ]
    )

    source_title = compact_text(
        raw_standard_title
    )

    if master_title is None:
        warning = (
            "Nomor standar ditemukan, tetapi Judul "
            "Acuan Standar pada Master Standar "
            "masih kosong."
        )

    elif source_title is None:
        warning = (
            "Nomor standar ditemukan, tetapi Judul "
            "Acuan Standar pada file Ruang Lingkup "
            "kosong."
        )

    elif (
        normalize_for_match(
            master_title
        )
        !=
        normalize_for_match(
            source_title
        )
    ):
        warning = (
            "Nomor standar ditemukan, tetapi judul "
            "pada file berbeda dengan judul di "
            "Master Standar."
        )

    return (
        row[
            "standard_id"
        ],
        row,
        None,
        warning,
    )


# ============================================================
# LOAD MASTER SKEMA SERTIFIKASI
# ============================================================

def load_certification_schemes(
    conn,
):
    rows = conn.execute(
        """
        SELECT
            certification_scheme_id,
            certification_scheme_code,
            certification_scheme_name

        FROM master_certification_scheme

        ORDER BY
            certification_scheme_id ASC
        """
    ).fetchall()

    result = {}

    for row in rows:
        key = normalize_for_match(
            row[
                "certification_scheme_name"
            ]
        )

        result.setdefault(
            key,
            [],
        ).append(
            row
        )

    return result


def match_certification_scheme(
    certification_schemes,
    value,
):
    text = compact_text(
        value
    )

    if text is None:
        return (
            None,
            (
                "Skema Sertifikasi kosong atau tidak "
                "dapat diwarisi dari baris produk "
                "sebelumnya."
            ),
            None,
        )

    matches = (
        certification_schemes.get(
            normalize_for_match(
                text
            ),
            [],
        )
    )

    if not matches:
        return (
            None,
            (
                "Skema Sertifikasi "
                f"'{text}' tidak ditemukan di "
                "Master Skema Sertifikasi."
            ),
            None,
        )

    selected = matches[0]

    warning = None

    if len(matches) > 1:
        warning = (
            "Nama Skema Sertifikasi cocok dengan "
            f"{len(matches)} data master. Sistem "
            "menggunakan ID pertama."
        )

    return (
        selected[
            "certification_scheme_id"
        ],
        None,
        warning,
    )


# ============================================================
# CONTEXT BARIS LANJUTAN STANDAR
# ============================================================

def make_context_key(
    raw_no_lpk,
):
    lpk_number = (
        extract_lpk_number(
            raw_no_lpk
        )
    )

    if lpk_number:
        return lpk_number

    return normalize_for_match(
        raw_no_lpk
    )


def is_standard_continuation_row(
    row,
):
    """
    Hanya forward-fill saat benar-benar terlihat sebagai
    baris standar lanjutan:

    - Nomor Acuan Standar ada
    - No. Urut Produk kosong
    - Jenis Produk/Proses/Jasa kosong

    Ini mencegah blank semantik pada data master dianggap
    otomatis sama dengan baris sebelumnya.
    """
    return (
        compact_text(
            row[
                "standard_number"
            ]
        )
        is not None

        and

        compact_text(
            row[
                "product_order_no"
            ]
        )
        is None

        and

        compact_text(
            row[
                "product_service"
            ]
        )
        is None
    )


def resolve_row_context(
    row,
    previous_context,
):
    current = {
        "product_order_no":
            compact_text(
                row[
                    "product_order_no"
                ]
            ),

        "scheme":
            value_to_text(
                row[
                    "scheme"
                ]
            ),

        "category":
            value_to_text(
                row[
                    "category"
                ]
            ),

        "subcategory":
            value_to_text(
                row[
                    "subcategory"
                ]
            ),

        "product_service":
            value_to_text(
                row[
                    "product_service"
                ]
            ),

        "certification_scheme":
            value_to_text(
                row[
                    "certification_scheme"
                ]
            ),
    }

    continuation = (
        is_standard_continuation_row(
            row
        )
    )

    if (
        continuation
        and
        previous_context
    ):
        for key in current:
            if compact_text(
                current[
                    key
                ]
            ) is None:
                current[
                    key
                ] = previous_context.get(
                    key
                )

    return (
        current,
        continuation,
    )


# ============================================================
# IMPORT KE SCOPE STAGING
# ============================================================

def import_scope_to_staging(
    file_content,
    filename,
    replace_staging=True,
):
    """
    Membaca file Ruang Lingkup dan memasukkan hasilnya ke
    scope_staging.

    Prinsip:
    - raw_* menyimpan nilai sumber.
    - cleaning hanya dipakai untuk matching.
    - data tidak langsung masuk scope final.
    - baris gagal matching tetap masuk staging sebagai ERROR.
    - setiap data menunggu review admin.
    """

    dataframe = read_scope_file(
        file_content,
        filename,
    )

    if dataframe.empty:
        raise ValueError(
            "File Ruang Lingkup tidak memiliki data."
        )

    conn = get_connection()

    try:
        institutions = (
            load_institutions(
                conn
            )
        )

        product_paths = (
            load_product_paths(
                conn
            )
        )

        standards = (
            load_standards(
                conn
            )
        )

        certification_schemes = (
            load_certification_schemes(
                conn
            )
        )

        if not institutions:
            raise ValueError(
                (
                    "Master Lembaga masih kosong. "
                    "Import Master Lembaga terlebih dahulu."
                )
            )

        if not product_paths:
            raise ValueError(
                (
                    "Master Produk masih kosong. "
                    "Import Master Produk terlebih dahulu."
                )
            )

        if not standards:
            raise ValueError(
                (
                    "Master Standar masih kosong. "
                    "Import Master Standar terlebih dahulu."
                )
            )

        if not certification_schemes:
            raise ValueError(
                (
                    "Master Skema Sertifikasi masih kosong. "
                    "Import Master Skema Sertifikasi "
                    "terlebih dahulu."
                )
            )

        conn.execute(
            "BEGIN"
        )

        if replace_staging:
            conn.execute(
                """
                DELETE FROM scope_staging
                """
            )

        valid_count = 0
        warning_count = 0
        error_count = 0
        skipped_count = 0
        inserted_count = 0

        # Context dipisahkan per No. LPK.
        contexts = {}

        for _, row in dataframe.iterrows():
            source_row = int(
                row[
                    "_source_row"
                ]
            )

            raw_no_lpk = value_to_text(
                row[
                    "no_lpk"
                ]
            )

            raw_product_order_no = (
                value_to_text(
                    row[
                        "product_order_no"
                    ]
                )
            )

            raw_scheme = value_to_text(
                row[
                    "scheme"
                ]
            )

            raw_category = value_to_text(
                row[
                    "category"
                ]
            )

            raw_subcategory = (
                value_to_text(
                    row[
                        "subcategory"
                    ]
                )
            )

            raw_product_service = (
                value_to_text(
                    row[
                        "product_service"
                    ]
                )
            )

            raw_standard_number = (
                value_to_text(
                    row[
                        "standard_number"
                    ]
                )
            )

            raw_standard_title = (
                value_to_text(
                    row[
                        "standard_title"
                    ]
                )
            )

            raw_certification_scheme = (
                value_to_text(
                    row[
                        "certification_scheme"
                    ]
                )
            )

            raw_notes = value_to_text(
                row[
                    "notes"
                ]
            )

            context_key = (
                make_context_key(
                    raw_no_lpk
                )
            )

            # =================================================
            # SKIP BARIS STRUKTURAL / SEPARATOR
            # =================================================

            if is_structural_row(
                row
            ):
                skipped_count += 1

                # Header kelompok / separator dianggap batas
                # konteks agar tidak salah forward-fill.
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
            ) = resolve_row_context(
                row,
                previous_context,
            )

            resolved_product_order_no = (
                compact_text(
                    resolved[
                        "product_order_no"
                    ]
                )
            )

            errors = []
            warnings = []

            # =================================================
            # MATCH LEMBAGA
            # =================================================

            (
                institution_id,
                institution_row,
                institution_message,
            ) = match_institution(
                institutions,
                raw_no_lpk,
            )

            if institution_id is None:
                errors.append(
                    institution_message
                )

            elif institution_message:
                warnings.append(
                    institution_message
                )

            # =================================================
            # NOMOR URUT PRODUK
            # =================================================

            if (
                resolved_product_order_no
                is None
            ):
                errors.append(
                    (
                        "No. Urut Produk kosong dan tidak "
                        "dapat diwarisi dari baris produk "
                        "sebelumnya."
                    )
                )

            # =================================================
            # MATCH MASTER PRODUK
            # =================================================

            (
                product_path_id,
                product_error,
                product_warning,
            ) = match_product_path(
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
                    product_error
                )

            if product_warning:
                warnings.append(
                    product_warning
                )

            # =================================================
            # MATCH MASTER STANDAR
            # =================================================

            (
                standard_id,
                standard_row,
                standard_error,
                standard_warning,
            ) = match_standard(
                standards,
                raw_standard_number,
                raw_standard_title,
            )

            if standard_error:
                errors.append(
                    standard_error
                )

            if standard_warning:
                warnings.append(
                    standard_warning
                )

            # =================================================
            # MATCH MASTER SKEMA SERTIFIKASI
            # =================================================

            (
                certification_scheme_id,
                certification_error,
                certification_warning,
            ) = match_certification_scheme(
                certification_schemes,
                resolved[
                    "certification_scheme"
                ],
            )

            if certification_error:
                errors.append(
                    certification_error
                )

            if certification_warning:
                warnings.append(
                    certification_warning
                )

            # =================================================
            # STATUS
            # =================================================

            if errors:
                validation_status = (
                    "ERROR"
                )

                error_count += 1

            elif warnings:
                validation_status = (
                    "WARNING"
                )

                warning_count += 1

            else:
                validation_status = (
                    "VALID"
                )

                valid_count += 1

            messages = []

            if errors:
                messages.append(
                    "ERROR: "
                    +
                    " | ".join(
                        errors
                    )
                )

            if warnings:
                messages.append(
                    "WARNING: "
                    +
                    " | ".join(
                        warnings
                    )
                )

            if (
                continuation
                and
                not errors
                and
                not warnings
            ):
                messages.append(
                    (
                        "Baris standar lanjutan: konteks "
                        "produk diwarisi dari baris produk "
                        "sebelumnya pada No. LPK yang sama."
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

            # =================================================
            # INSERT STAGING
            # =================================================

            conn.execute(
                """
                INSERT INTO scope_staging (
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
                    'PENDING',
                    NULL,
                    NULL
                )
                """,
                (
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

            inserted_count += 1

            # =================================================
            # UPDATE CONTEXT
            # =================================================

            if context_key:
                # Simpan context hanya jika baris memiliki
                # informasi produk nyata. Baris continuation
                # mempertahankan context yang sama.
                if (
                    not continuation
                    and
                    (
                        compact_text(
                            resolved[
                                "product_service"
                            ]
                        )
                        is not None
                        or
                        compact_text(
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

        conn.commit()

        return {
            "source_rows":
                int(
                    len(
                        dataframe
                    )
                ),

            "inserted_count":
                inserted_count,

            "valid_count":
                valid_count,

            "warning_count":
                warning_count,

            "error_count":
                error_count,

            "skipped_count":
                skipped_count,

            "replace_staging":
                bool(
                    replace_staging
                ),
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

# ============================================================
# REVALIDASI DATA STAGING
# ============================================================

def revalidate_scope_staging():
    """
    Menjalankan ulang matching seluruh data scope_staging
    terhadap master terbaru tanpa perlu upload ulang file.

    Digunakan setelah Master Lembaga / Master Produk /
    Master Standar / Master Skema Sertifikasi diperbarui.

    Catatan:
    - raw_* tidak diubah.
    - hasil matching dan validation_status diperbarui.
    - review_status dikembalikan menjadi PENDING karena
      hasil validasi setelah perubahan master perlu direview lagi.
    """

    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT
                staging_id,
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
                raw_notes
            FROM scope_staging
            ORDER BY
                source_row ASC,
                staging_id ASC
            """
        ).fetchall()

        if not rows:
            raise ValueError(
                "Belum ada data pada scope_staging untuk direvalidasi."
            )

        institutions = load_institutions(conn)
        product_paths = load_product_paths(conn)
        standards = load_standards(conn)
        certification_schemes = load_certification_schemes(conn)

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

        conn.execute("BEGIN")

        valid_count = 0
        warning_count = 0
        error_count = 0
        updated_count = 0

        contexts = {}
        last_source_row_by_context = {}

        for staging_row in rows:
            raw_no_lpk = staging_row[
                "raw_no_lpk"
            ]

            context_key = make_context_key(
                raw_no_lpk
            )

            source_row = staging_row[
                "source_row"
            ]

            # Jika ada lompatan nomor baris Excel, kemungkinan ada
            # separator/header kelompok yang sebelumnya di-skip.
            # Putus context agar forward-fill tidak menyeberang grup.
            if context_key:
                previous_source_row = (
                    last_source_row_by_context.get(
                        context_key
                    )
                )

                if (
                    previous_source_row is not None
                    and
                    source_row is not None
                    and
                    source_row > previous_source_row + 1
                ):
                    contexts.pop(
                        context_key,
                        None,
                    )

            row = {
                "product_order_no":
                    staging_row[
                        "raw_product_order_no"
                    ],

                "scheme":
                    staging_row[
                        "raw_scheme"
                    ],

                "category":
                    staging_row[
                        "raw_category"
                    ],

                "subcategory":
                    staging_row[
                        "raw_subcategory"
                    ],

                "product_service":
                    staging_row[
                        "raw_product_service"
                    ],

                "standard_number":
                    staging_row[
                        "raw_standard_number"
                    ],

                "certification_scheme":
                    staging_row[
                        "raw_certification_scheme"
                    ],
            }

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
            ) = resolve_row_context(
                row,
                previous_context,
            )

            resolved_product_order_no = compact_text(
                resolved[
                    "product_order_no"
                ]
            )

            errors = []
            warnings = []

            # ------------------------------------------------
            # MATCH MASTER LEMBAGA
            # ------------------------------------------------

            (
                institution_id,
                _institution_row,
                institution_message,
            ) = match_institution(
                institutions,
                raw_no_lpk,
            )

            if institution_id is None:
                errors.append(
                    institution_message
                )

            elif institution_message:
                warnings.append(
                    institution_message
                )

            # ------------------------------------------------
            # NOMOR URUT PRODUK
            # ------------------------------------------------

            if resolved_product_order_no is None:
                errors.append(
                    (
                        "No. Urut Produk kosong dan tidak dapat "
                        "diwarisi dari baris produk sebelumnya."
                    )
                )

            # ------------------------------------------------
            # MATCH MASTER PRODUK
            # ------------------------------------------------

            (
                product_path_id,
                product_error,
                product_warning,
            ) = match_product_path(
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
                    product_error
                )

            if product_warning:
                warnings.append(
                    product_warning
                )

            # ------------------------------------------------
            # MATCH MASTER STANDAR
            # ------------------------------------------------

            (
                standard_id,
                _standard_row,
                standard_error,
                standard_warning,
            ) = match_standard(
                standards,
                staging_row[
                    "raw_standard_number"
                ],
                staging_row[
                    "raw_standard_title"
                ],
            )

            if standard_error:
                errors.append(
                    standard_error
                )

            if standard_warning:
                warnings.append(
                    standard_warning
                )

            # ------------------------------------------------
            # MATCH MASTER SKEMA SERTIFIKASI
            # ------------------------------------------------

            (
                certification_scheme_id,
                certification_error,
                certification_warning,
            ) = match_certification_scheme(
                certification_schemes,
                resolved[
                    "certification_scheme"
                ],
            )

            if certification_error:
                errors.append(
                    certification_error
                )

            if certification_warning:
                warnings.append(
                    certification_warning
                )

            # ------------------------------------------------
            # STATUS VALIDASI
            # ------------------------------------------------

            if errors:
                validation_status = "ERROR"
                error_count += 1

            elif warnings:
                validation_status = "WARNING"
                warning_count += 1

            else:
                validation_status = "VALID"
                valid_count += 1

            messages = []

            if errors:
                messages.append(
                    "ERROR: "
                    +
                    " | ".join(
                        errors
                    )
                )

            if warnings:
                messages.append(
                    "WARNING: "
                    +
                    " | ".join(
                        warnings
                    )
                )

            if (
                continuation
                and
                not errors
                and
                not warnings
            ):
                messages.append(
                    (
                        "Baris standar lanjutan: konteks produk "
                        "diwarisi dari baris produk sebelumnya "
                        "pada No. LPK yang sama."
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

            # ------------------------------------------------
            # UPDATE STAGING
            # ------------------------------------------------

            conn.execute(
                """
                UPDATE scope_staging

                SET
                    resolved_product_order_no = ?,
                    institution_id = ?,
                    product_path_id = ?,
                    standard_id = ?,
                    certification_scheme_id = ?,
                    validation_status = ?,
                    validation_message = ?,
                    review_status = 'PENDING',
                    review_note = NULL,
                    reviewed_at = NULL,
                    updated_at = CURRENT_TIMESTAMP

                WHERE staging_id = ?
                """,
                (
                    resolved_product_order_no,
                    institution_id,
                    product_path_id,
                    standard_id,
                    certification_scheme_id,
                    validation_status,
                    validation_message,
                    staging_row[
                        "staging_id"
                    ],
                ),
            )

            updated_count += 1

            # ------------------------------------------------
            # UPDATE CONTEXT
            # ------------------------------------------------

            if context_key:
                if (
                    not continuation
                    and
                    (
                        compact_text(
                            resolved[
                                "product_service"
                            ]
                        )
                        is not None
                        or
                        compact_text(
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

                if source_row is not None:
                    last_source_row_by_context[
                        context_key
                    ] = source_row

        conn.commit()

        return {
            "updated_count":
                updated_count,

            "valid_count":
                valid_count,

            "warning_count":
                warning_count,

            "error_count":
                error_count,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

