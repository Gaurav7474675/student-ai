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
# 1. PAGE CONFIG & CHATGPT STYLES
# =========================================================
st.set_page_config(
    page_title="Student AI - Cyber Gaurav Edition",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    /* Streamlit Chrome CSS Reset */
    #MainMenu, footer, header {visibility: hidden !important;}
    div[data-testid="stHeader"], div[data-testid="stToolbar"], div[data-testid="stDecoration"], div[data-testid="stStatusWidget"] {display: none !important;}

    /* Native ChatGPT Dark Theme */
    .stApp {
        background-color: #212121 !important;
        color: #ECECF1 !important;
    }

    section[data-testid="stSidebar"] {
        background-color: #171717 !important;
        border-right: 1px solid #2F2F2F !important;
    }

    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 6rem !important;
        max-width: 850px !important;
    }

    /* ChatGPT Message Bubbles */
    .chat-user {
        background-color: #2F2F2F;
        color: #F8FAFC;
        padding: 12px 18px;
        border-radius: 18px 18px 2px 18px;
        margin-bottom: 12px;
        float: right;
        clear: both;
        max-width: 80%;
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }

    .chat-ai {
        background-color: #171717;
        color: #ECECF1;
        padding: 14px 20px;
        border-radius: 18px 18px 18px 2px;
        margin-bottom: 12px;
        float: left;
        clear: both;
        max-width: 85%;
        border: 1px solid #2F2F2F;
    }

    /* Input Fields UI */
    .stTextInput > div > div > input {
        background-color: #2F2F2F !important;
        color: #FFFFFF !important;
        border: 1px solid #424242 !important;
        border-radius: 10px !important;
    }

    div.stButton > button[kind="primary"] {
        background-color: #10A37F !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
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

    .dev-card {
        background: #18181B;
        border: 1px solid #27272A;
        padding: 15px;
        border-radius: 12px;
        margin-bottom: 15px;
    }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. SECURE DATABASE & BACKEND ENGINE
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
        return True, "Account Ban Gaya! Login Karein."
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Username Pehle Se Exists Karta Hai!"

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
        return False, "⚠️ Ref ID Already Used!", None
    
    c.execute("INSERT INTO transactions (txn_id, username, status, timestamp) VALUES (?, ?, 'APPROVED', ?)",
              (txn_clean, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    expiry, pass_key = update_pro_status(username, days=30)
    return True, f"🎉 Pro Plan Active Till {expiry}!", pass_key

# =========================================================
# 3. REFRESH & SESSION PERSISTENCE (COOKIE SIMULATION)
# =========================================================
if "messages" not in st.session_state:
    st.session_state.messages = []

# Check session persistence via URL Params
query_params = st.query_params
persisted_user = query_params.get("session_user", None)

if "is_logged_in" not in st.session_state or not st.session_state.is_logged_in:
    if persisted_user:
        conn = sqlite3.connect("users_database.db")
        c = conn.cursor()
        c.execute("SELECT username, email FROM users WHERE username=?", (persisted_user,))
        user_rec = c.fetchone()
        conn.close()
        if user_rec:
            st.session_state.is_logged_in = True
            st.session_state.user_data = {"username": user_rec[0], "email": user_rec[1]}

# =========================================================
# 4. AI PIPELINE ENGINE
# =========================================================
def call_ai(prompt, image=None):
    if not api_key:
        return "⚠️ API Key Missing! Setup secrets file."

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
# 5. AUTHENTICATION MODULE
# =========================================================
if not st.session_state.get("is_logged_in", False):
    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        st.markdown("<h1 style='text-align:center;'>🛡️ STUDENT AI</h1>", unsafe_allow_html=True)
        st.caption("<p style='text-align:center;'>ChatGPT Exam Assistant | Cyber Gaurav</p>", unsafe_allow_html=True)
        st.divider()

        auth_tab1, auth_tab2 = st.tabs(["🔐 Secure Login", "📝 Register Account"])

        with auth_tab1:
            with st.form(key="login_form"):
                login_user = st.text_input("👤 Username")
                login_pass = st.text_input("🔑 Password", type="password")
                submit_login = st.form_submit_button("🚀 Login", type="primary", use_container_width=True)

            if submit_login:
                user = validate_login(login_user.strip(), login_pass.strip())
                if user:
                    st.session_state.is_logged_in = True
                    st.session_state.user_data = {"username": user[0], "email": user[1]}
                    st.query_params["session_user"] = user[0]
                    st.success("Login Success!")
                    st.rerun()
                else:
                    st.error("❌ Galat Username ya Password!")

        with auth_tab2:
            with st.form(key="reg_form"):
                reg_email = st.text_input("📧 Email Address")
                reg_user = st.text_input("Username Select Karein")
                reg_pass = st.text_input("Password Select Karein", type="password")
                submit_reg = st.form_submit_button("📝 Account Banayein", type="primary", use_container_width=True)

            if submit_reg:
                if reg_user and reg_pass and reg_email:
                    success, msg = register_user(reg_user.strip(), reg_pass.strip(), reg_email.strip())
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)

# =========================================================
# 6. MAIN CHATGPT APP SCREEN
# =========================================================
else:
    username = st.session_state.user_data["username"]
    is_pro, expiry_info, days_left, passcode_key = check_user_pro_validity(username)

    # --- CHATGPT SIDEBAR ---
    with st.sidebar:
        st.markdown("## 🛡️ Student AI Pro")
        st.caption("ChatGPT Smart Assistant")
        st.divider()

        if st.button("➕ Nayi Chat Start Karein", use_container_width=True, type="primary"):
            st.session_state.messages = []
            st.rerun()

        st.divider()

        # DEVELOPER PROFILE MODAL / SECTION
        with st.expander("👨‍💻 Developer Profile"):
            st.markdown("""
            <div class="dev-card">
                <h4>Cyber Gaurav</h4>
                <p><b>Role:</b> Ethical Hacker & Lead Student Developer</p>
                <p><b>Specialization:</b> Cybersecurity, AI Integrations, & Web Security Architecture.</p>
                <p><b>Platform:</b> Student AI Ecosystem</p>
            </div>
            """, unsafe_allow_html=True)
            st.link_button("💬 Connect on WhatsApp", "https://wa.me/910000000000?text=Hi%20Cyber%20Gaurav,%20I%20have%20a%20query", use_container_width=True)

        # ACCOUNT & PRO PLAN SETTINGS
        with st.expander("👤 Account & Plan Status"):
            st.write(f"**User:** @{username}")
            st.write(f"**Email:** {st.session_state.user_data['email']}")
            st.write(f"**Plan:** {'👑 PRO' if is_pro else '🆓 Free Tier'}")
            st.write(f"**Days Left:** {days_left if is_pro else 0}")
            st.write(f"**Passcode Key:**")
            passcode_display = passcode_key if passcode_key else "Inactive"
            st.markdown(f'<div class="passcode-badge">{passcode_display}</div>', unsafe_allow_html=True)

            st.divider()
            st.write("**Upgrade to PRO (₹79/Month)**")
            st.link_button("💳 Pay ₹79 Online", RAZORPAY_PAY_LINK, use_container_width=True)

            txn_id_input = st.text_input("12-Digit Ref ID / Passcode:", key="side_txn")
            if st.button("Verify Key", use_container_width=True):
                if txn_id_input.strip() == PRO_PASSCODE:
                    exp, pass_k = update_pro_status(username)
                    st.success(f"🎉 Admin Passcode Accepted!")
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
            st.query_params.clear()
            st.rerun()

    # --- TOP MAIN HEADER ---
    st.markdown("### 🛡️ Student AI Pro")
    st.caption(f"Logged in as: **@{username}** | Plan: **{'👑 PRO' if is_pro else '🆓 FREE'}**")
    st.divider()

    # Empty State Welcome UI
    if not st.session_state.messages:
        st.markdown(f"<h2 style='text-align: center;'>Welcome @{username}! 👋</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #9B9B9B;'>Apne Doubts, PDF Notes, ya Exam Questions upload karke solution paayein!</p>", unsafe_allow_html=True)

    # Render Active Chat
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-ai">🛡️ <b>Student AI</b><br><br>{msg["content"]}</div>', unsafe_allow_html=True)

    st.markdown("<div style='clear: both;'></div>", unsafe_allow_html=True)

    # --- PDF & PHOTO SOLVER EXPLICIT TOOLKIT ---
    st.markdown("<br>", unsafe_allow_html=True)
    
    with st.popover("📎 Attach PDF Notes / Photo Problem"):
        st.markdown("### 📎 File Attachment & Solver Tool")
        attach_type = st.radio("Tool Select Karein:", ["Text Query", "📂 PDF Exam Solver", "📷 Photo Problem Solver"])

        if attach_type == "📂 PDF Exam Solver":
            uploaded_pdf = st.file_uploader("Upload PDF Notes:", type=["pdf"], key="pdf_up")
            pdf_feature = st.selectbox("Output Select Karein:", ["⚡ Quick Revision Notes", "🎯 Important Exam Questions", "🧪 Practice Quiz (MCQs)", "🛡️ Code Analysis"])
            
            # Explicit Process Button Fix for PDF Execution
            if uploaded_pdf and st.button("🚀 Solve / Process PDF", type="primary", use_container_width=True):
                reader = PdfReader(io.BytesIO(uploaded_pdf.getvalue()))
                page_count = len(reader.pages)
                
                if page_count > 3 and not is_pro:
                    st.error(f"🔒 Free tier limits max 3 pages! Upgrade to PRO.")
                else:
                    max_p = min(page_count, 3) if not is_pro else page_count
                    extracted_text = "".join([p.extract_text() or "" for p in reader.pages[:max_p]])
                    prompt_text = f"Analyze this PDF document and generate '{pdf_feature}':\n\n{extracted_text[:80000]}"
                    
                    st.session_state.messages.append({"role": "user", "content": f"📂 Analyzed File: {uploaded_pdf.name} ({pdf_feature})"})
                    with st.spinner("Analyzing PDF content..."):
                        res = call_ai(prompt_text)
                        st.session_state.messages.append({"role": "assistant", "content": res})
                    st.rerun()

        elif attach_type == "📷 Photo Problem Solver":
            if not is_pro:
                st.error("🔒 Photo Solver PRO Feature hai! Sidebar se Upgrade Karein.")
            else:
                uploaded_img = st.file_uploader("Upload Question Image:", type=["jpg", "png", "jpeg"], key="img_up")
                if uploaded_img and st.button("⚡ Solve Photo Question", type="primary", use_container_width=True):
                    img = Image.open(uploaded_img)
                    st.session_state.messages.append({"role": "user", "content": f"📷 Photo Problem Uploaded: {uploaded_img.name}"})
                    with st.spinner("Solving Image Problem..."):
                        res = call_ai("Solve this problem image with detailed logic:", image=img)
                        st.session_state.messages.append({"role": "assistant", "content": res})
                    st.rerun()

    # Regular Chat Bar
    user_prompt = st.chat_input("Kuch bhi puchein...")

    if user_prompt:
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.spinner("Thinking..."):
            res = call_ai(user_prompt)
            st.session_state.messages.append({"role": "assistant", "content": res})
        st.rerun()
