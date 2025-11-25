# ---- Admin Panel in Sidebar (Hidden until login) ----
st.sidebar.subheader("🛠️ Admin Panel")

if "is_admin" not in st.session_state:
    st.session_state["is_admin"] = False

# Show login input if not admin
if not st.session_state["is_admin"]:
    password = st.sidebar.text_input("Enter admin passcode", type="password")
    if st.sidebar.button("Login as Admin"):
        if password == ADMIN_PASSCODE:
            st.session_state["is_admin"] = True
            st.sidebar.success("Access granted ✅")
        else:
            st.sidebar.error("Wrong passcode.")

# Show full admin panel only if logged in
if st.session_state["is_admin"]:
    st.sidebar.success("Welcome Admin 👑")
    
    # --- Logout Button ---
    if st.sidebar.button("Logout"):
        st.session_state["is_admin"] = False
        st.sidebar.info("Logged out successfully.")
    
    # --- Dashboard Metrics ---
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
    Total Files: {total_files}  
    Active Files: {active_files}  
    Expired Files: {expired_files}  
    Downloads: {downloads_count}
    """)
    
    # --- Table of All Files ---
    df = get_all_files()
    st.sidebar.markdown("### 🗂 Uploaded Files")
    st.sidebar.dataframe(df, use_container_width=True)

    # --- Delete a File ---
    file_id = st.sidebar.number_input("Enter File ID to Delete", min_value=1, step=1)
    if st.sidebar.button("Delete File"):
        if delete_file(file_id):
            st.sidebar.success("🗑️ File deleted successfully.")
        else:
            st.sidebar.error("File not found.")
