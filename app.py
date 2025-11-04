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

# --- DB ---
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

# --- Helpers ---
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
            path = UPLOAD_FOLDER / saved_name
            if path.exists():
                path.unlink()
        except Exception:
            pass
    c.execute("DELETE FROM files WHERE expires_at <= ?", (now,))
    conn.commit()

def save_file(uploaded_file, expiry_seconds):
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
    c.execute("SELECT id, saved_name, original_name, expires_at, downloaded FROM files WHERE code=?", (code,))
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

# --- STYLING ---
st.set_page_config(page_title="File Share by Nabeel", layout="centered")

st.markdown("""
<style>
/* Beautiful gradient header */
.header {
    font-family: 'Poppins', sans-serif;
    text-align: center;
    background: linear-gradient(90deg, #00C9FF, #92FE9D);
    padding: 1.2rem;
    border-radius: 1rem;
    color: black;
    font-size: 1.8rem;
    font-weight: 600;
    box-shadow: 0 0 25px rgba(0,0,0,0.15);
}

/* Glowing name "By Nabeel" */

@keyframes glow {
    from { text-shadow: 0 0 5px #00e1ff; }
    to { text-shadow: 0 0 25px #00e1ff, 0 0 50px #00e1ff; }
}

/* Footer style */
.footer {
    position: fixed;
    left: 0;
    bottom: 0;
    width: 100%;
    text-align: center;
    font-family: 'Poppins', sans-serif;
    color: gray;
    font-size: 0.9rem;
    padding: 0.4rem;
    background: rgba(240, 240, 240, 0.6);
    backdrop-filter: blur(4px);
}
</style>
""", unsafe_allow_html=True)

# --- HEADER ---
st.markdown("<div class='header'>🔐 Secure File Share Platform</div>", unsafe_allow_html=True)
st.markdown("<div class='name'>✨ Made with ❤️ by Nabeel ✨</div>", unsafe_allow_html=True)
st.write("")

# --- APP BODY ---
if "one_time_download" not in st.session_state:
    st.session_state["one_time_download"] = True

mode = st.radio("Choose action", ("Upload & generate code", "Enter code to download"))

if mode == "Upload & generate code":
    st.header("📤 Upload File")
    uploaded = st.file_uploader("Select a file to upload", accept_multiple_files=False)

    col1, col2 = st.columns(2)
    with col1:
        expiry = st.number_input("Expires in (hours)", 1, 168, EXPIRY_HOURS)
    with col2:
        one_time = st.checkbox("One-time download (delete after first use)", True)

    if st.button("Generate Code"):
        if not uploaded:
            st.error("Please select a file first.")
        else:
            try:
                code, expires_at = save_file(uploaded, expiry * 3600)
                exp_dt = datetime.utcfromtimestamp(expires_at)
                st.session_state["one_time_download"] = one_time

                st.success("✅ File uploaded successfully!")
                st.write("Your secret code:")
                st.code(code, language="text")
                st.write(f"⏰ Expires on (UTC): **{exp_dt}**")
            except Exception as e:
                st.error(str(e))

else:
    st.header("📥 Download File")
    code_input = st.text_input("Enter your code")

    if st.button("Download"):
        if not code_input.strip():
            st.error("Enter a valid code.")
        else:
            cleanup_expired()
            rec = get_record_by_code(code_input.strip())
            if not rec:
                st.error("❌ Invalid or expired code.")
            else:
                rec_id, saved, orig, expires_at, downloaded = rec
                now = int(time.time())
                one_time = st.session_state["one_time_download"]
                if expires_at <= now:
                    st.error("⏳ Code expired.")
                elif one_time and downloaded:
                    st.error("⚠️ File already downloaded (one-time use).")
                else:
                    path = UPLOAD_FOLDER / saved
                    if not path.exists():
                        st.error("File not found.")
                    else:
                        with open(path, "rb") as f:
                            data = f.read()
                        st.download_button("⬇️ Download File", data=data, file_name=orig)
                        mark_downloaded_and_maybe_delete(rec_id, saved, one_time)
                        st.success("✅ Download ready!")

# --- FOOTER ---
st.markdown("<div class='footer'>© 2025 FileShare | Created by <b>Nabeel</b></div>", unsafe_allow_html=True)

