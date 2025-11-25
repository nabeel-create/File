# ======================================================
# 📁 Nabeel Advanced File Share System
# Admin Panel + QR + Multi Upload + Logs + Dark Mode
# ======================================================

import streamlit as st
import sqlite3
import random
import string
import time
import os
import qrcode
from io import BytesIO

# -----------------------------
# CONFIG
# -----------------------------
ADMIN_PASSWORD = "nabeel123"
DB = "files.db"

st.set_page_config(page_title="Nabeel File Share", layout="centered")

# Dark Mode Toggle
dark_mode = st.sidebar.checkbox("🌙 Dark Mode")

if dark_mode:
    st.markdown("""
        <style>
        body { background-color: #111 !important; color: #eee !important; }
        .stButton>button { background-color: #444 !important; color: white !important; }
        </style>
    """, unsafe_allow_html=True)


# -----------------------------
# DATABASE INIT
# -----------------------------
conn = sqlite3.connect(DB)
c = conn.cursor()

c.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        saved_name TEXT,
        original_name TEXT,
        created_at INTEGER,
        expires_at INTEGER,
        downloaded INTEGER DEFAULT 0,
        one_time INTEGER DEFAULT 1
    )
""")

c.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT,
        action TEXT,
        timestamp INTEGER
    )
""")

conn.commit()
conn.close()


# -----------------------------
# HELPERS
# -----------------------------
def generate_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def add_log(code, action):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO logs (code, action, timestamp) VALUES (?, ?, ?)",
              (code, action, int(time.time())))
    conn.commit()
    conn.close()


def save_file(uploaded_file, expiry_seconds, one_time_flag):
    timestamp = int(time.time())
    code = generate_code()
    saved_name = f"{timestamp}_{uploaded_file.name}"

    with open(saved_name, "wb") as f:
        f.write(uploaded_file.getbuffer())

    expires_at = timestamp + expiry_seconds

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(
        "INSERT INTO files (code, saved_name, original_name, created_at, expires_at, one_time) VALUES (?, ?, ?, ?, ?, ?)",
        (code, saved_name, uploaded_file.name, timestamp, expires_at, 1 if one_time_flag else 0)
    )
    conn.commit()
    conn.close()

    add_log(code, "UPLOAD")

    return code, expires_at, saved_name


def get_record(code):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, saved_name, original_name, expires_at, downloaded, one_time FROM files WHERE code=?", (code,))
    row = c.fetchone()
    conn.close()
    return row


def mark_download(id, saved_name, is_one_time, code):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE files SET downloaded=1 WHERE id=?", (id,))

    if is_one_time:
        try: os.remove(saved_name)
        except: pass
        c.execute("DELETE FROM files WHERE id=?", (id,))

    conn.commit()
    conn.close()

    add_log(code, "DOWNLOAD")


def generate_qr(text):
    img = qrcode.make(text)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# -----------------------------
# HEADER
# -----------------------------
st.markdown("<h1 style='text-align:center;'>📁 Nabeel Advanced File Sharing</h1>", unsafe_allow_html=True)


# -----------------------------
# ADMIN LOGIN
# -----------------------------
st.sidebar.markdown("### 🔐 Admin Login")

if "admin" not in st.session_state:
    st.session_state.admin = False

admin_input = st.sidebar.text_input("Enter Admin Password", type="password")

if st.sidebar.button("Login"):
    if admin_input == ADMIN_PASSWORD:
        st.session_state.admin = True
        st.sidebar.success("Admin Logged In!")
    else:
        st.sidebar.error("Wrong Password!")


# ----------------------------------------------------
# 📤 UPLOAD SECTION
# ----------------------------------------------------
st.subheader("📤 Upload Files")

uploaded_files = st.file_uploader("Select multiple files", accept_multiple_files=True)

expiry = st.number_input("Expiry (Hours)", 1, 168, 12)
one_time = st.checkbox("One-Time Download", True)

if uploaded_files and st.button("Upload Files"):
    st.write("### Generated Codes:")

    for file in uploaded_files:
        code, expires_at, saved_file = save_file(file, expiry * 3600, one_time)

        st.success(f"File: {file.name}")
        st.code(code)

        # QR Code
        qr_data = f"Code: {code}"
        qr_img = generate_qr(code)
        st.image(qr_img, width=150)

        st.write(f"⏳ Expires: {time.ctime(expires_at)}")
        st.markdown("---")


# ----------------------------------------------------
# 📥 DOWNLOAD SECTION
# ----------------------------------------------------
st.subheader("📥 Download File")

code_input = st.text_input("Enter Code")

if st.button("Download"):
    rec = get_record(code_input.upper())

    if not rec:
        st.error("❌ Invalid or expired code")
    else:
        file_id, saved, original, expires_at, downloaded, one_time_flag = rec
        now = int(time.time())

        if now > expires_at:
            st.error("⛔ File expired")
        elif downloaded and one_time_flag == 1:
            st.error("⛔ One-time file already downloaded")
        else:
            with open(saved, "rb") as f:
                st.download_button("⬇ Download", f, file_name=original)

            mark_download(file_id, saved, one_time_flag == 1, code_input.upper())
            st.success("✔ Download successful!")


# ----------------------------------------------------
# 🛠️ ADMIN PANEL
# ----------------------------------------------------
if st.session_state.admin:
    st.markdown("## 🛠️ Admin Panel")

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    st.markdown("### 📄 All Stored Files")
    files = c.execute("SELECT code, original_name, created_at, expires_at, downloaded FROM files").fetchall()

    if len(files) == 0:
        st.info("No files stored.")
    else:
        for f in files:
            st.write(f"**Code:** {f[0]} | **File:** {f[1]} | **Downloaded:** {f[4]}")
            st.write(f"Created: {time.ctime(f[2])} | Expires: {time.ctime(f[3])}")
            st.markdown("---")

    st.markdown("### 📜 Usage Logs")
    logs = c.execute("SELECT code, action, timestamp FROM logs ORDER BY id DESC").fetchall()

    for lg in logs:
        st.write(f"➡ **{lg[1]}** | Code: {lg[0]} | Time: {time.ctime(lg[2])}")

    conn.close()
