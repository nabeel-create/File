import streamlit as st
import sqlite3
import os
import secrets
import string
import time
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

# =============================
# 🌐 CONFIGURATION
# =============================
UPLOAD_FOLDER = Path("uploads")
DB_PATH = "files.db"
CODE_LENGTH = 8
MAX_FILE_SIZE_MB = 50
ADMIN_PASSCODE = "admin123"

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
    c.execute("SELECT id, saved_name FROM files WHERE expires_at <= ?", (now,))
    rows = c.fetchall()
    for _id, saved_name in rows:
        try:
            fpath = UPLOAD_FOLDER / saved_name
            if fpath.exists():
                fpath.unlink()
        except:
            pass
    c.execute("DELETE FROM files WHERE expires_at <= ?", (now,))
    conn.commit()

def save_file(uploaded_file, expiry_seconds, one_time=True, file_type="file"):
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

    # Safe filename for text uploads
    original_name = getattr(uploaded_file, "original_name", uploaded_file.name)
    saved_name = f"{timestamp}_{secrets.token_hex(8)}_{original_name}"

    dest = UPLOAD_FOLDER / saved_name
    with open(dest, "wb") as f:
        f.write(uploaded_file.read())

    c.execute(
        "INSERT INTO files (code, saved_name, original_name, created_at, expires_at, one_time, type) 
         VALUES (?, ?, ?, ?, ?, ?, ?)",
        (code, saved_name, original_name, timestamp, expires_at, int(one_time), file_type)
    )
    conn.commit()
    return code, expires_at

def get_record_by_code(code):
    c = conn.cursor()
    c.execute("SELECT id, saved_name, original_name, expires_at, downloaded, one_time, type FROM files WHERE code=?", (code,))
    return c.fetchone()

def mark_downloaded_and_maybe_delete(record_id, saved_name, one_time):
    c = conn.cursor()
    c.execute("UPDATE files SET downloaded=1 WHERE id=?", (record_id,))
    conn.commit()
    if one_time:
        try:
            (UPLOAD_FOLDER / saved_name).unlink(missing_ok=True)
        except:
            pass
        c.execute("DELETE FROM files WHERE id=?", (record_id,))
        conn.commit()

def get_all_files():
    c = conn.cursor()
    c.execute("SELECT id, code, original_name, downloaded, created_at, expires_at, one_time, type FROM files")
    rows = c.fetchall()
    df = pd.DataFrame(rows, columns=["ID","Code","File Name","Downloaded","Created At","Expires At","One-Time","Type"])
    df["Created At"] = df["Created At"].apply(lambda t: datetime.utcfromtimestamp(int(t)).strftime('%Y-%m-%d %H:%M:%S'))
    df["Expires At"] = df["Expires At"].apply(lambda t: datetime.utcfromtimestamp(int(t)).strftime('%Y-%m-%d %H:%M:%S'))
    df["One-Time"] = df["One-Time"].apply(lambda x: "Yes" if x else "No")
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
st.set_page_config(page_title="File/Text Share by Nabeel", layout="centered")
st.markdown("""
<style>
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
}
.name { text-align: center; font-family: 'Poppins', sans-serif; font-size:1.1rem; color:#333; margin-bottom:2rem; font-style:italic;}
.footer { text-align:center; font-family:'Poppins',sans-serif; color:#888; font-size:0.9rem; margin-top:3rem; border-top:1px solid #ddd; padding-top:0.8rem; }
.card { background:#fff; padding:1rem; border-radius:1rem; box-shadow:0 4px 15px rgba(0,0,0,0.1); text-align:center; margin-bottom:1rem; }
.card-title { font-weight:bold; font-size:1.2rem; }
.card-value { font-size:1.5rem; color:#0072ff; font-weight:bold; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='header'>🔐 Secure File/Text Share</div>", unsafe_allow_html=True)
st.markdown("<div class='name'>✨ Made with ❤️ by <b>Nabeel</b> ✨</div>", unsafe_allow_html=True)

# =============================
# ⚙️ UPLOAD & DOWNLOAD
# =============================
tab = st.tabs(["📤 Upload", "📥 Download"])

# ----- UPLOAD -----
with tab[0]:
    st.subheader("Upload File or Text")
    upload_type = st.radio("Choose type", ["File", "Text"])
    uploaded_file = None
    file_type = "file"

    if upload_type == "File":
        uploaded_file = st.file_uploader("Select a file", accept_multiple_files=False)
    else:
        text_content = st.text_area("Enter your text")
        if text_content.strip():
            fname = f"text_{int(time.time())}.txt"
            path = UPLOAD_FOLDER / fname
            
            with open(path, "w", encoding="utf-8") as f:
                f.write(text_content)

            uploaded_file = open(path, "rb")
            uploaded_file.original_name = fname
            file_type = "text"

    # Calendar + AM/PM picker
    st.markdown("**Select Expiry Date & Time**")
    expiry_date = st.date_input("Expiry Date", value=datetime.today() + timedelta(days=1))

    col1, col2, col3 = st.columns([1,1,1])
    with col1: hour = st.selectbox("Hour", list(range(1,13)))
    with col2: minute = st.selectbox("Minute", list(range(0,60)))
    with col3: am_pm = st.selectbox("AM/PM", ["AM","PM"])

    # Convert
    if am_pm=="PM" and hour!=12: hour+=12
    if am_pm=="AM" and hour==12: hour=0

    expiry_dt = datetime.combine(expiry_date, datetime.min.time()) + timedelta(hours=hour, minutes=minute)
    expiry_seconds = int((expiry_dt - datetime.utcnow()).total_seconds())

    one_time = st.checkbox("One-time download (delete after first use)", True)

    if st.button("Generate Code"):
        if not uploaded_file:
            st.error("Please select a file or enter text.")
        else:
            code, expires_at = save_file(uploaded_file, expiry_seconds, one_time, file_type)
            st.success("✅ Uploaded successfully!")
            st.code(code)

# ----- DOWNLOAD -----
with tab[1]:
    st.subheader("Download File or Text by Code")
    code_input = st.text_input("Enter your code")

    if st.button("Download File/Text"):
        if not code_input.strip():
            st.error("Please enter a valid code.")
        else:
            cleanup_expired()
            rec = get_record_by_code(code_input.strip())

            if not rec:
                st.error("❌ Invalid or expired code.")
            else:
                rec_id, saved, orig, expires_at, downloaded, one_time_flag, file_type = rec
                path = UPLOAD_FOLDER / saved

                if not path.exists():
                    st.error("File not found.")
                else:
                    with open(path, "rb") as f:
                        data = f.read()

                    if file_type == "text":
                        st.text(data.decode("utf-8"))

                    st.download_button("⬇️ Download", data=data, file_name=orig)
                    mark_downloaded_and_maybe_delete(rec_id, saved, one_time_flag)

# =============================
# ---- Admin Panel ----
# =============================
st.sidebar.subheader("🛠️ Admin Panel")
if "is_admin" not in st.session_state:
    st.session_state["is_admin"] = False

if not st.session_state["is_admin"]:
    password = st.sidebar.text_input("Admin Passcode", type="password")
    if st.sidebar.button("Login"):
        if password == ADMIN_PASSCODE:
            st.session_state["is_admin"] = True
            st.sidebar.success("Access granted")
        else:
            st.sidebar.error("Wrong passcode")

if st.session_state["is_admin"]:
    st.sidebar.success("Admin Logged In")
    if st.sidebar.button("Logout"):
        st.session_state["is_admin"] = False

    c = conn.cursor()
    now = int(time.time())
    total = c.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    active = c.execute("SELECT COUNT(*) FROM files WHERE expires_at>?", (now,)).fetchone()[0]
    expired = c.execute("SELECT COUNT(*) FROM files WHERE expires_at<=?", (now,)).fetchone()[0]
    downloads = c.execute("SELECT SUM(downloaded) FROM files").fetchone()[0] or 0

    st.sidebar.markdown("### 📊 Dashboard")
    st.sidebar.markdown(f"""
    <div class='card'><div class='card-title'>Total Files</div><div class='card-value'>{total}</div></div>
    <div class='card'><div class='card-title'>Active Files</div><div class='card-value'>{active}</div></div>
    <div class='card'><div class='card-title'>Expired Files</div><div class='card-value'>{expired}</div></div>
    <div class='card'><div class='card-title'>Downloads</div><div class='card-value'>{downloads}</div></div>
    """, unsafe_allow_html=True)

    st.sidebar.markdown("### 🗂 Uploaded Files")
    st.sidebar.dataframe(get_all_files(), use_container_width=True)

    file_id = st.sidebar.number_input("Enter File ID to delete", min_value=1)
    if st.sidebar.button("Delete File"):
        if delete_file(file_id):
            st.sidebar.success("Deleted successfully")
        else:
            st.sidebar.error("Not found")

# =============================
# 🧾 FOOTER
# =============================
st.markdown("<div class='footer'>© 2025 File/Text Share | Created by Nabeel</div>", unsafe_allow_html=True)
