import streamlit as st
import sqlite3
import os
from pathlib import Path
from datetime import datetime, timedelta
import random
import string

# -------------------------------------------------
# CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="Secure File Sharing",
    page_icon="📁",
    layout="wide"
)

UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)

# -------------------------------------------------
# DATABASE SETUP
# -------------------------------------------------
def get_db():
    conn = sqlite3.connect("files.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            filename TEXT,
            saved_name TEXT,
            expires_at TEXT,
            downloaded INTEGER DEFAULT 0,
            one_time INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn

# -------------------------------------------------
# HELPERS
# -------------------------------------------------
def random_code(length=7):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def remove_expired_files():
    conn = get_db()
    c = conn.cursor()
    now = datetime.now()
    c.execute("SELECT id, saved_name, expires_at FROM files")
    rows = c.fetchall()

    for rid, saved, expiry in rows:
        if expiry:
            dt = datetime.fromisoformat(expiry)
            if dt < now:
                try:
                    os.remove(UPLOAD_FOLDER / saved)
                except:
                    pass
                c.execute("DELETE FROM files WHERE id=?", (rid,))
    conn.commit()
    conn.close()

remove_expired_files()

# -------------------------------------------------
# SIDEBAR (ADMIN LOGIN)
# -------------------------------------------------
with st.sidebar:
    st.title("🔐 Admin Panel")

    if "admin" not in st.session_state:
        st.session_state.admin = False

    if not st.session_state.admin:
        admin_user = st.text_input("Username")
        admin_pass = st.text_input("Password", type="password")

        if st.button("Login"):
            if admin_user == "admin" and admin_pass == "123":
                st.session_state.admin = True
                st.success("Login successful!")
            else:
                st.error("Invalid Credentials")

    else:
        st.success("Logged in as Admin")
        if st.button("Logout"):
            st.session_state.admin = False
            st.experimental_rerun()

# -------------------------------------------------
# MAIN UI
# -------------------------------------------------
menu = st.tabs(["📤 Upload", "📥 Download", "🛠 Admin"])

# -------------------------------------------------
# UPLOAD TAB
# -------------------------------------------------
with menu[0]:
    st.header("📤 Secure File Upload")

    uploaded_files = st.file_uploader(
        "Upload Files",
        type=None,
        accept_multiple_files=True
    )

    one_time = st.checkbox("Allow only one-time download")

    expiry_hours = st.number_input(
        "File expiry (hours)",
        min_value=1,
        max_value=48,
        value=24
    )

    if st.button("Upload Files") and uploaded_files:
        conn = get_db()
        c = conn.cursor()

        results = []

        for file in uploaded_files:
            code = random_code()

            timestamp = str(int(datetime.timestamp(datetime.now())))
            saved_name = f"{timestamp}_{random_code(6)}_{file.name}"
            file_path = UPLOAD_FOLDER / saved_name

            with open(file_path, "wb") as f:
                f.write(file.getbuffer())

            expires_dt = datetime.now() + timedelta(hours=int(expiry_hours))

            c.execute("""
                INSERT INTO files (code, filename, saved_name, expires_at, one_time)
                VALUES (?, ?, ?, ?, ?)
            """, (code, file.name, saved_name, expires_dt.isoformat(), int(one_time)))
            conn.commit()

            results.append((file.name, code, expires_dt))

        conn.close()

        st.success("Files uploaded successfully!")

        st.subheader("Generated Download Codes")
        for name, code, exp in results:
            st.write(f"📄 **{name}** — 🔑 Code: `{code}` — ⏳ Expires: {exp}")

# -------------------------------------------------
# DOWNLOAD TAB
# -------------------------------------------------
with menu[1]:
    st.header("📥 Download File")

    input_code = st.text_input("Enter your download code")

    if st.button("Download"):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, saved_name, filename, expires_at, downloaded, one_time FROM files WHERE code=?", (input_code,))
        rec = c.fetchone()
        conn.close()

        if not rec:
            st.error("Invalid code")
        else:
            rec_id, saved, original, expiry, downloaded, one_time = rec

            if datetime.fromisoformat(expiry) < datetime.now():
                st.error("This file has expired.")
            else:
                file_path = UPLOAD_FOLDER / saved
                if not file_path.exists():
                    st.error("File not found")
                else:
                    with open(file_path, "rb") as f:
                        st.download_button(
                            label=f"⬇ Download {original}",
                            data=f.read(),
                            file_name=original,
                            mime="application/octet-stream"
                        )

                    if one_time == 1:
                        try:
                            os.remove(file_path)
                        except:
                            pass

                        conn = get_db()
                        c = conn.cursor()
                        c.execute("DELETE FROM files WHERE id=?", (rec_id,))
                        conn.commit()
                        conn.close()

# -------------------------------------------------
# ADMIN TAB
# -------------------------------------------------
with menu[2]:
    if not st.session_state.admin:
        st.warning("Admin login required.")

    else:
        st.header("🛠 Admin Dashboard")

        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM files")
        total = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM files WHERE expires_at > ?", (datetime.now().isoformat(),))
        active = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM files WHERE expires_at <= ?", (datetime.now().isoformat(),))
        expired = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM files WHERE one_time=1")
        one_time_count = c.fetchone()[0]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Files", total)
        col2.metric("Active Files", active)
        col3.metric("Expired Files", expired)
        col4.metric("One-time Files", one_time_count)

        st.subheader("📄 File Records")

        c.execute("SELECT id, filename, code, expires_at, one_time FROM files")
        rows = c.fetchall()
        conn.close()

        for rid, name, code, exp, one in rows:
            st.write(f"**{name}** — Code: `{code}` — Expires: {exp} — One-time: {bool(one)}")
            if st.button(f"Delete {rid}", key=f"del{rid}"):
                conn = get_db()
                c = conn.cursor()
                c.execute("DELETE FROM files WHERE id=?", (rid,))
                conn.commit()
                conn.close()
                st.success("Deleted successfully!")
                st.experimental_rerun()
