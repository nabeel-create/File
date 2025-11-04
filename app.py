# app.py
import streamlit as st
import sqlite3
import os
import secrets
import string
import time
from datetime import datetime, timedelta
from pathlib import Path

# --- CONFIG ---
UPLOAD_FOLDER = Path("uploads")
DB_PATH = "files.db"
CODE_LENGTH = 8            # length of generated code (alphanumeric)
EXPIRY_HOURS = 24          # default expiry after upload
ONE_TIME_DOWNLOAD = True   # set True to delete file after a successful download
MAX_FILE_SIZE_MB = 50      # soft limit - Streamlit will handle server limits too

# ensure folders exist
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

# --- DB helpers ---
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            saved_name TEXT,
            original_name TEXT,
            created_at INTEGER,
            expires_at INTEGER,
            downloaded INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn

conn = init_db()

def generate_code(n=CODE_LENGTH):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(n))

def cleanup_expired():
    now = int(time.time())
    c = conn.cursor()
    # delete expired files from disk and DB
    c.execute("SELECT id, saved_name FROM files WHERE expires_at <= ?", (now,))
    rows = c.fetchall()
    for _id, saved_name in rows:
        try:
            fpath = UPLOAD_FOLDER / saved_name
            if fpath.exists():
                fpath.unlink()
        except Exception:
            pass
    c.execute("DELETE FROM files WHERE expires_at <= ?", (now,))
    conn.commit()

def save_file_and_record(uploaded_file, expiry_seconds):
    # limit size check (soft)
    uploaded_file.seek(0, os.SEEK_END)
    size = uploaded_file.tell()
    uploaded_file.seek(0)
    if size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError(f"File exceeds {MAX_FILE_SIZE_MB} MB limit.")

    code = generate_code()
    # ensure uniqueness (very unlikely collision)
    c = conn.cursor()
    while True:
        c.execute("SELECT 1 FROM files WHERE code=?", (code,))
        if c.fetchone() is None:
            break
        code = generate_code()

    timestamp = int(time.time())
    expires_at = timestamp + expiry_seconds

    # saved filename to avoid collisions
    saved_name = f"{timestamp}_{secrets.token_hex(8)}_{uploaded_file.name}"
    dest = UPLOAD_FOLDER / saved_name
    # write bytes
    with open(dest, "wb") as f:
        f.write(uploaded_file.read())

    c.execute(
        "INSERT INTO files (code, saved_name, original_name, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
        (code, saved_name, uploaded_file.name, timestamp, expires_at)
    )
    conn.commit()
    return code, expires_at

def get_record_by_code(code):
    c = conn.cursor()
    c.execute("SELECT id, saved_name, original_name, created_at, expires_at, downloaded FROM files WHERE code=?", (code,))
    r = c.fetchone()
    return r

def mark_downloaded_and_maybe_delete(record_id, saved_name):
    c = conn.cursor()
    c.execute("UPDATE files SET downloaded=1 WHERE id=?", (record_id,))
    conn.commit()
    if ONE_TIME_DOWNLOAD:
        try:
            path = UPLOAD_FOLDER / saved_name
            if path.exists():
                path.unlink()
        except Exception:
            pass
        # remove DB row
        c.execute("DELETE FROM files WHERE id=?", (record_id,))
        conn.commit()

# perform cleanup at app start
cleanup_expired()

# --- Streamlit UI ---
st.set_page_config(page_title="FileShare with Code", layout="centered")

st.title("🔐 File Share — Upload → Generate Code → Download with Code")
st.write("Upload a file and you'll receive a secret code. Share the code with someone else so they can download the file from another computer.")

mode = st.radio("Choose action", ("Upload & generate code", "Enter code to download"))

if mode == "Upload & generate code":
    st.header("Upload file")
    uploaded_file = st.file_uploader("Choose file to upload", accept_multiple_files=False)
    col1, col2 = st.columns(2)
    with col1:
        expiry_hours = st.number_input("Expires in (hours)", min_value=1, max_value=168, value=EXPIRY_HOURS)
    with col2:
        one_time = st.checkbox("One-time download (delete file after first download)", value=ONE_TIME_DOWNLOAD)
    if st.button("Upload & Generate Code"):
        if uploaded_file is None:
            st.error("Choose a file first.")
        else:
            try:
                # update runtime option
                global ONE_TIME_DOWNLOAD
                ONE_TIME_DOWNLOAD = one_time

                code, expires_at = save_file_and_record(uploaded_file, expiry_hours * 3600)
                exp_dt = datetime.utcfromtimestamp(expires_at)  # UTC time
                st.success("File uploaded and code generated!")
                st.code(code, language="text")
                st.write(f"Share this code with the person who should download the file. Expires on (UTC): {exp_dt}  — you can convert to your timezone.")
                st.info("Important: Treat the code like a password. Anyone with it can download the file until it expires or is downloaded (if one-time enabled).")
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error("Upload failed: " + str(e))


else:
    st.header("Enter code to download file")
    code_input = st.text_input("Enter download code", value="")
    if st.button("Fetch file"):
        if not code_input:
            st.error("Enter the code you received from uploader.")
        else:
            cleanup_expired()  # ensure expired removed
            rec = get_record_by_code(code_input.strip())
            if rec is None:
                st.error("Invalid or expired code.")
            else:
                rec_id, saved_name, orig_name, created_at, expires_at, downloaded = rec
                now = int(time.time())
                if expires_at <= now:
                    st.error("This code has expired.")
                elif ONE_TIME_DOWNLOAD and downloaded:
                    st.error("This file was already downloaded (one-time).")
                else:
                    path = UPLOAD_FOLDER / saved_name
                    if not path.exists():
                        st.error("File missing on server (maybe it was deleted).")
                    else:
                        with open(path, "rb") as f:
                            data = f.read()
                        st.write(f"Original filename: **{orig_name}**")
                        st.download_button("Download file", data=data, file_name=orig_name)
                        # mark downloaded and optionally delete
                        mark_downloaded_and_maybe_delete(rec_id, saved_name)
                        st.success("Download prepared. If one-time downloads are enabled, file has been removed from server.")

# small admin - optional: show active codes (only local preview / remove before public use)
if st.sidebar.checkbox("Show active codes (admin)", value=False):
    c = conn.cursor()
    c.execute("SELECT id, code, original_name, created_at, expires_at, downloaded FROM files ORDER BY created_at DESC")
    rows = c.fetchall()
    st.sidebar.write("Active entries:")
    for r in rows:
        id_, code, oname, c_at, e_at, dl = r
        st.sidebar.write(f"{code} — {oname} — expires {datetime.utcfromtimestamp(e_at)} — downloaded={dl}")
