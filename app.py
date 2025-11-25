import streamlit as st
import sqlite3
import os
import secrets
import string
import time
from datetime import datetime
from pathlib import Path
import pandas as pd

# =============================
# 🌐 CONFIGURATION
# =============================
UPLOAD_FOLDER = Path("uploads")
DB_PATH = "files.db"
CODE_LENGTH = 8
EXPIRY_HOURS = 24
MAX_FILE_SIZE_MB = 50
ADMIN_PASSCODE = "admin123"  # 🔑 change this

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

# =============================
# 💾 DATABASE SETUP
# =============================
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

# =============================
# 🔧 HELPER FUNCTIONS
# =============================
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
            fpath = UPLOAD_FOLDER / saved_name
            if fpath.exists():
                fpath.unlink()
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
    expires_at = timestamp + int(expiry_seconds)  # store as integer
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

def get_all_files():
    c = conn.cursor()
    c.execute("SELECT id, code, original_name, downloaded, created_at, expires_at FROM files")
    rows = c.fetchall()
    df = pd.DataFrame(rows, columns=["ID", "Code", "File Name", "Downloaded", "Created At", "Expires At"])
    df["Created At"] = df["Created At"].apply(lambda t: datetime.utcfromtimestamp(int(t)).strftime('%Y-%m-%d %H:%M:%S'))
    df["Expires At"] = df["Expires At"].apply(lambda t: datetime.utcfromtimestamp(int(t)).strftime('%Y-%m-%d %H:%M:%S'))
    return df

def delete_file(file_id):
    c = conn.cursor()
    c.execute("SELECT saved_name FROM files WHERE id=?", (file_id,))
    row = c.fetchone()
    if row:
        saved_name = row[0]
        fpath = UPLOAD_FOLDER / saved_name
        if fpath.exists():
            fpath.unlink()
        c.execute("DELETE FROM files WHERE id=?", (file_id,))
        conn.commit()
        return True
    return False

cleanup_expired()

# =============================
# 🎨 STYLING
# =============================
st.set_page_config(page_title="File Share by Nabeel", layout="centered")
st.markdown("""
<style>
body { background-color: #f5f7fa; }
.header {
    text-align: center;
    padding: 1.5rem;
    font-size: 2rem;
    font-weight: bold;
    font-family: 'Poppins', sans-serif;
    color: white;
    background: linear-gradient(90deg, #0072ff, #00c6ff);
    border-radius: 1rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    margin-bottom: 1rem;
    animation: glow 2s ease-in-out infinite alternate;
}
@keyframes glow {
  from { text-shadow: 0 0 5px #00c6ff, 0 0 10px #0072ff; }
  to { text-shadow: 0 0 15px #00c6ff, 0 0 30px #0072ff; }
}
.name {
    text-align: center;
    font-family: 'Poppins', sans-serif;
    font-size: 1.1rem;
    color: #333;
    margin-bottom: 2rem;
    font-style: italic;
}
.footer {
    text-align: center;
    font-family: 'Poppins', sans-serif;
    color: #888;
    font-size: 0.9rem;
    margin-top: 3rem;
    border-top: 1px solid #ddd;
    padding-top: 0.8rem;
}
</style>
""", unsafe_allow_html=True)

# =============================
# 🧭 HEADER
# =============================
st.markdown("<div class='header'>🔐 Secure File Share Platform</div>", unsafe_allow_html=True)
st.markdown("<div class='name'>✨ Made with ❤️ by <b>Nabeel</b> ✨</div>", unsafe_allow_html=True)

# =============================
# ⚙️ MAIN APP
# =============================
if "one_time_download" not in st.session_state:
    st.session_state["one_time_download"] = True

mode = st.sidebar.radio("Navigation", ("📤 Upload", "📥 Download", "🛠️ Admin Panel"))

# ---- Upload ----
if mode == "📤 Upload":
    st.subheader("Upload File & Generate Code")
    uploaded = st.file_uploader("Select a file", accept_multiple_files=False)

    col1, col2 = st.columns(2)
    with col1:
        expiry = st.number_input("Expires in (hours)", 1, 168, EXPIRY_HOURS)
    with col2:
        one_time = st.checkbox("One-time download (delete after first use)", True)

    if st.button("Generate Code"):
        if not uploaded:
            st.error("Please select a file.")
        else:
            try:
                expiry_seconds = int(expiry * 3600)
                code, expires_at = save_file(uploaded, expiry_seconds)
                st.session_state["one_time_download"] = one_time
                st.success("✅ File uploaded successfully!")
                st.write("Your secret code:")
                st.code(code, language="text")
                st.info(f"⏰ Expires on (UTC): **{datetime.utcfromtimestamp(expires_at)}**")
            except Exception as e:
                st.error(str(e))

# ---- Download ----
elif mode == "📥 Download":
    st.subheader("Download File by Code")
    code_input = st.text_input("Enter your code")

    if st.button("Download File"):
        if not code_input.strip():
            st.error("Please enter a valid code.")
        else:
            cleanup_expired()
            rec = get_record_by_code(code_input.strip())
            if not rec:
                st.error("❌ Invalid or expired code.")
            else:
                rec_id, saved, orig, expires_at, downloaded = rec
                now = int(time.time())
                if expires_at <= now:
                    st.error("⏳ Code expired.")
                elif downloaded:
                    st.error("⚠️ File already downloaded (one-time).")
                else:
                    path = UPLOAD_FOLDER / saved
                    if not path.exists():
                        st.error("File not found.")
                    else:
                        with open(path, "rb") as f:
                            data = f.read()
                        st.download_button("⬇️ Download File", data=data, file_name=orig)
                        mark_downloaded_and_maybe_delete(rec_id, saved, one_time=True)
                        st.success("✅ Download ready!")

# ---- Admin ----
elif mode == "🛠️ Admin Panel":
    st.subheader("Admin Login")
    password = st.text_input("Enter admin passcode", type="password")
    if st.button("Login"):
        if password == ADMIN_PASSCODE:
            st.session_state["is_admin"] = True
            st.success("Access granted ✅")
        else:
            st.error("Wrong passcode.")

    if st.session_state.get("is_admin", False):
        st.success("Welcome Admin 👑")
        df = get_all_files()
        st.dataframe(df, use_container_width=True)

        file_id = st.number_input("Enter File ID to Delete", min_value=1, step=1)
        if st.button("Delete File"):
            if delete_file(file_id):
                st.success("🗑️ File deleted successfully.")
            else:
                st.error("File not found.")

# =============================
# 🧾 FOOTER
# =============================
st.markdown("<div class='footer'>© 2025 FileShare | Admin Enabled | Created by Nabeel</div>", unsafe_allow_html=True)
