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
# 1. PAGE CONFIG & EXACT CHATGPT MOBILE UI STYLES
# =========================================================
st.set_page_config(
    page_title="ChatGPT - Student AI",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    /* CSS Reset */
    #MainMenu, footer, header {visibility: hidden !important;}
    div[data-testid="stHeader"], div[data-testid="stToolbar"], div[data-testid="stDecoration"], div[data-testid="stStatusWidget"] {display: none !important;}

    /* Modern Pitch-Black Background */
    .stApp {
        background-color: #000000 !important;
        color: #FFFFFF !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    /* ChatGPT Mobile Style Drawer Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #0D0D0D !important;
        border-right: 1px solid #1A1A1A !important;
        width: 300px !important;
    }

    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 7rem !important;
        max-width: 800px !important;
    }

    /* Top ChatGPT Header Bar */
    .top-bar-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 0px 16px 0px;
        border-bottom: 1px solid #1A1A1A;
        margin-bottom: 15px;
    }

    .model-selector {
        font-size: 18px;
        font-weight: 600;
        color: #FFFFFF;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .pro-offer-btn {
        background-color: #1E1E1E;
        color: #38BDF8;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        text-decoration: none;
        border: 1px solid #2B2B2B;
    }

    /* ChatGPT Chat Bubbles */
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

    /* Floating ChatGPT Input Box Styling */
    .stChatInputContainer {
        padding-bottom: 15px !important;
    }
    
    .stChatInput > div {
        background-color: #171717 !important;
        border: 1px solid #2F2F2F !important;
        border-radius: 28px !important;
    }

    /* Sidebar Menu Custom Formatting */
    .sidebar-menu-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 12px;
        color: #E3E3E3;
        font-size: 14px;
        border-radius: 8px;
        margin-bottom: 4px;
    }

    .sidebar-section-title {
        color: #666666;
        font-size: 12px;
        font-weight: 600;
        margin-top: 15px;
        margin-bottom: 8px;
        padding-left: 10px;
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
# 3. REFRESH & SESSION PERSISTENCE
# =========================================================
if "messages" not in st.session_state:
    st.session_state.messages = []

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
        st.markdown("<h2 style='text-align:center;'>💬 ChatGPT Login</h2>", unsafe_allow_html=True)
        st.caption("<p style='text-align:center;'>Student AI Pro Edition</p>", unsafe_allow_html=True)
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
# 6. MAIN CHATGPT INTERFACE SCREEN
# =========================================================
else:
    username = st.session_state.user_data["username"]
    is_pro, expiry_info, days_left, passcode_key = check_user_pro_validity(username)

    # --- CHATGPT SIDEBAR DRAWER MENU ---
    with st.sidebar:
        if st.button("➕  Nai Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

        st.markdown("""
        <div style="margin-top: 10px;">
            <div class="sidebar-menu-item">🖼️ <span>Images</span></div>
            <div class="sidebar-menu-item">📚 <span>Library</span></div>
            <div class="sidebar-menu-item">📅 <span>Scheduled</span></div>
            <div class="sidebar-menu-item">🎡 <span>Playgrounds</span></div>
            <div class="sidebar-menu-item">📁 <span>Projects</span></div>
            <div class="sidebar-menu-item">💻 <span>Codex</span></div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="sidebar-section-title">Haliya Chats</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="sidebar-menu-item">💬 Greeting response</div>
        <div class="sidebar-menu-item">💬 Casual greeting</div>
        <div class="sidebar-menu-item">💬 Student AI Study Plan</div>
        """, unsafe_allow_html=True)

        st.divider()

        # DEVELOPER PROFILE MODAL
        with st.expander("👨‍💻 Developer Profile"):
            st.write("**Cyber Gaurav**")
            st.caption("Ethical Hacker & Lead Student Developer")
            st.link_button("💬 Connect WhatsApp", "https://wa.me/910000000000", use_container_width=True)

        # PRO PLAN UPGRADE & VERIFICATION
        with st.expander("🎁 Get PRO / Upgrade Option"):
            st.write(f"**Current Status:** {'👑 PRO' if is_pro else '🆓 Free Plan'}")
            if is_pro:
                st.write(f"**Days Left:** {days_left}")
                st.write(f"**Passcode:** `{passcode_key}`")
            else:
                st.write("**Unlock Pro Limits (₹79/Month)**")
                st.link_button("💳 Pay ₹79 via Razorpay", RAZORPAY_PAY_LINK, use_container_width=True)
                
                txn_input = st.text_input("Enter 12-Digit Ref ID / Key:", key="pro_key_input")
                if st.button("Activate Pro", use_container_width=True):
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

        st.markdown(f"<div style='margin-top:20px; font-size:12px; color:#888;'>Logged as <b>@{username}</b> ({'PRO' if is_pro else 'Free'})</div>", unsafe_allow_html=True)

    # --- TOP CHATGPT NAVIGATION BAR ---
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.markdown("""
        <div class="model-selector">
            <span>ChatGPT</span> <span style="font-size:12px; color:#888;">▼</span>
        </div>
        """, unsafe_allow_html=True)
    with col_t2:
        # VISIBLE PRO UPGRADE LINK ON MAIN APP TOP BAR
        st.markdown(f"""
        <div style="text-align: right;">
            <a href="{RAZORPAY_PAY_LINK}" target="_blank" class="pro-offer-btn">🎁 Free Offer / Upgrade Pro</a>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # Empty State Greeting
    if not st.session_state.messages:
        st.markdown(f"<h3 style='text-align: center; margin-top: 40px;'>Hi {username}! 👋</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #8E8E93;'>Kya bana rahe ho aaj? 🚀</p>", unsafe_allow_html=True)

    # Render Chat Flow
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-ai">{msg["content"]}</div>', unsafe_allow_html=True)

    st.markdown("<div style='clear: both;'></div>", unsafe_allow_html=True)

    # PDF & IMAGE TOOL ATTACHMENT POPOVER
    with st.popover("📎 Attach PDF Notes / Photo Question"):
        st.markdown("### Attach Document / Image")
        attach_type = st.radio("Choose Mode:", ["PDF Exam Solver", "Photo Problem Solver"])

        if attach_type == "PDF Exam Solver":
            uploaded_pdf = st.file_uploader("Upload PDF Notes:", type=["pdf"])
            pdf_feature = st.selectbox("Output Select Karein:", ["⚡ Quick Revision Notes", "🎯 Important Exam Questions", "🧪 Practice Quiz (MCQs)"])
            
            if uploaded_pdf and st.button("🚀 Solve / Process PDF", type="primary", use_container_width=True):
                reader = PdfReader(io.BytesIO(uploaded_pdf.getvalue()))
                page_count = len(reader.pages)
                
                if page_count > 3 and not is_pro:
                    st.error("🔒 Free tier max 3 pages limit! Upgrade to PRO in top bar.")
                else:
                    max_p = min(page_count, 3) if not is_pro else page_count
                    extracted_text = "".join([p.extract_text() or "" for p in reader.pages[:max_p]])
                    prompt_text = f"Analyze document and generate '{pdf_feature}':\n\n{extracted_text[:80000]}"
                    
                    st.session_state.messages.append({"role": "user", "content": f"📂 Analyzed PDF: {uploaded_pdf.name}"})
                    with st.spinner("Processing PDF..."):
                        res = call_ai(prompt_text)
                        st.session_state.messages.append({"role": "assistant", "content": res})
                    st.rerun()

        elif attach_type == "Photo Problem Solver":
            if not is_pro:
                st.error("🔒 Photo Solver requires PRO version. Upgrade from Top Bar / Sidebar.")
            else:
                uploaded_img = st.file_uploader("Upload Image:", type=["jpg", "png", "jpeg"])
                if uploaded_img and st.button("⚡ Solve Photo Question", type="primary", use_container_width=True):
                    img = Image.open(uploaded_img)
                    st.session_state.messages.append({"role": "user", "content": f"📷 Photo Question Uploaded"})
                    with st.spinner("Solving..."):
                        res = call_ai("Solve this problem image with detailed logic:", image=img)
                        st.session_state.messages.append({"role": "assistant", "content": res})
                    st.rerun()

    # MAIN CHAT INPUT CONTAINER
    user_prompt = st.chat_input("Kuch bhi puchein...")

    if user_prompt:
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.spinner("Thinking..."):
            res = call_ai(user_prompt)
            st.session_state.messages.append({"role": "assistant", "content": res})
        st.rerun()
