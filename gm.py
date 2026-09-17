import streamlit as st
import requests
from pypdf import PdfReader
from PIL import Image
import os
import base64
import io
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta

# =========================================================
# 1. PAGE CONFIG & STYLES (RESPONSIVE FIX)
# =========================================================
st.set_page_config(
    page_title="Student AI - Pro Platform",
    page_icon="🛡️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom CSS with layout bug fix
st.markdown("""
    <style>
    /* Hide Default Streamlit Chrome */
    #MainMenu, footer, header {visibility: hidden !important;}
    div[data-testid="stHeader"], div[data-testid="stToolbar"], div[data-testid="stDecoration"], div[data-testid="stStatusWidget"] {display: none !important;}

    /* Native Dark Background */
    .stApp {
        background-color: #0A0E17;
        color: #F4F7FB;
    }

    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2rem !important;
        max-width: 700px !important;
    }

    /* Clean Card UI */
    .card-box {
        background: #1E293B;
        padding: 18px;
        border-radius: 12px;
        border: 1px solid #334155;
        margin-bottom: 15px;
    }

    /* Green Process Button Customization */
    div.stButton > button[kind="primary"] {
        background-color: #22C55E !important;
        color: white !important;
        border-radius: 8px !important;
        border: none !important;
        font-weight: bold !important;
    }

    .passcode-badge {
        background: #064E3B;
        color: #34D399;
        padding: 8px 14px;
        border-radius: 8px;
        font-family: monospace;
        font-size: 15px;
        font-weight: bold;
        display: inline-block;
        border: 1px solid #059669;
    }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. CONFIGURATIONS & SECURE DATABASE ENGINE
# =========================================================
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
PRO_PASSCODE = st.secrets.get("PRO_PASSCODE") or os.environ.get("PRO_PASSCODE") or "GMCYBER2026"

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_passcode():
    return f"PRO-{secrets.token_hex(4).upper()}"

def init_db():
    conn = sqlite3.connect("users_database.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            full_name TEXT,
            phone TEXT,
            is_pro INTEGER DEFAULT 0,
            pro_expiry TEXT,
            passcode TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            txn_id TEXT PRIMARY KEY,
            username TEXT,
            status TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def register_user(username, password, full_name, phone):
    conn = sqlite3.connect("users_database.db")
    c = conn.cursor()
    hashed_p = hash_password(password)
    try:
        c.execute("INSERT INTO users (username, password, full_name, phone, is_pro) VALUES (?, ?, ?, ?, 0)",
                  (username, hashed_p, full_name, phone))
        conn.commit()
        conn.close()
        return True, "Account ban gaya! Login karein."
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Username pehle se maujood hai!"

def validate_login(username, password):
    conn = sqlite3.connect("users_database.db")
    c = conn.cursor()
    hashed_p = hash_password(password)
    c.execute("SELECT username, full_name, phone, is_pro, pro_expiry, passcode FROM users WHERE username=? AND password=?", (username, hashed_p))
    user = c.fetchone()
    conn.close()
    return user

def update_pro_status(username, days=30):
    expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    new_passcode = generate_passcode()
    conn = sqlite3.connect("users_database.db")
    c = conn.cursor()
    c.execute("UPDATE users SET is_pro=1, pro_expiry=?, passcode=? WHERE username=?", (expiry_date, new_passcode, username))
    conn.commit()
    conn.close()
    return expiry_date, new_passcode

def check_user_pro_validity(username):
    conn = sqlite3.connect("users_database.db")
    c = conn.cursor()
    c.execute("SELECT is_pro, pro_expiry, passcode FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    
    if not row or row[0] == 0 or not row[1]:
        return False, "Free Tier", 0, None
    
    expiry_dt = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
    if datetime.now() > expiry_dt:
        conn = sqlite3.connect("users_database.db")
        c = conn.cursor()
        c.execute("UPDATE users SET is_pro=0 WHERE username=?", (username,))
        conn.commit()
        conn.close()
        return False, "Expired", 0, None
    
    days_left = (expiry_dt - datetime.now()).days
    return True, row[1], days_left, row[2]

def validate_and_process_txn(txn_id, username):
    txn_clean = txn_id.strip()
    if len(txn_clean) < 10 or not txn_clean.isalnum():
        return False, "❌ Invalid 12-Digit Ref ID!", None
    
    conn = sqlite3.connect("users_database.db")
    c = conn.cursor()
    c.execute("SELECT txn_id FROM transactions WHERE txn_id=?", (txn_clean,))
    existing = c.fetchone()
    
    if existing:
        conn.close()
        return False, "⚠️ Yeh Transaction Ref ID pehle se used hai!", None
    
    c.execute("INSERT INTO transactions (txn_id, username, status, timestamp) VALUES (?, ?, 'APPROVED', ?)",
              (txn_clean, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    expiry, pass_key = update_pro_status(username, days=30)
    return True, f"🎉 Pro Plan Activated till {expiry}!", pass_key

# =========================================================
# 3. SESSION STATE ENGINE
# =========================================================
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "user_data" not in st.session_state:
    st.session_state.user_data = None
if "current_tab" not in st.session_state:
    st.session_state.current_tab = "Home"
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# =========================================================
# 4. AI BACKEND PIPELINE
# =========================================================
def call_ai(prompt, image=None):
    if not api_key:
        return "⚠️ Gemini API Key missing! Secrets mein GEMINI_API_KEY add karein."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    content_payload = [{"type": "text", "text": prompt}]

    if image:
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        content_payload.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img_str}"}
        })

    payload = {
        "model": "google/gemini-2.5-flash",
        "messages": [{"role": "user", "content": content_payload}],
        "max_tokens": 2000
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=120)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        return f"API Error: {response.text}"
    except Exception as e:
        return f"Network Error: {str(e)}"

# =========================================================
# 5. AUTHENTICATION SCREEN
# =========================================================
if not st.session_state.is_logged_in:
    st.markdown("<h2 style='text-align:center;'>🛡️ STUDENT AI</h2>", unsafe_allow_html=True)
    st.caption("<p style='text-align:center;'>Created by <b>MG Gangwar</b> | Academic AI Platform</p>", unsafe_allow_html=True)
    st.divider()

    auth_tab1, auth_tab2 = st.tabs(["🔐 Secure Login", "📝 Register New Account"])

    with auth_tab1:
        st.subheader("Login To Account")
        with st.form(key="login_form"):
            login_user = st.text_input("👤 Username", key="l_u")
            login_pass = st.text_input("🔑 Password", type="password", key="l_p")
            submit_login = st.form_submit_button("🚀 Login", type="primary", use_container_width=True)

        if submit_login:
            if login_user and login_pass:
                user = validate_login(login_user.strip(), login_pass.strip())
                if user:
                    st.session_state.is_logged_in = True
                    st.session_state.user_data = {
                        "username": user[0],
                        "full_name": user[1],
                        "phone": user[2]
                    }
                    st.success("Login Successful!")
                    st.rerun()
                else:
                    st.error("❌ Invalid Username or Password!")
            else:
                st.warning("Please fill all fields.")

    with auth_tab2:
        st.subheader("Create New Account")
        with st.form(key="reg_form"):
            reg_name = st.text_input("Full Name", key="r_n")
            reg_phone = st.text_input("Mobile Number", key="r_p")
            reg_user = st.text_input("Choose Username", key="r_u")
            reg_pass = st.text_input("Choose Password", type="password", key="r_pass")
            submit_reg = st.form_submit_button("📝 Register Now", type="primary", use_container_width=True)

        if submit_reg:
            if reg_user and reg_pass and reg_name:
                success, msg = register_user(reg_user.strip(), reg_pass.strip(), reg_name.strip(), reg_phone.strip())
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.warning("All fields are required.")

# =========================================================
# 6. MAIN APP INTERFACE (ROBUST TOP NAVIGATION)
# =========================================================
else:
    username = st.session_state.user_data["username"]
    is_pro, expiry_info, days_left, passcode_key = check_user_pro_validity(username)

    # Header Bar
    st.markdown(f"### 🛡️ Student AI Pro")
    st.caption(f"Logged in as: **@{username}** | Status: **{'👑 PRO' if is_pro else '🆓 FREE'}**")
    
    # Top Navigation Row
    nav_col1, nav_col2, nav_col3, nav_col4 = st.columns(4)
    with nav_col1:
        if st.button("🏠 Home", use_container_width=True):
            st.session_state.current_tab = "Home"
            st.rerun()
    with nav_col2:
        if st.button("📂 PDF AI", use_container_width=True):
            st.session_state.current_tab = "PDF"
            st.rerun()
    with nav_col3:
        if st.button("📷 Photo AI", use_container_width=True):
            st.session_state.current_tab = "Photo"
            st.rerun()
    with nav_col4:
        if st.button("👤 Profile", use_container_width=True):
            st.session_state.current_tab = "Profile"
            st.rerun()

    st.divider()

    # --- TAB 1: HOME DASHBOARD ---
    if st.session_state.current_tab == "Home":
        m1, m2 = st.columns(2)
        with m1:
            st.markdown(f'<div class="card-box" style="text-align:center;"><h4>Plan</h4><h3>{"PRO 👑" if is_pro else "FREE 🆓"}</h3></div>', unsafe_allow_html=True)
        with m2:
            st.markdown(f'<div class="card-box" style="text-align:center;"><h4>Validity</h4><h3>{days_left if is_pro else 0} Days</h3></div>', unsafe_allow_html=True)

        st.markdown("### ⚡ Quick Modules")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("📂 Open PDF Solver", use_container_width=True):
                st.session_state.current_tab = "PDF"
                st.rerun()
        with col_btn2:
            if st.button("📷 Open Photo Solver", use_container_width=True):
                st.session_state.current_tab = "Photo"
                st.rerun()

        st.divider()
        st.markdown("### 💬 Direct Ask Question")
        with st.form("home_chat_form", clear_on_submit=True):
            user_q = st.text_input("Type your doubt here:")
            send_btn = st.form_submit_button("Ask AI", type="primary", use_container_width=True)

        if send_btn and user_q:
            with st.spinner("Generating answer..."):
                ans = call_ai(user_q)
                st.markdown("### 💡 AI Response:")
                st.write(ans)

    # --- TAB 2: PDF SOLVER ---
    elif st.session_state.current_tab == "PDF":
        st.subheader("📂 PDF Notes & Exam Solver")
        pdf_file = st.file_uploader("Upload College Notes PDF:", type=["pdf"])
        feature = st.radio("Select Output:", ["⚡ Quick Revision Notes", "🎯 Important Exam Questions", "🧪 Practice Quiz (MCQs)", "🛡️ Code Analysis"], horizontal=True)

        if st.button("🚀 Process PDF", type="primary", use_container_width=True):
            if pdf_file:
                reader = PdfReader(io.BytesIO(pdf_file.getvalue()))
                page_count = len(reader.pages)
                
                if page_count > 3 and not is_pro:
                    st.error(f"🔒 Free tier allows max 3 pages! Your PDF has {page_count} pages.")
                    st.info("Upgrade to Pro in Profile tab for unlimited PDF pages.")
                else:
                    with st.spinner("Analyzing PDF content..."):
                        max_p = min(page_count, 3) if not is_pro else page_count
                        text = "".join([p.extract_text() or "" for p in reader.pages[:max_p]])
                        res = call_ai(f"Generate {feature} for:\n\n{text[:80000]}")
                        st.markdown("### 📋 Result:")
                        st.write(res)
            else:
                st.warning("Pehle PDF file upload karein.")

    # --- TAB 3: PHOTO SOLVER ---
    elif st.session_state.current_tab == "Photo":
        st.subheader("📷 Photo / Problem Solver")
        if not is_pro:
            st.error("🔒 Photo Solver is a PRO Feature!")
            if st.button("Upgrade to PRO Now", use_container_width=True):
                st.session_state.current_tab = "Profile"
                st.rerun()
        else:
            img_file = st.file_uploader("Upload Question Image:", type=["jpg", "png", "jpeg"])
            if img_file:
                img = Image.open(img_file)
                st.image(img, width=300)
                if st.button("⚡ Solve Question", type="primary", use_container_width=True):
                    with st.spinner("Solving image..."):
                        res = call_ai("Solve this problem image with step-by-step logic:", image=img)
                        st.markdown("### 💡 Solution:")
                        st.write(res)

    # --- TAB 4: PROFILE & PAYMENT ---
    elif st.session_state.current_tab == "Profile":
        st.subheader("👤 User Profile & Access Key")
        passcode_display = passcode_key if passcode_key else "PRO Inactive"
        
        st.markdown(f"""
        <div class="card-box">
            <h4>Name: {st.session_state.user_data['full_name']}</h4>
            <p><b>Username:</b> @{username}</p>
            <p><b>Status:</b> {'👑 PRO Tier' if is_pro else '🆓 Free Tier'}</p>
            <p><b>Remaining Days:</b> {days_left if is_pro else 0} Days</p>
            <p><b>Passcode Key:</b></p>
            <div class="passcode-badge">{passcode_display}</div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()
        st.subheader("💳 Upgrade to PRO Plan (₹79)")
        st.link_button("🚀 Pay ₹79 via Instamojo / UPI", "https://rzp.io/rzp/R3sR8rWg", use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)
        with st.form("pay_verify_form"):
            txn_id_input = st.text_input("Enter 12-Digit Payment Ref ID (or Admin Passcode):")
            submit_pay = st.form_submit_button("Verify & Activate Pro", use_container_width=True)

        if submit_pay:
            if txn_id_input.strip() == PRO_PASSCODE:
                exp, pass_k = update_pro_status(username)
                st.success(f"🎉 Admin Passcode Accepted! PRO Active till {exp}\n\nPasscode Key: {pass_k}")
                st.rerun()
            else:
                ok, msg, pass_k = validate_and_process_txn(txn_id_input, username)
                if ok:
                    st.success(f"{msg}\n\n🔑 Passcode Key: **{pass_k}**")
                    st.rerun()
                else:
                    st.error(msg)
