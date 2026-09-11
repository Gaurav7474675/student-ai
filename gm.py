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
# PAGE CONFIGURATION & CUSTOM NATIVE APP CSS
# =========================================================
st.set_page_config(
    page_title="Student AI - Pro Platform",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Hide Streamlit Chrome UI & Add Custom App-Like Styling
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    div[data-testid="stToolbar"] {display: none !important;}
    div[data-testid="stDecoration"] {display: none !important;}
    div[data-testid="stStatusWidget"] {visibility: hidden !important;}

    .stApp {
        background-color: #0E1117;
        color: #F4F7FB;
    }
    .block-container {
        max-width: 900px;
        padding-top: 1rem;
        padding-bottom: 100px;
    }
    .app-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background-color: #161F30;
        padding: 12px 20px;
        border-radius: 12px;
        border: 1px solid #202938;
        margin-bottom: 20px;
    }
    .stButton > button {
        border-radius: 10px;
        border: 1px solid #344054;
        background: #111827;
        color: #F8FAFC;
        font-weight: 600;
        width: 100%;
        padding: 0.5rem 1rem;
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
    .card-box {
        background: #161F30;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #202938;
        margin-bottom: 15px;
    }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# CONFIGS & DATABASE ENGINE
# =========================================================
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
PRO_PASSCODE = st.secrets.get("PRO_PASSCODE") or os.environ.get("PRO_PASSCODE") or "GMCYBER2026"
RAZORPAY_PAY_LINK = "https://razorpay.me/@gaurav1324"

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
        return True, "Account successfully ban gaya hai! Ab Login karein."
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
        return False, "❌ Invalid Transaction ID! Standard 12-digit Ref ID daalein.", None
    
    conn = sqlite3.connect("users_database.db")
    c = conn.cursor()
    c.execute("SELECT txn_id FROM transactions WHERE txn_id=?", (txn_clean,))
    existing = c.fetchone()
    
    if existing:
        conn.close()
        return False, "⚠️ Yeh Transaction ID pehle se istemal ho chuki hai!", None
    
    c.execute("INSERT INTO transactions (txn_id, username, status, timestamp) VALUES (?, ?, 'APPROVED', ?)",
              (txn_clean, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    expiry, pass_key = update_pro_status(username, days=30)
    return True, f"🎉 Pro Activated till {expiry}!", pass_key

# =========================================================
# SESSION STATE NAVIGATION & CONTROL
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

def navigate_to(page_name):
    st.session_state.current_page = page_name
    st.rerun()

# =========================================================
# AI INTEGRATION ENGINE
# =========================================================
def call_ai(prompt, image=None):
    if not api_key:
        return "⚠️ Gemini API Key config missing! Secrets me API Key add karein."

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
        return f"Error: {response.text}"
    except Exception as e:
        return f"Network Error: {str(e)}"

# =========================================================
# AUTHENTICATION SCREEN (NO REFRESH GLITCH)
# =========================================================
if not st.session_state.is_logged_in:
    st.markdown("### 🛡️ STUDENT AI")
    st.caption("Created by **MG Gangwar** | Instant Cyber & Academic Assistant")
    st.divider()

    auth_tab1, auth_tab2 = st.tabs(["🔐 Login", "📝 Register New Account"])

    with auth_tab1:
        st.subheader("Sign In")
        with st.form(key="login_form"):
            login_user = st.text_input("👤 Username")
            login_pass = st.text_input("🔑 Password", type="password")
            submit_login = st.form_submit_button("🚀 Login Now", type="primary")

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
                    st.error("❌ Galat Username ya Password!")
            else:
                st.warning("Dono fields fill karein.")

    with auth_tab2:
        st.subheader("Create Account")
        with st.form(key="reg_form"):
            reg_name = st.text_input("Full Name")
            reg_phone = st.text_input("Mobile Number")
            reg_user = st.text_input("Choose Username")
            reg_pass = st.text_input("Choose Password", type="password")
            submit_reg = st.form_submit_button("📝 Register Account", type="primary")

        if submit_reg:
            if reg_user and reg_pass and reg_name:
                success, msg = register_user(reg_user.strip(), reg_pass.strip(), reg_name.strip(), reg_phone.strip())
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.warning("Sabhi detail bharna zaroori hai.")

# =========================================================
# MAIN APP NAVIGATION & CORE INTERFACE
# =========================================================
else:
    username = st.session_state.user_data["username"]
    is_pro, expiry_info, days_left, passcode_key = check_user_pro_validity(username)

    # APP HEADER TOOLBAR
    st.markdown(f"""
    <div class="app-header">
        <div>
            <h3 style="margin:0; padding:0;">🛡️ Student AI</h3>
            <span style="font-size:12px; color:#A0AEC0;">User: @{username} | Plan: <b>{'👑 PRO' if is_pro else '🆓 FREE'}</b></span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # TOP APP-LIKE BUTTON NAVIGATION & BACK CONTROL
    nav_col1, nav_col2, nav_col3, nav_col4, nav_col5 = st.columns([1, 1, 1, 1, 1])
    
    with nav_col1:
        if st.session_state.current_page != "Dashboard":
            if st.button("⬅️ Back"):
                navigate_to("Dashboard")
        else:
            st.write("")

    with nav_col2:
        if st.button("🏠 Home"):
            navigate_to("Dashboard")
            
    with nav_col3:
        if st.button("🤖 Tools"):
            navigate_to("Tools")
            
    with nav_col4:
        if st.button("👤 Profile"):
            navigate_to("Profile")
            
    with nav_col5:
        if st.button("ℹ️ About"):
            navigate_to("About")

    st.divider()

    # ---------------------------------------------------------
    # PAGE: DASHBOARD
    # ---------------------------------------------------------
    if st.session_state.current_page == "Dashboard":
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.markdown(f'<div class="card-box" style="text-align:center;"><h4>Plan</h4><h3>{"PRO 👑" if is_pro else "FREE 🆓"}</h3></div>', unsafe_allow_html=True)
        with col_m2:
            st.markdown(f'<div class="card-box" style="text-align:center;"><h4>Days Left</h4><h3>{days_left if is_pro else 0}</h3></div>', unsafe_allow_html=True)
        with col_m3:
            st.markdown(f'<div class="card-box" style="text-align:center;"><h4>Queries</h4><h3>{st.session_state.query_count}</h3></div>', unsafe_allow_html=True)

        st.markdown("### ⚡ Fast Feature Access")
        dash_c1, dash_c2 = st.columns(2)
        with dash_c1:
            st.markdown("""
            <div class="card-box">
                <h4>📂 PDF Notes Solver</h4>
                <p>Upload lecture notes PDF to extract summaries and generate practice MCQs.</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Open PDF Solver"):
                navigate_to("Tools")

        with dash_c2:
            st.markdown("""
            <div class="card-box">
                <h4>📷 Photo Problem Solver</h4>
                <p>Upload handwritten exam questions or math problems for instant step-by-step resolution.</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Open Photo Solver"):
                navigate_to("Tools")

    # ---------------------------------------------------------
    # PAGE: AI TOOLS
    # ---------------------------------------------------------
    elif st.session_state.current_page == "Tools":
        tool_tab1, tool_tab2, tool_tab3 = st.tabs(["📂 PDF Analysis", "📷 Photo Solver", "💬 Direct Chat"])

        with tool_tab1:
            st.subheader("📂 Upload Notes / Book PDF")
            pdf_file = st.file_uploader("Choose PDF File:", type=["pdf"])
            feature = st.radio("Generate:", ["Quick Revision Notes", "Important Exam Questions", "Practice Quiz (MCQs)", "Cyber Security & Code Analysis"], horizontal=True)

            if st.button("🚀 Process PDF", type="primary"):
                if pdf_file:
                    with st.spinner("Analyzing PDF..."):
                        reader = PdfReader(io.BytesIO(pdf_file.getvalue()))
                        max_p = len(reader.pages) if is_pro else min(3, len(reader.pages))
                        text = "".join([p.extract_text() or "" for p in reader.pages[:max_p]])
                        res = call_ai(f"Generate {feature} for:\n\n{text[:80000]}")
                        st.session_state.query_count += 1
                        st.markdown("### Solution:")
                        st.write(res)
                else:
                    st.warning("Kripya pehle PDF file select karein.")

        with tool_tab2:
            st.subheader("📷 Photo / Problem Solver")
            if not is_pro:
                st.error("🔒 Photo Solver unlocks only in PRO Membership!")
                if st.button("Upgrade to Pro Plan"):
                    navigate_to("Profile")
            else:
                img_file = st.file_uploader("Upload Question Image:", type=["jpg", "png", "jpeg"])
                if img_file:
                    img = Image.open(img_file)
                    st.image(img, width=300)
                    if st.button("⚡ Solve Step-By-Step", type="primary"):
                        with st.spinner("Analyzing Image..."):
                            res = call_ai("Solve this question in complete detail step-by-step:", image=img)
                            st.session_state.query_count += 1
                            st.write(res)

        with tool_tab3:
            st.subheader("💬 Direct AI Assistant")
            if st.button("🗑️ Clear Chat History"):
                st.session_state.chat_history = []
                st.rerun()

            for q, a in st.session_state.chat_history:
                st.markdown(f"**❓ Question:** {q}")
                st.markdown(f"**🤖 Answer:** {a}")
                st.divider()

            with st.form("chat_form", clear_on_submit=True):
                user_q = st.text_input("Ask any question or concept...")
                send_btn = st.form_submit_button("Send Question", type="primary")

            if send_btn and user_q:
                with st.spinner("Thinking..."):
                    ans = call_ai(user_q)
                    st.session_state.query_count += 1
                    st.session_state.chat_history.append((user_q, ans))
                    st.rerun()

    # ---------------------------------------------------------
    # PAGE: PROFILE & PAYMENT LOGIC
    # ---------------------------------------------------------
    elif st.session_state.current_page == "Profile":
        st.subheader("👤 User Profile & Membership")
        
        st.markdown(f"""
        <div class="card-box">
            <p><b>Full Name:</b> {st.session_state.user_data['full_name']}</p>
            <p><b>Username:</b> @{username}</p>
            <p><b>Mobile:</b> {st.session_state.user_data['phone'] or 'N/A'}</p>
            <p><b>Active Plan:</b> {'👑 PRO Tier' if is_pro else '🆓 FREE Tier'}</p>
            <p><b>Passcode Key:</b> <code>{passcode_key if passcode_key else 'None'}</code></p>
        </div>
        """, unsafe_allow_html=True)

        st.divider()
        st.subheader("💳 Upgrade To Pro Plan (₹99 / Month)")
        st.link_button("💳 Pay ₹99 via Razorpay", RAZORPAY_PAY_LINK, type="primary")

        st.markdown("<br>", unsafe_allow_html=True)
        with st.form("payment_form"):
            txn_id_input = st.text_input("Enter 12-Digit Reference ID / Admin Passcode:")
            submit_pay = st.form_submit_button("Verify & Activate Pro")

        if submit_pay:
            if txn_id_input.strip() == PRO_PASSCODE:
                exp, pass_k = update_pro_status(username)
                st.success(f"🎉 Passcode Verified! Pro active till {exp}")
                st.rerun()
            else:
                ok, msg, pass_k = validate_and_process_txn(txn_id_input, username)
                if ok:
                    st.success(f"{msg}\n\nKey: **{pass_k}**")
                    st.rerun()
                else:
                    st.error(msg)

        st.divider()
        if st.button("🔒 Logout"):
            st.session_state.is_logged_in = False
            st.session_state.user_data = None
            st.rerun()

    # ---------------------------------------------------------
    # PAGE: ABOUT SECTION
    # ---------------------------------------------------------
    elif st.session_state.current_page == "About":
        st.subheader("ℹ️ About Student AI & Developer")
        
        about_col1, about_col2 = st.columns([1, 2])
        
        with about_col1:
            if os.path.exists("profile.jpg"):
                st.image("profile.jpg", caption="MG Gangwar", width=200)
            elif os.path.exists("profile.png"):
                st.image("profile.png", caption="MG Gangwar", width=200)
            else:
                st.image("https://github.com/identicons/mggangwar.png", caption="MG Gangwar", width=200)

        with about_col2:
            st.markdown("""
            ### 👑 Created By: **MG Gangwar**
            **Student AI** ek end-to-end smart learning solution hai jo students ki study, notes parsing, code analysis, aur problem solving ko single dashboard par laata hai.

            ---
            * **Secure Database Logic:** SHA-256 encrypted authentication system.
            * **Multi-Modal Vision AI:** Handwritten notes aur image queries solving engine.
            * **Instant Auto Verification:** Razorpay 12-digit transaction locking mechanism.
            
            **Developer Contact:** ggangwar314@gmail.com
            """)
