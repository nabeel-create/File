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
    
    # Create table if not exists
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
        except Exception:
            pass
    c.execute("DELETE FROM files WHERE expires_at <= ?", (now,))
    conn.commit()

def save_file(uploaded_file, expiry_seconds, one_time=True, ftype="file"):
    # For Streamlit UploadedFile or Path object
    if hasattr(uploaded_file, "read"):
        uploaded_file.seek(0, os.SEEK_END)
        size = uploaded_file.tell()
        uploaded_file.seek(0)
        if size > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise ValueError(f"File exceeds {MAX_FILE_SIZE_MB} MB limit.")
        file_data = uploaded_file.read()
        orig_name = uploaded_file.name
    else:
        # Path object (for text files)
        file_data = uploaded_file.read_bytes()
        orig_name = uploaded_file.name

    code = generate_code()
    c = conn.cursor()
    while True:
        c.execute("SELECT 1 FROM files WHERE code=?", (code,))
        if c.fetchone() is None:
            break
        code = generate_code()

    timestamp = int(time.time())
    expires_at = timestamp + int(expiry_seconds)
    saved_name = f"{timestamp}_{secrets.token_hex(8)}_{orig_name}"
    dest = UPLOAD_FOLDER / saved_name
    with open(dest, "wb") as f:
        f.write(file_data)

    c.execute(
        "INSERT INTO files (code, saved_name, original_name, created_at, expires_at, one_time, type) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (code, saved_name, orig_name, timestamp, expires_at, int(one_time), ftype)
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
        except Exception:
            pass
        c.execute("DELETE FROM files WHERE id=?", (record_id,))
        conn.commit()

def get_all_files():
    c = conn.cursor()
    c.execute("SELECT id, code, original_name, downloaded, created_at, expires_at, one_time, type FROM files")
    rows = c.fetchall()
    df = pd.DataFrame(rows, columns=["ID", "Code", "File Name", "Downloaded", "Created At", "Expires At", "One-Time", "Type"])
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
.card {
    background: #fff;
    padding: 1rem;
    border-radius: 1rem;
    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    text-align: center;
    margin-bottom: 1rem;
}
.card-title { font-weight: bold; font-size: 1.2rem; }
.card-value { font-size: 1.5rem; color: #0072ff; font-weight: bold; }
.progress { height: 10px; border-radius: 5px; background-color: #e0e0e0; }
.progress-bar { height: 10px; border-radius: 5px; background-color: #0072ff; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='header'>🔐 Secure File/Text Share</div>", unsafe_allow_html=True)
st.markdown("<div class='name'>✨ Made with ❤️ by <b>Nabeel</b> ✨</div>", unsafe_allow_html=True)

# =============================
# ⚙️ MAIN APP (Text/File upload & download)
# =============================
if "one_time_download" not in st.session_state:
    st.session_state["one_time_download"] = True

tab = st.tabs(["📤 Upload", "📥 Download"])

# ---- Upload Tab ----
with tab[0]:
    st.subheader("Upload Text or File & Generate Code")

    upload_type = st.radio("Upload Type", ("Text", "File"))
    one_time = st.checkbox("One-time download (delete after first use)", True)
    
    # Calendar + Time picker
    col1, col2 = st.columns(2)
    with col1:
        expiry_date = st.date_input("Select Expiry Date", value=datetime.today() + timedelta(days=1))
    with col2:
        expiry_time = st.time_input("Select Expiry Time", value=datetime.now().time())

    if upload_type == "Text":
        text_content = st.text_area("Enter your text here")
    else:
        uploaded_files = st.file_uploader("Select files", accept_multiple_files=True)

    if st.button("Generate Code"):
        expiry_dt = datetime.combine(expiry_date, expiry_time)
        expiry_seconds = int((expiry_dt - datetime.utcnow()).total_seconds())
        if expiry_seconds <= 0:
            st.error("Expiry time must be in the future.")
        else:
            if upload_type == "Text":
                if not text_content.strip():
                    st.error("Please enter some text.")
                else:
                    file_path = UPLOAD_FOLDER / f"text_{int(time.time())}.txt"
                    file_path.write_text(text_content, encoding="utf-8")
                    code, expires_at = save_file(file_path.open("rb"), expiry_seconds, one_time, "text")
                    st.success("✅ Text uploaded successfully!")
                    st.write("Your secret code:")
                    st.code(code)
                    st.info(f"⏰ Expires on (UTC): {datetime.utcfromtimestamp(expires_at)}")
            else:
                for uploaded in uploaded_files:
                    code, expires_at = save_file(uploaded, expiry_seconds, one_time, "file")
                    st.success(f"✅ {uploaded.name} uploaded successfully!")
                    st.write("Secret code:")
                    st.code(code)
                    st.info(f"⏰ Expires on (UTC): {datetime.utcfromtimestamp(expires_at)}")

# ---- Download Tab ----
with tab[1]:
    st.subheader("Download Text/File by Code")
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
                rec_id, saved, orig, expires_at, downloaded, one_time_flag, ftype = rec
                now = int(time.time())
                if expires_at <= now:
                    st.error("⏳ Code expired.")
                elif one_time_flag and downloaded:
                    st.error("⚠️ Already downloaded (one-time).")
                else:
                    path = UPLOAD_FOLDER / saved
                    if not path.exists():
                        st.error("File not found.")
                    else:
                        if ftype == "text":
                            text_content = path.read_text(encoding="utf-8")
                            st.text_area("Text Content:", value=text_content, height=200)
                            st.download_button("⬇️ Download Text", text_content, file_name=orig)
                        else:
                            data = path.read_bytes()
                            st.download_button("⬇️ Download File", data, file_name=orig)
                        mark_downloaded_and_maybe_delete(rec_id, saved, one_time_flag)
                        st.success("✅ Download ready!")

# =============================
# ---- Admin Panel in Sidebar ----
# =============================
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

    # Logout button
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
    <div class='card'><div class='card-title'>Total Files</div><div class='card-value'>{total_files}</div></div>
    <div class='card'><div class='card-title'>Active Files</div><div class='card-value'>{active_files}</div></div>
    <div class='card'><div class='card-title'>Expired Files</div><div class='card-value'>{expired_files}</div></div>
    <div class='card'><div class='card-title'>Downloads</div><div class='card-value'>{downloads_count}</div></div>
    """, unsafe_allow_html=True)

    # Table of files
    df = get_all_files()
    st.sidebar.markdown("### 🗂 Uploaded Files")
    st.sidebar.dataframe(df, use_container_width=True)

    # Delete a file
    file_id = st.sidebar.number_input("Enter File ID to Delete", min_value=1, step=1)
    if st.sidebar.button("Delete File"):
        if delete_file(file_id):
            st.sidebar.success("🗑️ File deleted successfully.")
        else:
            st.sidebar.error("File not found.")

# =============================
# 🧾 FOOTER
# =============================
st.markdown("<div class='footer'>© 2025 File/Text Share | Admin Enabled | Created by Nabeel</div>", unsafe_allow_html=True)
