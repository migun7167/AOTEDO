"""SQLite database layer for Paperless AOT."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get(
    "PAPERLESS_AOT_DB",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "paperless_aot.db"),
)

SCHEMA = """
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
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
