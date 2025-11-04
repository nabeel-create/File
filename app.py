import streamlit as st
import sqlite3
import os
import secrets
import string
import time
from datetime import datetime
from pathlib import Path

# --- CONFIG ---
UPLOAD_FOLDER = Path("uploads")
DB_PATH = "files.db"
CODE_LENGTH = 8
EXPIRY_HOURS = 24
MAX_FILE_SIZE_MB = 50

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

# --- DATABASE ---
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

# --- HELPERS ---
def generate_code(n=CODE_LENGTH):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(n))

def cleanup_expired():
    now = int(time.time())
    c = conn.cursor()
    c.execute("SELECT id, saved_name FROM files WHERE expires_at <= ?", (now,))
    rows = c.fetchall()
    for _id, saved_name in rows:
        try:
            (UPLOAD_FOLDER / saved_name).unlink(missing_ok=True)
        except Exception:
            pass
    c.execute("DELETE FROM files WHERE expires_at <= ?", (now,))
    conn.commit()

def save_file_and_record(uploaded_file, expiry_seconds):
    uploaded_file.seek(0, os.SEEK_END)
    size = uploaded_file.tell()
    uploaded_file.seek(0)
    if size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError(f"File exceeds {MAX_FILE_SIZE_MB} MB limit.")

    code = generate_code()
    c = conn.cursor()
    while True:
        c.execute("SELECT 1 FROM files WHERE code=?", (code,))
        if c.fetchone() is None:
            break
        code = generate_code()

    timestamp = int(time.time())
    expires_at = timestamp + expiry_seconds
    saved_name = f"{timestamp}_{secrets.token_hex(8)}_{uploaded_file.name}"
    dest = UPLOAD_FOLDER / saved_name
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
    return c.fetchone()

def mark_downloaded_and_maybe_delete(record_id, saved_name, one_time):
    c = conn.cursor()
    c.execute("UPDATE files SET downloaded=1 WHERE id=?", (record_id,))
    conn.commit()
    if one_time:
        try:
            (UPLOAD_FOLDER / saved_name).unlink(missing_ok=True)
        except Exception:
            pass
        c.execute("DELETE FROM files WHERE id=?", (record_id,))
        conn.commit()

cleanup_expired()

# --- UI SETUP ---
st.set_page_config(page_title="FileShare", page_icon="🔐", layout="centered")

st.markdown(
    """
    <style>
    .main-title {
        text-align: center;
        font-size: 2.2em;
        color: #00c4ff;
        font-weight: 700;
        margin-bottom: 0.5em;
    }
    .subtitle {
        text-align: center;
        color: gray;
        margin-bottom: 1.5em;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown('<h1 class="main-title">🔐 FileShare Portal</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Securely upload & download files using a secret code</p>', unsafe_allow_html=True)

# --- SESSION STATE INIT ---
if "mode" not in st.session_state:
    st.session_state["mode"] = None
if "one_time_download" not in st.session_state:
    st.session_state["one_time_download"] = True

# --- WELCOME SCREEN ---
if st.session_state["mode"] is None:
    st.write("👋 Welcome! What would you like to do today?")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📤 Upload a File"):
            st.session_state["mode"] = "upload"
            st.rerun()
    with col2:
        if st.button("📥 Download a File"):
            st.session_state["mode"] = "download"
            st.rerun()

# --- UPLOAD SECTION ---
elif st.session_state["mode"] == "upload":
    st.header("📤 Upload File")
    uploaded_file = st.file_uploader("Choose file to upload", accept_multiple_files=False)

    col1, col2 = st.columns(2)
    with col1:
        expiry_hours = st.number_input("Expires in (hours)", min_value=1, max_value=168, value=EXPIRY_HOURS)
    with col2:
        one_time = st.checkbox("One-time download (delete after first use)", value=True)

    if st.button("Generate Code"):
        if uploaded_file is None:
            st.error("Please select a file first.")
        else:
            try:
                code, expires_at = save_file_and_record(uploaded_file, expiry_hours * 3600)
                st.session_state["one_time_download"] = one_time
                exp_dt = datetime.utcfromtimestamp(expires_at)

                st.success("✅ File uploaded successfully!")
                st.write("Your secret code (share this with the downloader):")
                st.code(code, language="text")
                st.write(f"⏰ Expires on (UTC): **{exp_dt}**")
                st.info("Share this code safely — anyone with it can download the file.")
            except Exception as e:
                st.error(f"Upload failed: {e}")

    if st.button("⬅️ Back to Home"):
        st.session_state["mode"] = None
        st.rerun()

# --- DOWNLOAD SECTION ---
elif st.session_state["mode"] == "download":
    st.header("📥 Download File by Code")
    code_input = st.text_input("Enter download code", value="")

    if st.button("Fetch File"):
        if not code_input.strip():
            st.error("Enter a valid code.")
        else:
            cleanup_expired()
            rec = get_record_by_code(code_input.strip())
            if rec is None:
                st.error("❌ Invalid or expired code.")
            else:
                rec_id, saved_name, orig_name, created_at, expires_at, downloaded = rec
                now = int(time.time())
                one_time = st.session_state.get("one_time_download", True)

                if expires_at <= now:
                    st.error("⏳ This code has expired.")
                elif one_time and downloaded:
                    st.error("⚠️ This file was already downloaded (one-time).")
                else:
                    path = UPLOAD_FOLDER / saved_name
                    if not path.exists():
                        st.error("File not found on server (maybe deleted).")
                    else:
                        with open(path, "rb") as f:
                            data = f.read()
                        st.write(f"Original filename: **{orig_name}**")
                        st.download_button("⬇️ Download File", data=data, file_name=orig_name)
                        mark_downloaded_and_maybe_delete(rec_id, saved_name, one_time)
                        st.success("✅ Download ready! (File deleted if one-time mode is active)")

    if st.button("⬅️ Back to Home"):
        st.session_state["mode"] = None
        st.rerun()

# --- ADMIN PANEL (optional) ---
if st.sidebar.checkbox("🛠 Show active codes (Admin)", value=False):
    c = conn.cursor()
    c.execute("SELECT id, code, original_name, created_at, expires_at, downloaded FROM files ORDER BY created_at DESC")
    rows = c.fetchall()
    st.sidebar.write("Active entries:")
    for r in rows:
        id_, code, oname, c_at, e_at, dl = r
        st.sidebar.write(f"{code} — {oname} — Expires {datetime.utcfromtimestamp(e_at)} — downloaded={dl}")
