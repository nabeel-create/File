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
ADMIN_PASSCODE = "admin123"

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

# =============================
# 💾 DATABASE
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
# 🔧 HELPERS
# =============================
def generate_code(n=CODE_LENGTH):
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(n))

def cleanup_expired():
    now = int(time.time())
    c = conn.cursor()
    c.execute("SELECT id, saved_name FROM files WHERE expires_at <= ?", (now,))
    for _id, saved_name in c.fetchall():
        try: (UPLOAD_FOLDER / saved_name).unlink()
        except: pass
    c.execute("DELETE FROM files WHERE expires_at <= ?", (now,))
    conn.commit()

def save_file(uploaded_file, expiry_hours):
    uploaded_file.seek(0, os.SEEK_END)
    size = uploaded_file.tell()
    uploaded_file.seek(0)
    if size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError(f"File exceeds {MAX_FILE_SIZE_MB} MB")

    code = generate_code()
    c = conn.cursor()
    while c.execute("SELECT 1 FROM files WHERE code=?", (code,)).fetchone(): 
        code = generate_code()

    timestamp = int(time.time())
    expires_at = timestamp + expiry_hours*3600
    saved_name = f"{timestamp}_{secrets.token_hex(8)}_{uploaded_file.name}"
    with open(UPLOAD_FOLDER / saved_name, "wb") as f: f.write(uploaded_file.read())

    c.execute(
        "INSERT INTO files (code, saved_name, original_name, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
        (code, saved_name, uploaded_file.name, timestamp, expires_at)
    )
    conn.commit()
    return code, expires_at

def get_record(code): 
    return conn.cursor().execute("SELECT id, saved_name, original_name, expires_at, downloaded FROM files WHERE code=?", (code,)).fetchone()

def mark_downloaded(rec_id, saved_name, one_time):
    c = conn.cursor()
    c.execute("UPDATE files SET downloaded=1 WHERE id=?", (rec_id,))
    conn.commit()
    if one_time:
        try: (UPLOAD_FOLDER / saved_name).unlink()
        except: pass
        c.execute("DELETE FROM files WHERE id=?", (rec_id,))
        conn.commit()

def get_all_files():
    df = pd.DataFrame(conn.cursor().execute("SELECT id, code, original_name, downloaded, created_at, expires_at FROM files").fetchall(),
                      columns=["ID","Code","File Name","Downloaded","Created At","Expires At"])
    df["Created At"] = df["Created At"].apply(lambda t: datetime.utcfromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S"))
    df["Expires At"] = df["Expires At"].apply(lambda t: datetime.utcfromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S"))
    return df

def delete_file(file_id):
    c = conn.cursor()
    row = c.execute("SELECT saved_name FROM files WHERE id=?", (file_id,)).fetchone()
    if row:
        try: (UPLOAD_FOLDER / row[0]).unlink()
        except: pass
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
.header { text-align:center;padding:1.5rem;font-size:2rem;font-weight:bold;
color:white;background:linear-gradient(90deg,#0072ff,#00c6ff);
border-radius:1rem;box-shadow:0 4px 20px rgba(0,0,0,0.2);margin-bottom:1rem;
animation: glow 2s ease-in-out infinite alternate; }
@keyframes glow { from{ text-shadow:0 0 5px #00c6ff,0 0 10px #0072ff; } to{ text-shadow:0 0 15px #00c6ff,0 0 30px #0072ff; } }
.name{text-align:center;font-size:1.1rem;color:#333;margin-bottom:2rem;font-style:italic;}
.footer{text-align:center;color:#888;font-size:0.9rem;margin-top:3rem;border-top:1px solid #ddd;padding-top:0.8rem;}
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='header'>🔐 Secure File Share Platform</div>", unsafe_allow_html=True)
st.markdown("<div class='name'>✨ Made with ❤️ by <b>Nabeel</b> ✨</div>", unsafe_allow_html=True)

# =============================
# ⚙️ MAIN UI
# =============================
if "one_time_download" not in st.session_state: st.session_state["one_time_download"] = True
if "is_admin" not in st.session_state: st.session_state["is_admin"] = False

# ---- Tabs for Upload/Download ----
tab1, tab2 = st.tabs(["📤 Upload", "📥 Download"])

with tab1:
    st.subheader("Upload File & Generate Code")
    uploaded = st.file_uploader("Select a file", accept_multiple_files=False)
    col1, col2 = st.columns(2)
    with col1: expiry = st.number_input("Expires in hours", 1, 168, 24)
    with col2: one_time = st.checkbox("One-time download", True)
    if st.button("Generate Code"):
        if not uploaded: st.error("Select a file!")
        else:
            code, expires_at = save_file(uploaded, expiry)
            st.session_state["one_time_download"] = one_time
            st.success("✅ File uploaded!")
            st.code(code, language="text")
            st.info(f"Expires on (UTC): {datetime.utcfromtimestamp(expires_at)}")

with tab2:
    st.subheader("Download File by Code")
    code_input = st.text_input("Enter your code")
    if st.button("Download File"):
        if not code_input.strip(): st.error("Enter code!")
        else:
            cleanup_expired()
            rec = get_record(code_input.strip())
            if not rec: st.error("Invalid/expired code")
            else:
                rec_id, saved, orig, expires_at, downloaded = rec
                now = int(time.time())
                if expires_at <= now: st.error("⏳ Code expired")
                elif downloaded: st.error("⚠️ Already downloaded")
                else:
                    with open(UPLOAD_FOLDER / saved, "rb") as f: data=f.read()
                    st.download_button("⬇️ Download File", data=data, file_name=orig)
                    mark_downloaded(rec_id, saved, one_time)
                    st.success("✅ Download ready!")

# ---- Admin in Main Page ----
st.subheader("🛠️ Admin Panel")
password = st.text_input("Enter admin passcode", type="password")
if st.button("Login as Admin"):
    if password == ADMIN_PASSCODE:
        st.session_state["is_admin"] = True
        st.success("Access granted ✅")
    else: st.error("Wrong passcode")

if st.session_state["is_admin"]:
    st.success("Welcome Admin 👑")
    st.dataframe(get_all_files(), use_container_width=True)
    file_id = st.number_input("Enter File ID to delete", min_value=1, step=1)
    if st.button("Delete File"):
        if delete_file(file_id): st.success("Deleted ✅")
        else: st.error("File not found")

st.markdown("<div class='footer'>© 2025 FileShare | Admin Enabled | Created by Nabeel</div>", unsafe_allow_html=True)
