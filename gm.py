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
# 1. PAGE CONFIG & CHATGPT NATIVE STYLES
# =========================================================
st.set_page_config(
    page_title="Student AI - ChatGPT Edition",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    /* Hide Default Streamlit Chrome Header & Footer */
    #MainMenu, footer, header {visibility: hidden !important;}
    div[data-testid="stHeader"], div[data-testid="stToolbar"], div[data-testid="stDecoration"], div[data-testid="stStatusWidget"] {display: none !important;}

    /* Native Dark Background - ChatGPT UI */
    .stApp {
        background-color: #212121 !important;
        color: #ECECF1 !important;
    }

    /* Left Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #171717 !important;
        border-right: 1px solid #2F2F2F !important;
    }

    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 6rem !important;
        max-width: 800px !important;
    }

    /* ChatGPT Style Chat Bubbles */
    .chat-user {
        background-color: #2F2F2F;
        color: #F8FAFC;
        padding: 12px 18px;
        border-radius: 18px 18px 2px 18px;
        margin-bottom: 12px;
        margin-left: 20%;
        width: fit-content;
        max-width: 80%;
        float: right;
        clear: both;
        box-shadow: 0 1px 3px rgba(0,0,0,0.2);
    }

    .chat-ai {
        background-color: #171717;
        color: #ECECF1;
        padding: 14px 20px;
        border-radius: 18px 18px 18px 2px;
        margin-bottom: 12px;
        margin-right: 15%;
        width: fit-content;
        max-width: 85%;
        float: left;
        clear: both;
        border: 1px solid #2F2F2F;
    }

    /* Input & Button Styling */
    .stTextInput > div > div > input {
        background-color: #2F2F2F !important;
        color: #FFFFFF !important;
        border: 1px solid #424242 !important;
        border-radius: 12px !important;
    }

    div.stButton > button[kind="primary"] {
        background-color: #10A37F !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
    }

    div.stButton > button[kind="primary"]:hover {
        background-color: #1A7F64 !important;
    }

    .passcode-badge {
        background: #064E3B;
        color: #34D399;
        padding: 6px 12px;
        border-radius: 6px;
        font-family: monospace;
        font-size: 14px;
        font-weight: bold;
        display: inline-block;
        border: 1px solid #059669;
    }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. CONFIGURATIONS & DATABASE ENGINE (EMAIL BASED & 1-MONTH VALIDITY)
# =========================================================
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
PRO_PASSCODE = st.secrets.get("PRO_PASSCODE") or os.environ.get("PRO_PASSCODE") or "GMCYBER2026"
RAZORPAY_PAY_LINK = "https://rzp.io/rzp/R3sR8rWg"

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
            email TEXT,
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

def register_user(username, password, email):
    conn = sqlite3.connect("users_database.db")
    c = conn.cursor()
    hashed_p = hash_password(password)
    try:
        c.execute("INSERT INTO users (username, password, email, is_pro) VALUES (?, ?, ?, 0)",
                  (username, hashed_p, email))
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
    c.execute("SELECT username, email, is_pro, pro_expiry, passcode FROM users WHERE username=? AND password=?", (username, hashed_p))
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
if "messages" not in st.session_state:
    st.session_state.messages = []

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
# 5. AUTHENTICATION SCREEN (ONLY EMAIL, USERNAME & PASSWORD)
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
                        "email": user[1]
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
            reg_email = st.text_input("📧 Gmail / Email ID", key="r_e")
            reg_user = st.text_input("Choose Username", key="r_u")
            reg_pass = st.text_input("Choose Password", type="password", key="r_pass")
            submit_reg = st.form_submit_button("📝 Register Now", type="primary", use_container_width=True)

        if submit_reg:
            if reg_user and reg_pass and reg_email:
                success, msg = register_user(reg_user.strip(), reg_pass.strip(), reg_email.strip())
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.warning("All fields are required.")

# =========================================================
# 6. MAIN CHATGPT-STYLE APP INTERFACE
# =========================================================
else:
    username = st.session_state.user_data["username"]
    is_pro, expiry_info, days_left, passcode_key = check_user_pro_validity(username)

    # --- CHATGPT SIDEBAR ---
    with st.sidebar:
        st.markdown("### 🤖 ChatGPT AI")
        if st.button("➕ Nayi Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
            
        st.divider()
        st.markdown("**Haliya (Recent)**")
        st.caption("• Academic Doubts")
        st.caption("• PDF Exam Notes")
        st.caption("• Photo Solver")

        st.divider()
        st.markdown(f"**👤 @{username}**")
        st.caption(f"Email: {st.session_state.user_data['email']}")
        st.caption(f"Status: {'👑 PRO' if is_pro else '🆓 Free'}")

        # Account & Payment Section inside Sidebar Expander
        with st.expander("👤 Account & Plan Settings"):
            passcode_display = passcode_key if passcode_key else "PRO Inactive"
            st.write(f"**Plan:** {'👑 PRO' if is_pro else '🆓 Free Tier'}")
            st.write(f"**Remaining Days:** {days_left if is_pro else 0}")
            st.write(f"**Passcode Key:**")
            st.markdown(f'<div class="passcode-badge">{passcode_display}</div>', unsafe_allow_html=True)
            
            st.markdown("---")
            st.write("**Upgrade to PRO Plan (₹79)**")
            st.link_button("💳 Pay ₹79 via Razorpay", RAZORPAY_PAY_LINK, use_container_width=True)
            
            txn_id_input = st.text_input("Enter 12-Digit Ref ID / Passcode:", key="side_txn")
            if st.button("Verify & Activate", key="side_pay_btn", type="primary", use_container_width=True):
                if txn_id_input.strip() == PRO_PASSCODE:
                    exp, pass_k = update_pro_status(username)
                    st.success(f"🎉 Admin Passcode Accepted! Active till {exp}")
                    st.rerun()
                else:
                    ok, msg, pass_k = validate_and_process_txn(txn_id_input, username)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.is_logged_in = False
            st.session_state.user_data = None
            st.rerun()

    # --- MAIN TOP HEADER ---
    st.markdown("### 🤖 Student AI Pro")
    st.caption("ChatGPT Powered Exam & Learning Assistant")
    st.divider()

    # Welcome Message for New Chat
    if not st.session_state.messages:
        st.markdown(f"<h2 style='text-align: center;'>Welcome @{username}! 👋</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #9B9B9B;'>Kya bana rahe ho aaj? Padhai ya Doubt Solver start karein! 🔥</p>", unsafe_allow_html=True)

    # Render Active Chat
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-ai">🤖 <b>Student AI</b><br><br>{msg["content"]}</div>', unsafe_allow_html=True)

    st.markdown("<div style='clear: both;'></div>", unsafe_allow_html=True)

    # --- CHATGPT INPUT DOCK + PDF/PHOTO TOOLS ---
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    with st.popover("➕ PDF / Photo Tools Attach Karein"):
        st.markdown("### 📎 Attach Document / Photo")
        attach_type = st.radio("Select Tool:", ["Text Question Only", "📂 PDF Exam Solver", "📷 Photo Problem Solver"])
        
        uploaded_pdf = None
        uploaded_img = None
        pdf_feature = "⚡ Quick Revision Notes"

        if attach_type == "📂 PDF Exam Solver":
            uploaded_pdf = st.file_uploader("Upload PDF College Notes:", type=["pdf"])
            pdf_feature = st.radio("Output Option Select Karein:", ["⚡ Quick Revision Notes", "🎯 Important Exam Questions", "🧪 Practice Quiz (MCQs)", "🛡️ Code Analysis"])
        elif attach_type == "📷 Photo Problem Solver":
            if not is_pro:
                st.error("🔒 Photo Solver is a PRO Feature! Sidebar se Upgrade Karein.")
            else:
                uploaded_img = st.file_uploader("Upload Question Image:", type=["jpg", "png", "jpeg"])

    # Continuous Bottom Text Bar
    user_prompt = st.chat_input("Kuch bhi puchein...")

    if user_prompt:
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        st.rerun()

    # Process AI Execution
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        latest_prompt = st.session_state.messages[-1]["content"]

        with st.spinner("ChatGPT processing..."):
            ai_response = ""

            # 1. PDF Processing Logic
            if uploaded_pdf:
                reader = PdfReader(io.BytesIO(uploaded_pdf.getvalue()))
                page_count = len(reader.pages)
                
                if page_count > 3 and not is_pro:
                    ai_response = f"🔒 Free tier allows max 3 pages! Your PDF has {page_count} pages. Upgrade to PRO for unlimited access."
                else:
                    max_p = min(page_count, 3) if not is_pro else page_count
                    extracted_text = "".join([p.extract_text() or "" for p in reader.pages[:max_p]])
                    full_p = f"{latest_prompt}\n\nTask: Generate {pdf_feature} for:\n{extracted_text[:80000]}"
                    ai_response = call_ai(full_p)

            # 2. Photo Processing Logic
            elif uploaded_img and is_pro:
                img = Image.open(uploaded_img)
                ai_response = call_ai(f"Solve this step-by-step: {latest_prompt}", image=img)

            # 3. Direct AI Question Logic
            else:
                ai_response = call_ai(latest_prompt)

            st.session_state.messages.append({"role": "assistant", "content": ai_response})
            st.rerun()
