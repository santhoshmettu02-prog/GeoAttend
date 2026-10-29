import hashlib
import hmac
import os
import secrets
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PHOTO_DIR = DATA_DIR / "photos"
DB_PATH = DATA_DIR / "geoattend.db"


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240_000)
    return f"pbkdf2_sha256${salt.hex()}${key.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_hex, key_hex = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        expected = bytes.fromhex(key_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 240_000)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def initialize():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS employees (
            employee_id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            department TEXT NOT NULL DEFAULT 'General',
            role TEXT NOT NULL DEFAULT 'Employee' CHECK(role IN ('Admin','Employee')),
            status INTEGER NOT NULL DEFAULT 1 CHECK(status IN (0,1)),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS office_locations (
            location_id INTEGER PRIMARY KEY AUTOINCREMENT,
            location_name TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            allowed_radius INTEGER NOT NULL CHECK(allowed_radius > 0)
        );
        CREATE TABLE IF NOT EXISTS attendance (
            attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(employee_id),
            location_id INTEGER NOT NULL REFERENCES office_locations(location_id),
            work_date TEXT NOT NULL,
            check_in_time TEXT NOT NULL,
            check_out_time TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            accuracy_m REAL,
            photo_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Present' CHECK(status IN ('Present','Pending','Rejected')),
            UNIQUE(employee_id, work_date)
        );
        CREATE TABLE IF NOT EXISTS attendance_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            attendance_id INTEGER REFERENCES attendance(attendance_id) ON DELETE SET NULL,
            actor_id INTEGER REFERENCES employees(employee_id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            remarks TEXT,
            action_time TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(work_date);
        CREATE INDEX IF NOT EXISTS idx_attendance_employee ON attendance(employee_id, work_date);
        """)
        if not con.execute("SELECT 1 FROM office_locations LIMIT 1").fetchone():
            con.execute("INSERT INTO office_locations(location_name, latitude, longitude, allowed_radius) VALUES(?,?,?,?)",
                        ("GeoAttend Demo Office", 27.1751, 78.0421, 500))
        if not con.execute("SELECT 1 FROM employees WHERE role='Admin' LIMIT 1").fetchone():
            con.execute("INSERT INTO employees(employee_name,email,password_hash,department,role) VALUES(?,?,?,?,?)",
                        ("Demo Administrator", "admin@geoattend.local", hash_password("Admin@123"), "Administration", "Admin"))


def audit(con, attendance_id, actor_id, action, remarks=""):
    con.execute("INSERT INTO attendance_audit(attendance_id,actor_id,action,remarks) VALUES(?,?,?,?)",
                (attendance_id, actor_id, action, remarks))
