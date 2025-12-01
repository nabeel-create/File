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
ADMIN_PASSCODE = "admin123"  # 🔑 Change this for security!

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

# =============================
# 💾 DATABASE SETUP
# =============================
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    
    # Create table if not exists
    c.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            saved_name TEXT,
            original_name TEXT,
            text_content TEXT,
            created_at INTEGER,
            expires_at INTEGER,
            downloaded INTEGER DEFAULT 0,
            one_time INTEGER DEFAULT 1,
            type TEXT DEFAULT 'file'
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
    c.execute("SELECT id, saved_name, type FROM files WHERE expires_at <= ?", (now,))
    rows = c.fetchall()
    for _id, saved_name, ftype in rows:
        if ftype == 'file':
            try:
                fpath = UPLOAD_FOLDER / saved_name
                if fpath.exists():
                    fpath.unlink()
            except Exception:
                pass
    c.execute("DELETE FROM files WHERE expires_at <= ?", (now,))
    conn.commit()

def save_file(uploaded_file, expiry_seconds, one_time=True):
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
    expires_at = timestamp + int(expiry_seconds)
    saved_name = f"{timestamp}_{secrets.token_hex(8)}_{uploaded_file.name}"
    dest = UPLOAD_FOLDER / saved_name
    with open(dest, "wb") as f:
        f.write(uploaded_file.read())
    
    c.execute(
        "INSERT INTO files (code, saved_name, original_name, created_at, expires_at, one_time, type) VALUES (?, ?, ?, ?, ?, ?, 'file')",
        (code, saved_name, uploaded_file.name, timestamp, expires_at, int(one_time))
    )
    conn.commit()
    return code, expires_at

def save_text(text_content, expiry_seconds, one_time=True):
    code = generate_code()
    c = conn.cursor()
    while True:
        c.execute("SELECT 1 FROM files WHERE code=?", (code,))
        if c.fetchone() is None:
            break
        code = generate_code()
    timestamp = int(time.time())
    expires_at = timestamp + int(expiry_seconds)
    c.execute(
        "INSERT INTO files (code, text_content, created_at, expires_at, one_time, type) VALUES (?, ?, ?, ?, ?, 'text')",
        (code, text_content, timestamp, expires_at, int(one_time))
    )
    conn.commit()
    return code, expires_at

def get_record_by_code(code):
    c = conn.cursor()
    c.execute("SELECT id, saved_name, original_name, text_content, expires_at, downloaded, one_time, type FROM files WHERE code=?", (code,))
    return c.fetchone()

def mark_downloaded_and_maybe_delete(record_id, saved_name, one_time, ftype):
    c = conn.cursor()
    c.execute("UPDATE files SET downloaded=1 WHERE id=?", (record_id,))
    conn.commit()
    if one_time:
        if ftype == 'file':
            try:
                (UPLOAD_FOLDER / saved_name).unlink(missing_ok=True)
            except Exception:
                pass
        c.execute("DELETE FROM files WHERE id=?", (record_id,))
        conn.commit()

def get_all_files():
    c = conn.cursor()
    c.execute("SELECT id, code, original_name, downloaded, created_at, expires_at, one_time, type FROM files")
    rows = c.fetchall()
    df = pd.DataFrame(rows, columns=["ID", "Code", "File Name / Text Preview", "Downloaded", "Created At", "Expires At", "One-Time", "Type"])
    df["Created At"] = df["Created At"].apply(lambda t: datetime.utcfromtimestamp(int(t)).strftime('%Y-%m-%d %H:%M:%S'))
    df["Expires At"] = df["Expires At"].apply(lambda t: datetime.utcfromtimestamp(int(t)).strftime('%Y-%m-%d %H:%M:%S'))
    df["One-Time"] = df["One-Time"].apply(lambda x: "Yes" if x else "No")
    df["File Name / Text Preview"] = df.apply(lambda r: r["File Name / Text Preview"][:20]+"..." if r["Type"]=="text" and r["File Name / Text Preview"] else r["File Name / Text Preview"], axis=1)
    return df

def delete_file(file_id):
    c = conn.cursor()
    c.execute("SELECT saved_name, type FROM files WHERE id=?", (file_id,))
    row = c.fetchone()
    if row:
        saved_name, ftype = row
        if ftype == 'file':
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
st.set_page_config(page_title="File/Text Share by Nabeel", layout="wide")
st.markdown("""
<style>
body { background-color: #f5f7fa; }
.header { text-align: center; padding:1.5rem; font-size:2rem; font-weight:bold;
color:white; background: linear-gradient(90deg,#0072ff,#00c6ff); border-radius:1rem;
box-shadow:0 4px 20px rgba(0,0,0,0.2); margin-bottom:1rem; animation:glow 2s ease-in-out infinite alternate;}
@keyframes glow {from { text-shadow: 0 0 5px #00c6ff,0 0 10px #0072ff; } to { text-shadow:0 0 15px #00c6ff,0 0 30px #0072ff; }}
.name { text-align:center; font-family:'Poppins',sans-serif; font-size:1.1rem; color:#333; margin-bottom:2rem; font-style:italic;}
.footer { text-align:center; font-family:'Poppins',sans-serif; color:#888; font-size:0.9rem; margin-top:3rem; border-top:1px solid #ddd; padding-top:0.8rem; }
.card { background:#fff; padding:1rem; border-radius:1rem; box-shadow:0 4px 15px rgba(0,0,0,0.1); text-align:center; margin-bottom:1rem; }
.card-title { font-weight:bold; font-size:1.2rem; }
.card-value { font-size:1.5rem; color:#0072ff; font-weight:bold; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='header'>🔐 Secure File/Text Share Platform</div>", unsafe_allow_html=True)
st.markdown("<div class='name'>✨ Made with ❤️ by <b>Nabeel</b> ✨</div>", unsafe_allow_html=True)

# =============================
# ⚙️ MAIN APP
# =============================
if "one_time_download" not in st.session_state:
    st.session_state["one_time_download"] = True

tabs = st.tabs(["📤 Upload File", "✍️ Upload Text", "📥 Download"])

# ---------------- Upload File ----------------
with tabs[0]:
    st.subheader("Upload File & Generate Code")
    uploaded = st.file_uploader("Select file", accept_multiple_files=False)
    col1, col2 = st.columns(2)
    with col1:
        expiry = st.number_input("Expires in (hours)", 1, 168, EXPIRY_HOURS)
    with col2:
        one_time = st.checkbox("One-time download (delete after first use)", True)

    if st.button("Generate File Code"):
        if not uploaded:
            st.error("Please select a file.")
        else:
            try:
                expiry_seconds = int(expiry*3600)
                code, expires_at = save_file(uploaded, expiry_seconds, one_time)
                st.session_state["one_time_download"] = one_time
                st.success("✅ File uploaded successfully!")
                st.write("Your secret code:")
                st.code(code, language="text")
                st.info(f"⏰ Expires on (UTC): **{datetime.utcfromtimestamp(expires_at)}**")
            except Exception as e:
                st.error(str(e))

# ---------------- Upload Text ----------------
with tabs[1]:
    st.subheader("Upload Text & Generate Code")
    text_input = st.text_area("Enter your text here")
    col1, col2 = st.columns(2)
    with col1:
        expiry_text = st.number_input("Expires in (hours)", 1, 168, EXPIRY_HOURS, key="text_expiry")
    with col2:
        one_time_text = st.checkbox("One-time download (delete after first use)", True, key="text_one_time")

    if st.button("Generate Text Code"):
        if not text_input.strip():
            st.error("Please enter some text.")
        else:
            try:
                expiry_seconds = int(expiry_text*3600)
                code, expires_at = save_text(text_input, expiry_seconds, one_time_text)
                st.session_state["one_time_download"] = one_time_text
                st.success("✅ Text uploaded successfully!")
                st.write("Your secret code:")
                st.code(code, language="text")
                st.info(f"⏰ Expires on (UTC): **{datetime.utcfromtimestamp(expires_at)}**")
            except Exception as e:
                st.error(str(e))

# ---------------- Download ----------------
with tabs[2]:
    st.subheader("Download File or Text by Code")
    code_input = st.text_input("Enter your code to download", key="download_code")
    if st.button("Fetch & Download"):
        if not code_input.strip():
            st.error("Please enter a valid code.")
        else:
            cleanup_expired()
            rec = get_record_by_code(code_input.strip())
            if not rec:
                st.error("❌ Invalid or expired code.")
            else:
                rec_id, saved_name, orig_name, text_content, expires_at, downloaded, one_time_flag, ftype = rec
                now = int(time.time())
                one_time_flag = bool(one_time_flag)
                if expires_at <= now:
                    st.error("⏳ Code expired.")
                elif one_time_flag and downloaded:
                    st.error("⚠️ Already downloaded (one-time).")
                else:
                    if ftype == 'file':
                        path = UPLOAD_FOLDER / saved_name
                        if not path.exists():
                            st.error("File not found.")
                        else:
                            with open(path,"rb") as f:
                                data = f.read()
                            st.download_button("⬇️ Download File", data=data, file_name=orig_name)
                            st.success("✅ Download ready!")
                            mark_downloaded_and_maybe_delete(rec_id, saved_name, one_time_flag, ftype)
                    elif ftype == 'text':
                        st.text_area("📄 Text Content", value=text_content, height=250)
                        st.download_button("⬇️ Download as .txt", data=text_content, file_name=f"{code}.txt")
                        st.success("✅ Text ready!")
                        mark_downloaded_and_maybe_delete(rec_id, saved_name, one_time_flag, ftype)

# ---------------- Admin Panel Sidebar ----------------
st.sidebar.subheader("🛠️ Admin Panel")
if "is_admin" not in st.session_state:
    st.session_state["is_admin"] = False

if not st.session_state["is_admin"]:
    password = st.sidebar.text_input("Enter admin passcode", type="password")
    if st.sidebar.button("Login as Admin"):
        if password == ADMIN_PASSCODE:
            st.session_state["is_admin"] = True
            st.sidebar.success("Access granted ✅")
        else:
            st.sidebar.error("Wrong passcode.")

if st.session_state["is_admin"]:
    st.sidebar.success("Welcome Admin 👑")
    if st.sidebar.button("Logout"):
        st.session_state["is_admin"] = False
        st.sidebar.info("Logged out successfully.")
    
    # Dashboard metrics
    c = conn.cursor()
    now = int(time.time())
    c.execute("SELECT COUNT(*) FROM files")
    total_files = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM files WHERE expires_at > ?", (now,))
    active_files = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM files WHERE expires_at <= ?", (now,))
    expired_files = c.fetchone()[0]
    c.execute("SELECT SUM(downloaded) FROM files")
    downloads_count = c.fetchone()[0] or 0

    st.sidebar.markdown("### 📊 Dashboard")
    st.sidebar.markdown(f"""
    <div class='card'><div class='card-title'>Total Files/Text</div><div class='card-value'>{total_files}</div></div>
    <div class='card'><div class='card-title'>Active</div><div class='card-value'>{active_files}</div></div>
    <div class='card'><div class='card-title'>Expired</div><div class='card-value'>{expired_files}</div></div>
    <div class='card'><div class='card-title'>Downloads</div><div class='card-value'>{downloads_count}</div></div>
    """, unsafe_allow_html=True)

    df = get_all_files()
    st.sidebar.markdown("### 🗂 Uploaded Files/Text")
    st.sidebar.dataframe(df, use_container_width=True)
    
    file_id = st.sidebar.number_input("Enter File/Text ID to Delete", min_value=1, step=1)
    if st.sidebar.button("Delete"):
        if delete_file(file_id):
            st.sidebar.success("🗑️ Deleted successfully")
        else:
            st.sidebar.error("File/Text not found")

# ---------------- Footer ----------------
st.markdown("<div class='footer'>© 2025 File/Text Share | Admin Enabled | Made by Nabeel</div>", unsafe_allow_html=True)
