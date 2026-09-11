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
    page_title="Student AI - Pro Platform",
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
    .block-container {
        max-width: 1000px;
        padding-top: 1.5rem;
        padding-bottom: 120px;
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
        width: 100%;
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
    .profile-card {
        background: #161F30;
        padding: 24px;
        border-radius: 12px;
        border: 1px solid #202938;
        margin-bottom: 20px;
    }
    .metric-card {
        background: #111827;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #1F2937;
        text-align: center;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# =========================================================
# CONFIGS & DATABASE
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
        return True, "Account successfully created! Ab Login karein."
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Username pehle se exist karta hai!"

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
        return False, "❌ Invalid Transaction ID! Standard 12-digit UPI/Razorpay Ref ID daalein.", None
    
    conn = sqlite3.connect("users_database.db")
    c = conn.cursor()
    c.execute("SELECT txn_id FROM transactions WHERE txn_id=?", (txn_clean,))
    existing = c.fetchone()
    
    if existing:
        conn.close()
        return False, "⚠️ Yeh Transaction ID pehle se used hai!", None
    
    c.execute("INSERT INTO transactions (txn_id, username, status, timestamp) VALUES (?, ?, 'APPROVED', ?)",
              (txn_clean, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    expiry, pass_key = update_pro_status(username, days=30)
    return True, f"🎉 Pro Activated till {expiry}!", pass_key

# =========================================================
# SESSION STATE INITIALIZATION
# =========================================================
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "user_data" not in st.session_state:
    st.session_state.user_data = None
if "current_page" not in st.session_state:
    st.session_state.current_page = "🏠 Dashboard"
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "query_count" not in st.session_state:
    st.session_state.query_count = 0

# =========================================================
# AI ENGINE
# =========================================================
def call_ai(prompt, image=None):
    if not api_key:
        raise Exception("GEMINI_API_KEY Missing in Streamlit Secrets.")

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
# LOGIN / REGISTER (FORM CONTROLLED - NO REFRESH GLITCH)
# =========================================================
if not st.session_state.is_logged_in:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🛡️ Student AI Platform")
    st.caption("Created by **MG Gangwar** | Instant Cyber & Student Assistant")
    st.divider()

    auth_tab1, auth_tab2 = st.tabs(["🔐 Login", "📝 Register New Account"])

    with auth_tab1:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.subheader("Login To Account")
            with st.form(key="login_form"):
                login_user = st.text_input("👤 Username")
                login_pass = st.text_input("🔑 Password", type="password")
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
                        st.success("Login Successful!")
                        st.rerun()
                    else:
                        st.error("❌ Galat Username ya Password!")
                else:
                    st.warning("Dono fields bharen.")

    with auth_tab2:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.subheader("New Registration")
            with st.form(key="reg_form"):
                reg_name = st.text_input("Full Name")
                reg_phone = st.text_input("Mobile Number")
                reg_user = st.text_input("Choose Username")
                reg_pass = st.text_input("Choose Password", type="password")
                submit_reg = st.form_submit_button("📝 Register Now", type="primary")

            if submit_reg:
                if reg_user and reg_pass and reg_name:
                    success, msg = register_user(reg_user.strip(), reg_pass.strip(), reg_name.strip(), reg_phone.strip())
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
                else:
                    st.warning("Sabhi fields required hain.")

# =========================================================
# MAIN APPLICATION INTERFACE
# =========================================================
else:
    username = st.session_state.user_data["username"]
    is_pro, expiry_info, days_left, passcode_key = check_user_pro_validity(username)

    # SIDEBAR NAVIGATION
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.user_data['full_name']}")
        st.caption(f"Status: **{'👑 PRO' if is_pro else '🆓 FREE'}**")
        if is_pro:
            st.caption(f"Days Left: **{days_left} Days**")

        st.divider()
        st.markdown("### 📌 Navigation")
        
        if st.button("🏠 Dashboard"):
            st.session_state.current_page = "🏠 Dashboard"
            st.rerun()
        if st.button("🤖 AI Student Tools"):
            st.session_state.current_page = "🤖 AI Student Tools"
            st.rerun()
        if st.button("👤 Profile & Plan"):
            st.session_state.current_page = "👤 Profile & Plan"
            st.rerun()
        if st.button("ℹ️ About App & Developer"):
            st.session_state.current_page = "ℹ️ About App & Developer"
            st.rerun()

        st.divider()
        if st.button("🔒 Logout"):
            st.session_state.is_logged_in = False
            st.session_state.user_data = None
            st.rerun()

    # HEADER
    head1, head2 = st.columns([3, 1])
    with head1:
        st.title(f"Student AI — {st.session_state.current_page}")
    with head2:
        if not is_pro:
            st.warning("Plan: Free Tier")
        else:
            st.success(f"👑 Pro Active ({days_left}d)")

    st.divider()

    # ---------------------------------------------------------
    # PAGE 1: DASHBOARD
    # ---------------------------------------------------------
    if st.session_state.current_page == "🏠 Dashboard":
        m1, m2, m3 = st.columns(3)
        with m1:
            st.markdown(f'<div class="metric-card"><h4>Current Plan</h4><h3>{"PRO 👑" if is_pro else "FREE 🆓"}</h3></div>', unsafe_allow_html=True)
        with m2:
            st.markdown(f'<div class="metric-card"><h4>Pro Days Left</h4><h3>{days_left if is_pro else 0} Days</h3></div>', unsafe_allow_html=True)
        with m3:
            st.markdown(f'<div class="metric-card"><h4>Total Queries</h4><h3>{st.session_state.query_count}</h3></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("⚡ Quick Start Features")
        
        c1, c2 = st.columns(2)
        with c1:
            st.info("📂 **PDF Analysis**\n\nNotes extraction aur MCQ generation tool use karein.")
            if st.button("Go To PDF Tools"):
                st.session_state.current_page = "🤖 AI Student Tools"
                st.rerun()
        with c2:
            st.info("📷 **Photo Solver**\n\nExam/Homework questions image upload karke solve karein.")
            if st.button("Go To Image Solver"):
                st.session_state.current_page = "🤖 AI Student Tools"
                st.rerun()

    # ---------------------------------------------------------
    # PAGE 2: AI TOOLS
    # ---------------------------------------------------------
    elif st.session_state.current_page == "🤖 AI Student Tools":
        tool_tab1, tool_tab2, tool_tab3 = st.tabs(["📂 PDF Solver", "📷 Image Solver", "💬 Interactive Chat"])

        with tool_tab1:
            st.subheader("📂 PDF Document Processor")
            pdf_file = st.file_uploader("Upload Notes/Book PDF:", type=["pdf"])
            feature = st.radio("Generate Format:", ["Revision Notes", "Exam Questions", "Practice MCQs"], horizontal=True)

            if st.button("🚀 Process PDF", type="primary"):
                if pdf_file:
                    with st.spinner("Processing..."):
                        reader = PdfReader(io.BytesIO(pdf_file.getvalue()))
                        max_p = len(reader.pages) if is_pro else min(3, len(reader.pages))
                        text = "".join([p.extract_text() or "" for p in reader.pages[:max_p]])
                        res = call_ai(f"Generate {feature} for:\n\n{text[:80000]}")
                        st.session_state.query_count += 1
                        st.markdown("### Result:")
                        st.write(res)
                else:
                    st.warning("Pehle PDF file upload karein!")

        with tool_tab2:
            st.subheader("📷 Photo / Problem Solver")
            if not is_pro:
                st.error("🔒 Photo Solver unlocks only in PRO Membership!")
            else:
                img_file = st.file_uploader("Upload Question Picture:", type=["jpg", "png", "jpeg"])
                if img_file:
                    img = Image.open(img_file)
                    st.image(img, width=300)
                    if st.button("⚡ Solve Step-By-Step", type="primary"):
                        with st.spinner("Solving..."):
                            res = call_ai("Solve this problem in detail with full explanations:", image=img)
                            st.session_state.query_count += 1
                            st.write(res)

        with tool_tab3:
            st.subheader("💬 Direct AI Doubt Solver")
            if st.button("🗑️ Clear Conversation"):
                st.session_state.chat_history = []
                st.rerun()

            for q, a in st.session_state.chat_history:
                st.markdown(f"**❓ Question:** {q}")
                st.markdown(f"**🤖 Answer:** {a}")
                st.divider()

            with st.form("chat_form", clear_on_submit=True):
                user_q = st.text_input("Ask any doubt...")
                send_btn = st.form_submit_button("Send Question", type="primary")

            if send_btn and user_q:
                with st.spinner("Thinking..."):
                    ans = call_ai(user_q)
                    st.session_state.query_count += 1
                    st.session_state.chat_history.append((user_q, ans))
                    st.rerun()

    # ---------------------------------------------------------
    # PAGE 3: PROFILE & PAYMENT
    # ---------------------------------------------------------
    elif st.session_state.current_page == "👤 Profile & Plan":
        st.subheader("👤 User Account & Passcode")
        
        st.markdown(f"""
        <div class="profile-card">
            <h4>Name: {st.session_state.user_data['full_name']}</h4>
            <p><b>Username:</b> @{username}</p>
            <p><b>Mobile:</b> {st.session_state.user_data['phone'] or 'N/A'}</p>
            <p><b>Status:</b> {'👑 PRO Plan Active' if is_pro else '🆓 Free Tier'}</p>
            <p><b>Validity:</b> {days_left if is_pro else 0} Days Left</p>
            <p><b>Passcode Key:</b> <code>{passcode_key if passcode_key else 'None'}</code></p>
        </div>
        """, unsafe_allow_html=True)

        st.divider()
        st.subheader("💳 Upgrade To Pro Plan (₹99 / Month)")
        
        st.link_button("💳 Pay ₹99 via Razorpay Link", RAZORPAY_PAY_LINK, type="primary")
        
        st.markdown("<br>", unsafe_allow_html=True)
        with st.form("payment_verify_form"):
            txn_id_input = st.text_input("Enter 12-Digit UPI / Razorpay Reference ID (or Admin Code):")
            submit_pay = st.form_submit_button("Verify & Activate Pro Plan")

        if submit_pay:
            if txn_id_input.strip() == PRO_PASSCODE:
                exp, pass_k = update_pro_status(username)
                st.success(f"🎉 Admin Passcode Accepted! Active till {exp}. Key: {pass_k}")
                st.rerun()
            else:
                ok, msg, pass_k = validate_and_process_txn(txn_id_input, username)
                if ok:
                    st.success(f"{msg}\n\n🔑 Generated Passcode: **{pass_k}**")
                    st.rerun()
                else:
                    st.error(msg)

    # ---------------------------------------------------------
    # PAGE 4: ABOUT APP & DEVELOPER
    # ---------------------------------------------------------
    elif st.session_state.current_page == "ℹ️ About App & Developer":
        st.subheader("ℹ️ About Student AI & Developer")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            if os.path.exists("profile.jpg"):
                st.image("profile.jpg", caption="MG Gangwar (Founder)", width=220)
            elif os.path.exists("profile.png"):
                st.image("profile.png", caption="MG Gangwar (Founder)", width=220)
            else:
                st.image("https://github.com/identicons/mggangwar.png", caption="MG Gangwar (Founder)", width=220)

        with col2:
            st.markdown("""
            ### 👑 App Developed By: **MG Gangwar**
            **Student AI** ek high-performance, secure academic & cyber-security assistant app hai. Is platform ko students ke exam preparation, notes parsing, aur image solver requirements ko automated aur Fast banane ke liye banaya gaya hai.

            ---
            #### 🚀 Key Architecture Highlights:
            * **Secure SHA-256 Authentication:** Fast and encrypted database logins.
            * **Automated Billing Logic:** Single-use 12-digit payment reference verification with 30 days lock.
            * **Smart Multi-Modal Vision Engine:** Detailed handwritten/diagram problem solver.
            
            **Contact Support:** ggangwar314@gamil.com  
            **Developer:** MG Gangwar (GM Cyber Solutions)
            """)
