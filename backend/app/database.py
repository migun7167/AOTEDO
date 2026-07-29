"""SQLite database layer for Paperless AOT."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "paperless_aot.db")


def db_path() -> str:
    """Resolved at call time, not import time, so PAPERLESS_AOT_DB can be set
    after this module is first imported (test suites do exactly that)."""
    return os.environ.get("PAPERLESS_AOT_DB", DEFAULT_DB_PATH)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_login_at TEXT
);

-- Failed sign-ins, kept so repeated attempts can be throttled and reviewed.
CREATE TABLE IF NOT EXISTS login_attempts (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    ip_address TEXT,
    success INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_attempts
ON login_attempts(username, created_at);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT
);

CREATE TABLE IF NOT EXISTS import_batches (
    id TEXT PRIMARY KEY,
    batch_no TEXT NOT NULL UNIQUE,
    imported_by TEXT,
    imported_at TEXT NOT NULL,
    source_channel TEXT NOT NULL,
    total_files INTEGER NOT NULL DEFAULT 0,
    success_files INTEGER NOT NULL DEFAULT 0,
    failed_files INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cargo_messages (
    id TEXT PRIMARY KEY,
    batch_id TEXT REFERENCES import_batches(id),
    message_type TEXT,
    message_version TEXT,
    original_filename TEXT,
    file_size INTEGER,
    source_channel TEXT,
    raw_message TEXT NOT NULL,
    message_hash TEXT NOT NULL,
    parse_status TEXT NOT NULL,
    parse_error_code TEXT,
    parse_error_message TEXT,
    duplicate_of TEXT,
    duplicate_type TEXT,
    imported_by TEXT,
    imported_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cargo_messages_hash ON cargo_messages(message_hash);
CREATE INDEX IF NOT EXISTS idx_cargo_messages_type ON cargo_messages(message_type);
CREATE INDEX IF NOT EXISTS idx_cargo_messages_imported_at ON cargo_messages(imported_at);

CREATE TABLE IF NOT EXISTS fwb_master (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES cargo_messages(id),
    mawb_number TEXT NOT NULL,
    airline_prefix TEXT,
    serial_number TEXT,
    origin TEXT,
    destination TEXT,
    pieces INTEGER,
    gross_weight REAL,
    weight_unit TEXT,
    chargeable_weight REAL,
    flight_number TEXT,
    flight_date TEXT,
    routing TEXT,
    shipper_name TEXT,
    shipper_address TEXT,
    shipper_country TEXT,
    consignee_name TEXT,
    consignee_address TEXT,
    consignee_country TEXT,
    agent_code TEXT,
    agent_name TEXT,
    currency TEXT,
    payment_type TEXT,
    rate REAL,
    freight_charge REAL,
    other_charge REAL,
    total_charge REAL,
    nature_of_goods TEXT,
    issue_date TEXT,
    issue_place TEXT,
    reference_number TEXT,
    special_handling_codes TEXT,
    parsed_data TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fwb_mawb ON fwb_master(mawb_number);
CREATE INDEX IF NOT EXISTS idx_fwb_route ON fwb_master(origin, destination);

CREATE TABLE IF NOT EXISTS fhl_house (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES cargo_messages(id),
    mawb_number TEXT NOT NULL,
    hawb_number TEXT NOT NULL,
    origin TEXT,
    destination TEXT,
    pieces INTEGER,
    gross_weight REAL,
    weight_unit TEXT,
    commodity TEXT,
    hs_code TEXT,
    customs_country TEXT,
    customs_party_type TEXT,
    customs_info_type TEXT,
    consignee_tax_id TEXT,
    shipper_name TEXT,
    shipper_address TEXT,
    shipper_country TEXT,
    shipper_postal_code TEXT,
    consignee_name TEXT,
    consignee_address TEXT,
    consignee_country TEXT,
    consignee_postal_code TEXT,
    consignee_phone TEXT,
    parsed_data TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fhl_mawb ON fhl_house(mawb_number);
CREATE INDEX IF NOT EXISTS idx_fhl_hawb ON fhl_house(hawb_number);

CREATE TABLE IF NOT EXISTS ffm_flight (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES cargo_messages(id),
    flight_number TEXT,
    flight_date TEXT,
    origin TEXT,
    destination TEXT,
    mawb_number TEXT,
    pieces INTEGER,
    gross_weight REAL,
    weight_unit TEXT,
    nature_of_goods TEXT,
    parsed_data TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ffm_mawb ON ffm_flight(mawb_number);

CREATE TABLE IF NOT EXISTS fsu_status (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES cargo_messages(id),
    mawb_number TEXT,
    status_code TEXT,
    airport TEXT,
    flight_number TEXT,
    status_date TEXT,
    status_time TEXT,
    weight REAL,
    weight_unit TEXT,
    hawb_number TEXT,
    raw_line TEXT,
    parsed_data TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fsu_mawb ON fsu_status(mawb_number);

CREATE TABLE IF NOT EXISTS matching_results (
    id TEXT PRIMARY KEY,
    mawb_number TEXT NOT NULL UNIQUE,
    fwb_id TEXT REFERENCES fwb_master(id),
    match_status TEXT NOT NULL,
    match_score INTEGER NOT NULL DEFAULT 0,
    fhl_count INTEGER NOT NULL DEFAULT 0,
    fwb_pieces INTEGER,
    fhl_total_pieces INTEGER,
    pieces_difference INTEGER,
    fwb_weight REAL,
    fhl_total_weight REAL,
    weight_difference REAL,
    weight_difference_percentage REAL,
    origin_match INTEGER,
    destination_match INTEGER,
    pieces_match INTEGER,
    weight_match INTEGER,
    duplicate_hawb INTEGER,
    reviewed INTEGER NOT NULL DEFAULT 0,
    reviewed_by TEXT,
    reviewed_at TEXT,
    review_note TEXT,
    override_status TEXT,
    override_reason TEXT,
    override_by TEXT,
    override_at TEXT,
    last_matched_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matching_result_houses (
    matching_result_id TEXT NOT NULL REFERENCES matching_results(id),
    fhl_id TEXT NOT NULL REFERENCES fhl_house(id),
    linked_by TEXT NOT NULL,
    linked_by_user TEXT,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (matching_result_id, fhl_id)
);

-- Manual link/unlink decisions (FR-014). Kept separate from
-- matching_result_houses so they survive every re-match.
CREATE TABLE IF NOT EXISTS house_link_overrides (
    id TEXT PRIMARY KEY,
    mawb_number TEXT NOT NULL,
    fhl_id TEXT NOT NULL REFERENCES fhl_house(id),
    action TEXT NOT NULL,
    reason TEXT,
    performed_by TEXT,
    performed_at TEXT NOT NULL,
    UNIQUE (mawb_number, fhl_id)
);

CREATE TABLE IF NOT EXISTS validation_results (
    id TEXT PRIMARY KEY,
    matching_result_id TEXT NOT NULL REFERENCES matching_results(id),
    rule_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    result TEXT NOT NULL,
    fwb_value TEXT,
    fhl_value TEXT,
    difference_value TEXT,
    message TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS match_history (
    id TEXT PRIMARY KEY,
    mawb_number TEXT NOT NULL,
    event_type TEXT NOT NULL,
    previous_status TEXT,
    new_status TEXT,
    previous_score INTEGER,
    new_score INTEGER,
    details TEXT,
    performed_by TEXT,
    performed_at TEXT NOT NULL
);

-- Delivery Orders issued to customs (one per house waybill). Stored so a
-- reprint always carries the same DO number as the original.
CREATE TABLE IF NOT EXISTS delivery_orders (
    id TEXT PRIMARY KEY,
    do_number TEXT NOT NULL UNIQUE,
    mawb_number TEXT NOT NULL,
    hawb_number TEXT,
    fhl_id TEXT REFERENCES fhl_house(id),
    station TEXT,
    do_date TEXT,
    customer_code TEXT,
    consignee_name TEXT,
    flight_number TEXT,
    aircraft_registration TEXT,
    landed_at TEXT,
    expiry_at TEXT,
    issued_by TEXT,
    pieces INTEGER,
    weight REAL,
    payload TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    reprint_count INTEGER NOT NULL DEFAULT 0,
    do_type TEXT NOT NULL DEFAULT 'SINGLE',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    superseded_by TEXT,
    split_from TEXT,
    -- A combined DO leaves hawb_number NULL, and SQLite treats NULLs as
    -- distinct, so this still stops two live single DOs for one house.
    UNIQUE (mawb_number, hawb_number)
);
CREATE INDEX IF NOT EXISTS idx_do_mawb ON delivery_orders(mawb_number);

-- One row per house waybill printed on a DO. A single DO has one; a combined
-- DO has many, which is what lets one consignee collect several shipments
-- against one release document.
CREATE TABLE IF NOT EXISTS delivery_order_lines (
    id TEXT PRIMARY KEY,
    do_id TEXT NOT NULL REFERENCES delivery_orders(id),
    line_no INTEGER NOT NULL,
    fhl_id TEXT REFERENCES fhl_house(id),
    mawb_number TEXT,
    hawb_number TEXT,
    shc TEXT,
    -- pieces/weight are what THIS document releases; house_* is everything the
    -- house holds. They differ on a part delivery, where the balance stays
    -- available for a later document.
    pieces INTEGER,
    master_pieces INTEGER,
    house_pieces INTEGER,
    weight REAL,
    master_weight REAL,
    house_weight REAL,
    is_partial INTEGER NOT NULL DEFAULT 0,
    weight_unit TEXT,
    board_point TEXT,
    off_point TEXT,
    flight_number TEXT,
    aircraft_registration TEXT,
    landed_at TEXT,
    nature_of_goods TEXT
);
CREATE INDEX IF NOT EXISTS idx_do_lines_do ON delivery_order_lines(do_id);
CREATE INDEX IF NOT EXISTS idx_do_lines_fhl ON delivery_order_lines(fhl_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    user_id TEXT,
    entity_type TEXT,
    entity_id TEXT,
    before_value TEXT,
    after_value TEXT,
    reason TEXT,
    ip_address TEXT,
    user_agent TEXT,
    created_at TEXT NOT NULL
);
"""


def get_connection() -> sqlite3.Connection:
    path = db_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Columns added after the first release. SQLite has no "ADD COLUMN IF NOT
# EXISTS", so they are applied only when missing from an existing database.
MIGRATIONS: list[tuple[str, str, str]] = [
    ("cargo_messages", "duplicate_type", "TEXT"),
    ("fsu_status", "status_time", "TEXT"),
    ("users", "must_change_password", "INTEGER NOT NULL DEFAULT 0"),
    ("matching_results", "override_status", "TEXT"),
    ("matching_results", "override_reason", "TEXT"),
    ("matching_results", "override_by", "TEXT"),
    ("matching_results", "override_at", "TEXT"),
    ("delivery_orders", "do_type", "TEXT NOT NULL DEFAULT 'SINGLE'"),
    ("delivery_orders", "status", "TEXT NOT NULL DEFAULT 'ACTIVE'"),
    ("delivery_orders", "superseded_by", "TEXT"),
    ("delivery_orders", "split_from", "TEXT"),
    ("delivery_order_lines", "house_pieces", "INTEGER"),
    ("delivery_order_lines", "house_weight", "REAL"),
    ("delivery_order_lines", "is_partial", "INTEGER NOT NULL DEFAULT 0"),
]


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        for table, column, coltype in MIGRATIONS:
            existing = {r["name"] for r in
                        conn.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        _backfill_do_lines(conn)
        conn.commit()
    finally:
        conn.close()


def _backfill_do_lines(conn: sqlite3.Connection) -> None:
    """Give every pre-existing single DO the line row the new model expects."""
    orphans = conn.execute(
        """SELECT d.* FROM delivery_orders d
           WHERE NOT EXISTS (SELECT 1 FROM delivery_order_lines l
                             WHERE l.do_id = d.id)""").fetchall()
    for row in orphans:
        payload = {}
        if row["payload"]:
            try:
                payload = json.loads(row["payload"])
            except ValueError:
                payload = {}
        conn.execute(
            """INSERT INTO delivery_order_lines
               (id, do_id, line_no, fhl_id, mawb_number, hawb_number, shc,
                pieces, master_pieces, weight, master_weight, weight_unit,
                board_point, off_point, flight_number, aircraft_registration,
                landed_at, nature_of_goods)
               VALUES (?,?,1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), row["id"], row["fhl_id"], row["mawb_number"],
             row["hawb_number"], payload.get("shc"), row["pieces"],
             payload.get("masterPieces"), row["weight"],
             payload.get("masterWeight"), payload.get("weightUnit"),
             payload.get("boardPoint"), payload.get("offPoint"),
             row["flight_number"], row["aircraft_registration"],
             row["landed_at"], payload.get("natureOfGoods")))


@contextmanager
def db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
