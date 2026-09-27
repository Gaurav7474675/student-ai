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
# 1. PAGE CONFIG & MODERN UI STYLES
# =========================================================
st.set_page_config(
    page_title="Student AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    /* Reset Unwanted Streamlit Elements */
    #MainMenu, footer, header {visibility: hidden !important;}
    div[data-testid="stHeader"], div[data-testid="stToolbar"], div[data-testid="stDecoration"], div[data-testid="stStatusWidget"] {display: none !important;}

    /* Pitch-Black Dark Theme */
    .stApp {
        background-color: #000000 !important;
        color: #FFFFFF !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    /* ChatGPT Mobile Style Drawer Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #0D0D0D !important;
        border-right: 1px solid #1A1A1A !important;
        width: 310px !important;
    }

    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 7rem !important;
        max-width: 820px !important;
    }

    /* Top Bar ChatGPT Style Alignment */
    .top-bar-custom {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding-bottom: 10px;
        border-bottom: 1px solid #1F1F1F;
        margin-bottom: 15px;
    }

    .app-title-text {
        font-size: 19px;
        font-weight: 700;
        color: #FFFFFF;
    }

    .pro-badge {
        background: linear-gradient(135deg, #FFD700 0%, #FF8C00 100%);
        color: #000000;
        font-size: 10px;
        font-weight: 800;
        padding: 2px 6px;
        border-radius: 4px;
        margin-left: 6px;
    }

    /* Chat Bubbles */
    .chat-user {
        background-color: #212121;
        color: #FFFFFF;
        padding: 12px 18px;
        border-radius: 22px;
        margin-bottom: 14px;
        float: right;
        clear: both;
        max-width: 82%;
        font-size: 15px;
        line-height: 1.5;
    }

    .chat-ai {
        color: #ECECF1;
        padding: 4px 0px 14px 0px;
        margin-bottom: 14px;
        float: left;
        clear: both;
        width: 100%;
        font-size: 15px;
        line-height: 1.6;
    }

    /* Input Box */
    .stChatInputContainer {
        padding-bottom: 15px !important;
    }
    
    .stChatInput > div {
        background-color: #171717 !important;
        border: 1px solid #2F2F2F !important;
        border-radius: 28px !important;
    }

    .plan-notice {
        font-size: 11px;
        color: #888888;
        text-align: center;
        margin-top: 4px;
    }

    .feature-card {
        background-color: #121212;
        border: 1px solid #222222;
        padding: 20px;
        border-radius: 12px;
        margin-bottom: 15px;
    }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. DATABASE & BACKEND ENGINE
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
        return True, "Account Created! Please Login."
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Username Already Exists!"

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
        return False, "❌ Invalid Ref ID!", None
    
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
# 3. SESSION MANAGEMENT
# =========================================================
if "messages" not in st.session_state:
    st.session_state.messages = []

if "active_page" not in st.session_state:
    st.session_state.active_page = "chat"

if "show_sidebar" not in st.session_state:
    st.session_state.show_sidebar = False

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
        return "⚠️ API Key Missing!"

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
        st.markdown("<h2 style='text-align:center;'>🛡️ Student AI</h2>", unsafe_allow_html=True)
        st.caption("<p style='text-align:center;'>Sign in to start learning</p>", unsafe_allow_html=True)
        st.divider()

        auth_tab1, auth_tab2 = st.tabs(["🔐 Sign In", "📝 Create Account"])

        with auth_tab1:
            with st.form(key="login_form"):
                login_user = st.text_input("👤 Username")
                login_pass = st.text_input("🔑 Password", type="password")
                submit_login = st.form_submit_button("Log In", type="primary", use_container_width=True)

            if submit_login:
                user = validate_login(login_user.strip(), login_pass.strip())
                if user:
                    st.session_state.is_logged_in = True
                    st.session_state.user_data = {"username": user[0], "email": user[1]}
                    st.query_params["session_user"] = user[0]
                    st.success("Login Success!")
                    st.rerun()
                else:
                    st.error("❌ Invalid Credentials!")

        with auth_tab2:
            with st.form(key="reg_form"):
                reg_email = st.text_input("📧 Email")
                reg_user = st.text_input("Username")
                reg_pass = st.text_input("Password", type="password")
                submit_reg = st.form_submit_button("Sign Up", type="primary", use_container_width=True)

            if submit_reg:
                if reg_user and reg_pass and reg_email:
                    success, msg = register_user(reg_user.strip(), reg_pass.strip(), reg_email.strip())
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)

# =========================================================
# 6. MAIN APPLICATION SCREEN
# =========================================================
else:
    username = st.session_state.user_data["username"]
    is_pro, expiry_info, days_left, passcode_key = check_user_pro_validity(username)
    app_display_name = "Student AI Pro" if is_pro else "Student AI"

    # --- SIDEBAR DRAWER NAVIGATION ---
    with st.sidebar:
        st.markdown(f"### 🛡️ {app_display_name}")
        st.caption(f"Logged as **@{username}** ({'👑 PRO' if is_pro else '🆓 Free Plan'})")
        st.divider()

        if st.button("💬 Chat AI Interface", use_container_width=True):
            st.session_state.active_page = "chat"
            st.rerun()

        if st.button("📱 About App & Plans", use_container_width=True):
            st.session_state.active_page = "about"
            st.rerun()

        if st.button("👨‍💻 Developer Profile", use_container_width=True):
            st.session_state.active_page = "developer"
            st.rerun()

        st.divider()

        with st.expander("💳 Upgrade / Activate Pro"):
            if is_pro:
                st.success(f"PRO Active! Days Left: {days_left}")
                st.code(f"Passcode: {passcode_key}")
            else:
                st.write("Unlock Unlimited PDF Pages & Photo Solver!")
                st.link_button("💳 Pay ₹79 via Razorpay", RAZORPAY_PAY_LINK, use_container_width=True)
                
                txn_input = st.text_input("Enter 12-Digit Ref ID / Passcode:", key="side_pro_key")
                if st.button("Activate Pro Plan", use_container_width=True):
                    if txn_input.strip() == PRO_PASSCODE:
                        exp, pass_k = update_pro_status(username)
                        st.success("🎉 Admin Passcode Accepted!")
                        st.rerun()
                    else:
                        ok, msg, pass_k = validate_and_process_txn(txn_input, username)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

        if st.button("🚪 Logout Account", use_container_width=True):
            st.session_state.is_logged_in = False
            st.session_state.user_data = None
            st.query_params.clear()
            st.rerun()

    # =========================================================
    # EXACT CHATGPT STYLE TOP HEADER BAR
    # =========================================================
    h_col1, h_col2, h_col3 = st.columns([1, 4, 1])

    # Left: Hamburger Menu Icon (To Toggle Drawer)
    with h_col1:
        with st.popover("☰ Menu"):
            st.markdown("### Navigation Drawer")
            if st.button("💬 Chat Interface", key="pop_chat", use_container_width=True):
                st.session_state.active_page = "chat"
                st.rerun()
            if st.button("📱 About & Plans", key="pop_about", use_container_width=True):
                st.session_state.active_page = "about"
                st.rerun()
            if st.button("👨‍💻 Developer Profile", key="pop_dev", use_container_width=True):
                st.session_state.active_page = "developer"
                st.rerun()

    # Center: App Title
    with h_col2:
        pro_tag = '<span class="pro-badge">PRO</span>' if is_pro else ''
        st.markdown(f"<div style='text-align:center;'><span class='app-title-text'>🛡️ {app_display_name}</span>{pro_tag}</div>", unsafe_allow_html=True)

    # Right: ChatGPT Three Dots Options Menu
    with h_col3:
        with st.popover("⋮ More"):
            st.markdown(f"**User:** @{username}")
            st.caption(f"Status: {'👑 PRO Active' if is_pro else '🆓 Free Plan'}")
            st.divider()
            if not is_pro:
                st.link_button("🎁 Offer / Upgrade Pro", RAZORPAY_PAY_LINK, use_container_width=True)
            if st.button("👨‍💻 Developer Profile", key="top_dev_btn", use_container_width=True):
                st.session_state.active_page = "developer"
                st.rerun()

    st.divider()

    # =========================================================
    # PAGE 1: CHAT INTERFACE
    # =========================================================
    if st.session_state.active_page == "chat":
        
        if not st.session_state.messages:
            st.markdown(f"<h3 style='text-align: center; margin-top: 20px;'>Hi {username}! 👋</h3>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #8E8E93;'>Apne Doubts, PDF Notes, ya Exam Questions upload karke solution paayein!</p>", unsafe_allow_html=True)

        for msg in st.session_state.messages:
            if msg["role"] == "user":
                st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-ai">{msg["content"]}</div>', unsafe_allow_html=True)

        st.markdown("<div style='clear: both;'></div>", unsafe_allow_html=True)

        # PDF & Photo Attachment Button
        with st.popover("📎 Attach PDF Notes / Photo Problem"):
            st.markdown("### Attach Document / Image")
            attach_type = st.radio("Choose Mode:", ["PDF Exam Solver", "Photo Problem Solver"])

            if attach_type == "PDF Exam Solver":
                uploaded_pdf = st.file_uploader("Upload PDF Notes:", type=["pdf"])
                pdf_feature = st.selectbox("Output Format:", ["⚡ Quick Revision Notes", "🎯 Important Exam Questions", "🧪 Practice Quiz (MCQs)"])
                
                if uploaded_pdf and st.button("🚀 Process PDF", type="primary", use_container_width=True):
                    reader = PdfReader(io.BytesIO(uploaded_pdf.getvalue()))
                    page_count = len(reader.pages)
                    
                    if page_count > 3 and not is_pro:
                        st.error("🔒 Free version me maximum 3 pages allowed hain! Upgrade to Pro for unlimited pages.")
                    else:
                        max_pages = page_count if is_pro else min(page_count, 3)
                        extracted_text = "".join([p.extract_text() or "" for p in reader.pages[:max_pages]])
                        prompt_text = f"Analyze document and generate '{pdf_feature}':\n\n{extracted_text[:80000]}"
                        
                        st.session_state.messages.append({"role": "user", "content": f"📂 Analyzed PDF: {uploaded_pdf.name}"})
                        with st.spinner("Processing PDF..."):
                            res = call_ai(prompt_text)
                            st.session_state.messages.append({"role": "assistant", "content": res})
                        st.rerun()

            elif attach_type == "Photo Problem Solver":
                if not is_pro:
                    st.error("🔒 Photo Solver feature Pro version me available hai.")
                else:
                    uploaded_img = st.file_uploader("Upload Image:", type=["jpg", "png", "jpeg"])
                    if uploaded_img and st.button("⚡ Solve Photo Question", type="primary", use_container_width=True):
                        img = Image.open(uploaded_img)
                        st.session_state.messages.append({"role": "user", "content": f"📷 Photo Question Uploaded"})
                        with st.spinner("Solving Question..."):
                            res = call_ai("Solve this question with step-by-step detail:", image=img)
                            st.session_state.messages.append({"role": "assistant", "content": res})
                        st.rerun()

        # Chat Input Bar
        user_prompt = st.chat_input("Kuch bhi puchein...")
        st.markdown(f"<div class='plan-notice'>Plan Mode: {'Pro (Unlimited PDF Pages)' if is_pro else 'Free Tier (Max 3 Pages per PDF)'}</div>", unsafe_allow_html=True)

        if user_prompt:
            st.session_state.messages.append({"role": "user", "content": user_prompt})
            with st.spinner("Thinking..."):
                res = call_ai(user_prompt)
                st.session_state.messages.append({"role": "assistant", "content": res})
            st.rerun()

    # =========================================================
    # PAGE 2: ABOUT APP & PLANS
    # =========================================================
    elif st.session_state.active_page == "about":
        st.markdown(f"## 📱 About {app_display_name} & Membership Plans")
        st.write("Student AI platform specially built for students to solve exam questions, generate revision notes, and analyze PDF study materials instantly.")
        st.divider()

        col_f1, col_f2 = st.columns(2)

        with col_f1:
            st.markdown("""
            <div class="feature-card">
                <h3>🆓 Free Version (Student AI)</h3>
                <ul>
                    <li><b>Unlimited Text Chat</b>: Ask doubts anytime.</li>
                    <li><b>PDF Page Limit</b>: Strictly <b>3 Pages</b> per document.</li>
                    <li><b>Standard AI Speed</b>.</li>
                    <li><b>Photo Solver</b>: Not Included.</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

        with col_f2:
            st.markdown("""
            <div class="feature-card" style="border: 1px solid #38BDF8;">
                <h3 style="color: #38BDF8;">👑 Pro Version (Student AI Pro)</h3>
                <ul>
                    <li><b>Unlimited PDF Pages</b>: Scans 100+ page books & syllabus.</li>
                    <li><b>Photo Question Solver</b>: Upload photos of math & science questions.</li>
                    <li><b>Priority High Speed Response</b>.</li>
                    <li><b>Dedicated Support</b>.</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

        if not is_pro:
            st.link_button("💳 Upgrade to Student AI Pro (₹79/Mo)", RAZORPAY_PAY_LINK, type="primary", use_container_width=True)

    # =========================================================
    # PAGE 3: DEVELOPER PROFILE PAGE
    # =========================================================
    elif st.session_state.active_page == "developer":
        st.markdown("## 👨‍💻 Developer Profile")
        st.divider()

        dev_col1, dev_col2 = st.columns([1, 2])

        with dev_col1:
            st.markdown("""
            <div style="text-align: center; padding: 20px; background-color: #121212; border-radius: 12px; border: 1px solid #222;">
                <div style="font-size: 60px;">🛡️</div>
                <h3 style="margin-bottom: 0px;">Cyber Gaurav</h3>
                <p style="color: #38BDF8; font-size: 14px;">Lead Developer & AI Creator</p>
            </div>
            """, unsafe_allow_html=True)

        with dev_col2:
            st.markdown("""
            ### About the Developer
            **Cyber Gaurav** is a developer and student innovator dedicated to creating accessible AI tools for students.

            - **Project Name**: Student AI / Student AI Pro
            - **Mission**: Making exam preparation and study note extraction effortless using AI models.
            - **Tech Stack**: Python, Streamlit, OpenRouter API, SQLite3, Custom Dark UI.
            """)
            st.link_button("💬 Contact Developer on WhatsApp", "https://wa.me/910000000000", use_container_width=True)
