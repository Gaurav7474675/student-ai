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
import extra_streamlit_components as stx

# =========================================================
# 1. PAGE CONFIG & STYLES (NATIVE APP LOOK)
# =========================================================
st.set_page_config(
    page_title="Student AI - Pro Platform",
    page_icon="🛡️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Cookie Manager Setup for Auto-Login Persistence
cookie_manager = stx.get_cookie_manager()

st.markdown("""
    <style>
    /* Hide Default Web Elements */
    #MainMenu, footer, header {visibility: hidden !important;}
    div[data-testid="stToolbar"], div[data-testid="stDecoration"], div[data-testid="stStatusWidget"] {display: none !important;}

    /* Native App Dark Theme */
    .stApp {
        background-color: #0A0E17;
        color: #F4F7FB;
        font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
    }

    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 95px !important; /* Space for Bottom Nav */
        max-width: 500px !important;
    }

    .app-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: linear-gradient(135deg, #1E293B, #0F172A);
        padding: 14px 18px;
        border-radius: 14px;
        border: 1px solid #334155;
        margin-bottom: 18px;
    }

    /* Fixed Native Bottom Navigation Bar */
    div[data-testid="stHorizontalBlock"] {
        position: fixed !important;
        bottom: 0 !important;
        left: 0 !important;
        right: 0 !important;
        background-color: #1E293B !important;
        padding: 8px 10px !important;
        border-top: 1px solid #334155 !important;
        z-index: 999999 !important;
        display: flex !important;
        justify-content: space-around !important;
        box-shadow: 0px -4px 15px rgba(0,0,0,0.5);
    }

    div[data-testid="stHorizontalBlock"] > div {
        flex: 1 !important;
        margin: 0 2px !important;
    }

    div[data-testid="stHorizontalBlock"] button {
        background: transparent !important;
        border: none !important;
        color: #94A3B8 !important;
        font-size: 11px !important;
        padding: 4px 0px !important;
        border-radius: 8px !important;
        height: auto !important;
    }

    div[data-testid="stHorizontalBlock"] button:hover {
        color: #22C55E !important;
        background: #0F172A !important;
    }

    .card-box {
        background: #1E293B;
        padding: 18px;
        border-radius: 14px;
        border: 1px solid #334155;
        margin-bottom: 15px;
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

    .profile-avatar {
        text-align: center;
        margin-bottom: 15px;
    }
    .profile-avatar img {
        border-radius: 50%;
        border: 3px solid #22C55E;
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

def get_user_by_username(username):
    conn = sqlite3.connect("users_database.db")
    c = conn.cursor()
    c.execute("SELECT username, full_name, phone, is_pro, pro_expiry, passcode FROM users WHERE username=?", (username,))
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
# 3. AUTO-LOGIN PERSISTENCE ENGINE (30-DAY COOKIE LOCK)
# =========================================================
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "user_data" not in st.session_state:
    st.session_state.user_data = None
if "current_page" not in st.session_state:
    st.session_state.current_page = "Dashboard"
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "query_count" not in st.session_state:
    st.session_state.query_count = 0

# Check persistent cookie token
saved_user_token = cookie_manager.get(cookie="student_ai_user")
if saved_user_token and not st.session_state.is_logged_in:
    db_user = get_user_by_username(saved_user_token)
    if db_user:
        st.session_state.is_logged_in = True
        st.session_state.user_data = {
            "username": db_user[0],
            "full_name": db_user[1],
            "phone": db_user[2]
        }

def navigate_to(page_name):
    st.session_state.current_page = page_name
    st.rerun()

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
        with st.form(key="login_form_persistent"):
            login_user = st.text_input("👤 Username", key="l_u")
            login_pass = st.text_input("🔑 Password", type="password", key="l_p")
            submit_login = st.form_submit_button("🚀 Login", type="primary")

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
                    # Save persistent cookie token for 30 Days
                    cookie_manager.set(
                        "student_ai_user", 
                        user[0], 
                        key="set_user_cookie", 
                        expires_at=datetime.now() + timedelta(days=30)
                    )
                    st.success("Login Successful!")
                    st.rerun()
                else:
                    st.error("❌ Invalid Username or Password!")
            else:
                st.warning("Please fill all fields.")

    with auth_tab2:
        st.subheader("Create New Account")
        with st.form(key="reg_form_persistent"):
            reg_name = st.text_input("Full Name", key="r_n")
            reg_phone = st.text_input("Mobile Number", key="r_p")
            reg_user = st.text_input("Choose Username", key="r_u")
            reg_pass = st.text_input("Choose Password", type="password", key="r_pass")
            submit_reg = st.form_submit_button("📝 Register Now", type="primary")

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
# 6. MAIN APP INTERFACE & PAGE ROUTING
# =========================================================
else:
    username = st.session_state.user_data["username"]
    is_pro, expiry_info, days_left, passcode_key = check_user_pro_validity(username)

    # Native App Header Bar
    st.markdown(f"""
    <div class="app-header">
        <div>
            <h4 style="margin:0; color:#F8FAFC;">Student AI Pro</h4>
            <span style="font-size:12px; color:#94A3B8;">User: <b>@{username}</b> | Status: <b>{'👑 PRO' if is_pro else '🆓 FREE'}</b></span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # PAGE 1: DASHBOARD
    if st.session_state.current_page == "Dashboard":
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.markdown(f'<div class="card-box" style="text-align:center;"><h4>Plan</h4><h3>{"PRO 👑" if is_pro else "FREE 🆓"}</h3></div>', unsafe_allow_html=True)
        with col_m2:
            st.markdown(f'<div class="card-box" style="text-align:center;"><h4>Pro Validity</h4><h3>{days_left if is_pro else 0} Days</h3></div>', unsafe_allow_html=True)

        st.markdown("### ⚡ Quick Access Modules")
        
        st.markdown("""
        <div class="card-box">
            <h4>📂 PDF Notes Solver</h4>
            <p>Upload lecture notes PDF to extract summaries & practice MCQs.</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Open PDF Solver"):
            navigate_to("Tools")

        st.markdown("""
        <div class="card-box">
            <h4>📷 Photo Problem Solver</h4>
            <p>Upload handwritten exam questions or math problems for instant solutions.</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Open Photo Solver"):
            navigate_to("Tools")

    # PAGE 2: TOOLS
    elif st.session_state.current_page == "Tools":
        tool_tab1, tool_tab2, tool_tab3, tool_tab4 = st.tabs(["📂 PDF Solver", "📷 Photo Solver", "💬 AI Chat", "⚡ Flashcards"])

        with tool_tab1:
            st.subheader("📂 Upload Notes / Book PDF")
            pdf_file = st.file_uploader("Choose PDF File:", type=["pdf"])
            feature = st.radio("Generate Output:", ["Quick Revision Notes", "Important Exam Questions", "Practice Quiz (MCQs)", "Code Analysis"], horizontal=True)

            if st.button("🚀 Process PDF", type="primary"):
                if pdf_file:
                    with st.spinner("Analyzing PDF..."):
                        reader = PdfReader(io.BytesIO(pdf_file.getvalue()))
                        max_p = len(reader.pages) if is_pro else min(3, len(reader.pages))
                        text = "".join([p.extract_text() or "" for p in reader.pages[:max_p]])
                        res = call_ai(f"Generate {feature} for:\n\n{text[:80000]}")
                        st.session_state.query_count += 1
                        st.markdown("### Output Result:")
                        st.write(res)
                else:
                    st.warning("Please upload a PDF file.")

        with tool_tab2:
            st.subheader("📷 Photo / Homework Question Solver")
            if not is_pro:
                st.error("🔒 Photo Solver is locked! Requires PRO Membership.")
                if st.button("Unlock PRO Plan"):
                    navigate_to("Profile")
            else:
                img_file = st.file_uploader("Upload Image:", type=["jpg", "png", "jpeg"])
                if img_file:
                    img = Image.open(img_file)
                    st.image(img, width=280)
                    if st.button("⚡ Solve Step-By-Step", type="primary"):
                        with st.spinner("Analyzing Image..."):
                            res = call_ai("Solve this problem image with step-by-step logic:", image=img)
                            st.session_state.query_count += 1
                            st.write(res)

        with tool_tab3:
            st.subheader("💬 AI Assistant Chat")
            if st.button("🗑️ Clear Chat History"):
                st.session_state.chat_history = []
                st.rerun()

            for q, a in st.session_state.chat_history:
                st.markdown(f"**❓ Question:** {q}")
                st.markdown(f"**🤖 Answer:** {a}")
                st.divider()

            with st.form("chat_form_module", clear_on_submit=True):
                user_q = st.text_input("Ask any doubt...")
                send_btn = st.form_submit_button("Send Query", type="primary")

            if send_btn and user_q:
                with st.spinner("Generating..."):
                    ans = call_ai(user_q)
                    st.session_state.query_count += 1
                    st.session_state.chat_history.append((user_q, ans))
                    st.rerun()

        with tool_tab4:
            st.subheader("⚡ Flashcard Generator")
            topic = st.text_input("Topic Name:")
            if st.button("Generate Flashcards", type="primary"):
                if topic:
                    with st.spinner("Generating..."):
                        res = call_ai(f"Create 5 high-yield flashcards for topic: {topic}.")
                        st.write(res)

    # PAGE 3: PROFILE & FIXED RAZORPAY PAYMENT
    elif st.session_state.current_page == "Profile":
        st.subheader("👤 Account Profile & Passcode Key")
        passcode_display = passcode_key if passcode_key else "PRO Not Active"
        
        st.markdown(f"""
        <div class="card-box">
            <h4>Name: {st.session_state.user_data['full_name']}</h4>
            <p><b>Username:</b> @{username}</p>
            <p><b>Mobile:</b> {st.session_state.user_data['phone'] or 'N/A'}</p>
            <p><b>Status:</b> {'👑 PRO Tier' if is_pro else '🆓 Free Tier'}</p>
            <p><b>Days Left:</b> {days_left if is_pro else 0} Days</p>
            <p><b>Your Passcode Key:</b></p>
            <div class="passcode-badge">{passcode_display}</div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()
        st.subheader("💳 Upgrade To Pro Plan (Fixed ₹99 / Month)")
        
        # FIXED SECURE RAZORPAY PAYMENT BUTTON (EMBEDDED POPUP CHECKOUT TO PREVENT CUSTOM AMOUNT)
        razorpay_html = """
        <form style="text-align:center;">
            <script src="https://checkout.razorpay.com/v1/payment-button.js" 
                    data-payment_button_id="pl_N8x2X99FIXED99" 
                    data-button_text="💳 Pay Fixed ₹99 via Razorpay" 
                    data-button_theme="brand_color">
            </script>
        </form>
        """
        st.components.v1.html(razorpay_html, height=70)

        st.markdown("<br>", unsafe_allow_html=True)
        with st.form("pay_verify_module"):
            txn_id_input = st.text_input("Enter 12-Digit Ref ID (or Admin Code):")
            submit_pay = st.form_submit_button("Verify Payment & Generate Passcode Key")

        if submit_pay:
            if txn_id_input.strip() == PRO_PASSCODE:
                exp, pass_k = update_pro_status(username)
                st.success(f"🎉 Admin Code Accepted! PRO Active till {exp}\n\nP
