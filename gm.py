import streamlit as st
import requests
from pypdf import PdfReader
from PIL import Image
import os
import base64
import io
import sqlite3
import re
from datetime import datetime, timedelta

# =========================================================
# STREAMLIT TOOLBAR & FOOTER HIDE
# =========================================================
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    div[data-testid="stToolbar"] {display: none !important;}
    div[data-testid="stDecoration"] {display: none !important;}
    div[data-testid="stStatusWidget"] {visibility: hidden !important;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# =========================================================
# PAGE CONFIG & ADVANCED CSS
# =========================================================
st.set_page_config(
    page_title="Student AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(
    """
    <style>
    .stApp {
        background-color: #0E1117;
        color: #F4F7FB;
    }
    *, *::before, *::after {
        transition: none !important;
        animation: none !important;
    }
    .block-container {
        max-width: 950px;
        padding-top: 1rem;
        padding-bottom: 140px !important;
    }
    section[data-testid="stSidebar"] {
        background-color: #121824;
        border-right: 1px solid #202938;
    }
    .stButton > button {
        border-radius: 10px;
        border: 1px solid #344054;
        background: #111827;
        color: #F8FAFC;
        font-weight: 600;
    }
    .stButton > button:hover {
        border-color: #22C55E;
        background: #172033;
    }
    div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(135deg, #16A34A, #15803D) !important;
        border: 1px solid #22C55E !important;
        color: white !important;
        font-weight: 800 !important;
    }
    .gemini-dock-wrapper {
        position: fixed;
        bottom: 0px;
        left: 0px;
        right: 0px;
        background-color: #0E1117;
        padding: 15px 20px 25px 20px;
        border-top: 1px solid #202938;
        z-index: 99999;
    }
    .dock-container {
        max-width: 850px;
        margin: 0 auto;
    }
    .profile-card {
        background: #161F30;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #202938;
        margin-bottom: 20px;
    }
    .header-title-box {
        display: flex;
        align-items: center;
        gap: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# =========================================================
# CONFIGS & SECRETS
# =========================================================
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
PRO_PASSCODE = st.secrets.get("PRO_PASSCODE") or os.environ.get("PRO_PASSCODE") or "GMCYBER2026"

# FIXED ₹99 PAYMENT LINK WITH PRE-FILLED AMOUNT
RAZORPAY_PAY_LINK = "https://razorpay.me/@gaurav1324?amount=9900"

# =========================================================
# SQLITE DATABASE MANAGEMENT
# =========================================================
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
            pro_expiry TEXT
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
    try:
        c.execute("INSERT INTO users (username, password, full_name, phone, is_pro) VALUES (?, ?, ?, ?, 0)",
                  (username, password, full_name, phone))
        conn.commit()
        conn.close()
        return True, "User Account Successfully Created!"
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Username pehle se exist karta hai! Dusra username chunen."

def validate_login(username, password):
    conn = sqlite3.connect("users_database.db")
    c = conn.cursor()
    c.execute("SELECT username, full_name, phone, is_pro, pro_expiry FROM users WHERE username=? AND password=?", (username, password))
    user = c.fetchone()
    conn.close()
    return user

def update_pro_status(username, days=30):
    expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("users_database.db")
    c = conn.cursor()
    c.execute("UPDATE users SET is_pro=1, pro_expiry=? WHERE username=?", (expiry_date, username))
    conn.commit()
    conn.close()
    return expiry_date

def check_user_pro_validity(username):
    conn = sqlite3.connect("users_database.db")
    c = conn.cursor()
    c.execute("SELECT is_pro, pro_expiry FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    
    if not row or row[0] == 0 or not row[1]:
        return False, "Free Tier", 0
    
    expiry_dt = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
    if datetime.now() > expiry_dt:
        conn = sqlite3.connect("users_database.db")
        c = conn.cursor()
        c.execute("UPDATE users SET is_pro=0 WHERE username=?", (username,))
        conn.commit()
        conn.close()
        return False, "Expired", 0
    
    days_left = (expiry_dt - datetime.now()).days
    return True, row[1], days_left

def validate_and_process_txn(txn_id, username):
    txn_clean = txn_id.strip()
    if len(txn_clean) < 10:
        return False, "❌ Invalid Transaction ID! Kripya sahi UPI/Razorpay Reference ID daalein."
    
    conn = sqlite3.connect("users_database.db")
    c = conn.cursor()
    c.execute("SELECT txn_id FROM transactions WHERE txn_id=?", (txn_clean,))
    existing = c.fetchone()
    
    if existing:
        conn.close()
        return False, "⚠️ Yeh Transaction ID pehle se use ho chuki hai!"
    
    c.execute("INSERT INTO transactions (txn_id, username, status, timestamp) VALUES (?, ?, 'APPROVED', ?)",
              (txn_clean, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    expiry = update_pro_status(username, days=30)
    return True, f"🎉 Payment Verified! Pro Plan Activated till {expiry}."

# =========================================================
# SESSION STATE INITIALIZATION
# =========================================================
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "user_data" not in st.session_state:
    st.session_state.user_data = None
if "show_pro_popup" not in st.session_state:
    st.session_state.show_pro_popup = False
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# =========================================================
# AI ENGINE
# =========================================================
def call_ai(prompt, image=None):
    if not api_key:
        raise Exception("GEMINI_API_KEY missing in Secrets.")

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

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=120
    )

    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        raise Exception(f"API Error: {response.text}")

# =========================================================
# PRO PAYMENT DIALOG
# =========================================================
@st.dialog("💎 Unlock Student AI Pro")
def premium_popup():
    st.markdown("### 👑 STUDENT AI PRO (30 Days)")
    st.write("Unlock Unlimited PDF Processing, Image Solving & Instant MCQs Generator.")
    st.markdown("### 🏷️ Fixed Plan: **₹99 / Month**")
    st.markdown("---")
    
    st.markdown("**Step 1: Direct ₹99 Payment Link**")
    st.link_button("💳 Pay ₹99 via Razorpay / UPI", RAZORPAY_PAY_LINK, type="primary", use_container_width=True)
    st.caption("⚡ Direct ₹99 auto-filled link for fast UPI checkout.")

    st.markdown("---")
    st.markdown("**Step 2: Submit Payment Transaction / UTR ID**")
    txn_input = st.text_input("🔐 Enter 12-Digit UPI Ref / Transaction ID:", placeholder="e.g. 423812908312")

    unlock_col, close_col = st.columns(2)
    with unlock_col:
        if st.button("👑 Verify & Unlock Pro", type="primary", use_container_width=True):
            if txn_input.strip() == PRO_PASSCODE:
                expiry = update_pro_status(st.session_state.user_data["username"])
                st.session_state.show_pro_popup = False
                st.success(f"🎉 Admin Passcode Accepted! Active till {expiry}.")
                st.rerun()
            else:
                success, msg = validate_and_process_txn(txn_input, st.session_state.user_data["username"])
                if success:
                    st.session_state.show_pro_popup = False
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    with close_col:
        if st.button("Close", use_container_width=True):
            st.session_state.show_pro_popup = False
            st.rerun()

if st.session_state.show_pro_popup:
    premium_popup()

# =========================================================
# PAGE 1: LOGIN / REGISTER SCREEN
# =========================================================
if not st.session_state.is_logged_in:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🛡️ Student AI")
    st.caption("Created by **MG Gangwar** | Instant Cyber Assistance, Exam Notes & MCQs")
    st.divider()

    auth_tab1, auth_tab2 = st.tabs(["🔐 Login", "📝 Register New Account"])

    with auth_tab1:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.subheader("Welcome Back")
            login_user = st.text_input("👤 Username", key="l_user")
            login_pass = st.text_input("🔑 Password", type="password", key="l_pass")
            
            if st.button("🚀 Login", type="primary", use_container_width=True):
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
                    st.error("❌ Galat Username ya Password!")

    with auth_tab2:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.subheader("Create Account")
            reg_name = st.text_input("Full Name", key="r_name")
            reg_phone = st.text_input("Mobile Number", key="r_phone")
            reg_user = st.text_input("Choose Username", key="r_user")
            reg_pass = st.text_input("Choose Password", type="password", key="r_pass")
            
            if st.button("📝 Register Account", use_container_width=True):
                if reg_user and reg_pass and reg_name:
                    success, msg = register_user(reg_user.strip(), reg_pass.strip(), reg_name.strip(), reg_phone.strip())
                    if success:
                        st.success(msg + " Login Tab par jaakar login karein.")
                    else:
                        st.error(msg)
                else:
                    st.warning("Sabhi details bharna zaroori hai!")

# =========================================================
# PAGE 2: MAIN DASHBOARD & SYSTEM
# =========================================================
else:
    username = st.session_state.user_data["username"]
    is_pro, expiry_info, days_left = check_user_pro_validity(username)

    # TOP HEADER (COMPACT LOGO & TITLE)
    head_col1, head_col2 = st.columns([4, 1])
    with head_col1:
        st.markdown("### 🛡️ Student AI")
        st.caption(f"User: **{st.session_state.user_data['full_name']}** (@{username})")

    with head_col2:
        if not is_pro:
            if st.button("⭐ UPGRADE ₹99", type="primary"):
                st.session_state.show_pro_popup = True
                st.rerun()
        else:
            st.success(f"👑 Pro ({days_left}d Left)")

    st.divider()

    # SIDEBAR
    with st.sidebar:
        st.markdown("### 👤 User Account")
        st.write(f"**Name:** {st.session_state.user_data['full_name']}")
        st.write(f"**Plan:** {'👑 PRO Member' if is_pro else '🆓 Free User'}")
        if is_pro:
            st.caption(f"Expires in: **{days_left} Days**")
            if days_left <= 5:
                if st.button("🔄 Renew Plan (₹99)", type="primary", use_container_width=True):
                    st.session_state.show_pro_popup = True
                    st.rerun()

        if st.button("🔒 Logout", use_container_width=True):
            st.session_state.is_logged_in = False
            st.session_state.user_data = None
            st.rerun()

        st.divider()
        st.markdown("### 📌 Navigation")
        app_page = st.selectbox("Choose Page:", ["🤖 Student AI Tools", "👤 My Profile", "ℹ️ About App & Developer"])

    # PAGE 1: STUDENT AI TOOLS
    if app_page == "🤖 Student AI Tools":
        tab1, tab2, tab3 = st.tabs(["📂 PDF Analysis", "📷 Image Solver", "💬 Direct Ask Question"])

        # TAB 1: PDF ANALYSIS
        with tab1:
            st.subheader("📂 PDF Notes & MCQ Generator")
            uploaded_file = st.file_uploader("Upload PDF File:", type=["pdf"])

            pdf_page_count = 0
            if uploaded_file:
                try:
                    pdf_reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
                    pdf_page_count = len(pdf_reader.pages)
                    if pdf_page_count > 3 and not is_pro:
                        st.warning(f"🔒 PDF me **{pdf_page_count} pages** hain. Free plan me pehle 3 pages process honge.")
                except Exception as e:
                    st.error(f"PDF Error: {e}")

            feature = st.radio("Generate Output:", ["⚡ Revision Notes", "🎯 Exam Questions", "🧪 Practice MCQs"], horizontal=True)

            if st.button("🚀 Process PDF", type="primary", use_container_width=True):
                if not uploaded_file:
                    st.warning("Pehle PDF Upload karein!")
                else:
                    with st.spinner("Processing PDF..."):
                        reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
                        text = ""
                        max_p = len(reader.pages) if is_pro else min(3, len(reader.pages))
                        for p in reader.pages[:max_p]:
                            text += p.extract_text() or ""
                        
                        ans = call_ai(f"Create structured {feature} from this text:\n\n{text[:100000]}")
                        st.markdown("### 📋 AI Result")
                        st.write(ans)

        # TAB 2: IMAGE SOLVER
        with tab2:
            st.subheader("📷 Photo / Question Solver")
            if not is_pro:
                st.info("🔒 Image Solver PRO Feature hai.")
                if st.button("Unlock Image Solver @ ₹99", type="primary"):
                    st.session_state.show_pro_popup = True
                    st.rerun()
            else:
                uploaded_img = st.file_uploader("Upload Question Image:", type=["jpg", "png", "jpeg"])
                if uploaded_img:
                    img = Image.open(uploaded_img)
                    st.image(img, caption="Uploaded Image", width=300)
                    if st.button("⚡ Solve Image", type="primary"):
                        with st.spinner("Solving..."):
                            res = call_ai("Solve and explain this image step-by-step:", image=img)
                            st.markdown("### 💡 Solution")
                            st.write(res)

        # TAB 3: CHATGPT STYLE DIRECT ASK
        with tab3:
            st.subheader("💬 Direct Ask Question")
            st.caption("Answers scrollable area me display honge.")

            if st.session_state.chat_history:
                for q, a in st.session_state.chat_history:
                    st.markdown(f"**❓ Q:** {q}")
                    st.markdown(f"**🤖 A:** {a}")
                    st.divider()

            st.markdown('<div class="gemini-dock-wrapper"><div class="dock-container">', unsafe_allow_html=True)
            with st.container():
                c1, c2 = st.columns([5, 1])
                with c1:
                    query = st.text_input("Ask any doubt...", key="dock_query", label_visibility="collapsed", placeholder="e.g. Explain Python OOPS Concepts")
                with c2:
                    ask_btn = st.button("⚡ Ask", key="dock_btn", type="primary", use_container_width=True)
            st.markdown('</div></div>', unsafe_allow_html=True)

            if ask_btn and query:
                with st.spinner("Generating..."):
                    ans = call_ai(query)
                    st.session_state.chat_history.append((query, ans))
                    st.rerun()

    # PAGE 2: MY PROFILE & RENEWAL
    elif app_page == "👤 My Profile":
        st.subheader("👤 My Profile Dashboard")
        st.markdown(f"""
        <div class="profile-card">
            <h3>Name: {st.session_state.user_data['full_name']}</h3>
            <p><b>Username:</b> @{username}</p>
            <p><b>Mobile:</b> {st.session_state.user_data['phone'] or 'N/A'}</p>
            <p><b>Membership Status:</b> {'👑 PRO Member' if is_pro else '🆓 Free Plan'}</p>
            <p><b>Days Remaining:</b> {days_left if is_pro else '0'} Days</p>
        </div>
        """, unsafe_allow_html=True)

        if not is_pro or days_left <= 5:
            st.subheader("🔄 Subscription & Renewal")
            if st.button("⭐ Upgrade / Renew Plan (₹99)", type="primary"):
                st.session_state.show_pro_popup = True
                st.rerun()

    # PAGE 3: ABOUT APP & DEVELOPER (WITH LOCAL GITHUB PROFILE PHOTO)
    elif app_page == "ℹ️ About App & Developer":
        st.subheader("ℹ️ About Student AI Platform")
        
        col_dev1, col_dev2 = st.columns([1, 2])
        
        with col_dev1:
            # Tries to load local image from repository, fallback to online avatar
            if os.path.exists("profile.jpg"):
                st.image("profile.jpg", caption="MG Gangwar (Founder)", width=200)
            elif os.path.exists("profile.png"):
                st.image("profile.png", caption="MG Gangwar (Founder)", width=200)
            else:
                st.image("https://github.com/identicons/mggangwar.png", caption="MG Gangwar (Founder)", width=200)
        
        with col_dev2:
            st.markdown("")
            ### 👑 Created By: **MG Gangwar**
            **Student AI** ek high-performance AI platform hai jise specifically Students aur C
