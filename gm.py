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
import streamlit.components.v1 as components

# =========================================================
# 1. PAGE CONFIG & MODERN UI STYLES
# =========================================================
st.set_page_config(
    page_title="Student AI Pro",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
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
        width: 300px !important;
    }

    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 6rem !important;
        max-width: 850px !important;
    }

    /* Header & Large Title Styling */
    .main-app-header {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        padding: 10px 0;
        margin-bottom: 15px;
        border-bottom: 1px solid #1A1A1A;
    }

    .app-title-large {
        font-size: 26px !important;
        font-weight: 800 !important;
        color: #FFFFFF !important;
        letter-spacing: 0.5px;
    }

    .pro-badge {
        background: linear-gradient(135deg, #FFD700 0%, #FF8C00 100%);
        color: #000000;
        font-size: 11px;
        font-weight: 800;
        padding: 3px 8px;
        border-radius: 6px;
        text-transform: uppercase;
    }

    /* Chat Bubbles */
    .chat-user {
        background-color: #212121;
        color: #FFFFFF;
        padding: 12px 18px;
        border-radius: 20px;
        margin-bottom: 12px;
        float: right;
        clear: both;
        max-width: 82%;
        font-size: 15px;
        line-height: 1.5;
    }

    .chat-ai {
        color: #ECECF1;
        padding: 6px 0px 14px 0px;
        margin-bottom: 12px;
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
        font-size: 12px;
        color: #888888;
        text-align: center;
        margin-top: 6px;
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
DB_FILE = "users_database.db"

def get_db_connection():
    return sqlite3.connect(DB_FILE, timeout=10)

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def generate_session_token():
    return secrets.token_hex(24)

def init_db():
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password TEXT,
                    email TEXT,
                    is_pro INTEGER DEFAULT 0,
                    pro_expiry TEXT,
                    session_token TEXT
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS active_sessions (
                    token TEXT PRIMARY KEY,
                    username TEXT,
                    last_active TEXT
                )
            ''')
            conn.commit()
    except Exception as e:
        st.error(f"Database Error: {str(e)}")

init_db()

def register_user(username, password, email):
    hashed_p = hash_password(password)
    token = generate_session_token()
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password, email, is_pro, session_token) VALUES (?, ?, ?, 0, ?)",
                      (username, hashed_p, email, token))
            conn.commit()
            return True, "Account Created Successfully!", token
    except sqlite3.IntegrityError:
        return False, "Username Already Exists!", None
    except Exception as e:
        return False, f"Registration Error: {str(e)}", None

def validate_login(username, password):
    hashed_p = hash_password(password)
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT username, email, is_pro, session_token FROM users WHERE username=? AND password=?", (username, hashed_p))
            row = c.fetchone()
            if row:
                token = generate_session_token()
                c.execute("UPDATE users SET session_token=? WHERE username=?", (token, username))
                c.execute("INSERT OR REPLACE INTO active_sessions VALUES (?, ?, ?)", 
                          (token, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                return row[0], row[1], token
            return None
    except Exception:
        return None

def verify_session_token(token):
    if not token:
        return None
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT username, email FROM users WHERE session_token=?", (token,))
            return c.fetchone()
    except Exception:
        return None

def update_pro_status(username, days=30):
    expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET is_pro=1, pro_expiry=? WHERE username=?", (expiry_date, username))
            conn.commit()
        return True, expiry_date
    except Exception as e:
        return False, str(e)

def check_user_pro_validity(username):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT is_pro, pro_expiry FROM users WHERE username=?", (username,))
            row = c.fetchone()
            if not row or row[0] == 0 or not row[1]:
                return False, "Free Tier", 0
            
            expiry_dt = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
            if datetime.now() > expiry_dt:
                c.execute("UPDATE users SET is_pro=0 WHERE username=?", (username,))
                conn.commit()
                return False, "Expired", 0
            
            days_left = (expiry_dt - datetime.now()).days
            return True, row[1], max(0, days_left)
    except Exception:
        return False, "Free Tier", 0

# =========================================================
# 3. AUTO-LOGIN / PERSISTENT SESSION SYSTEM
# =========================================================
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "user_data" not in st.session_state:
    st.session_state.user_data = None

# Query Parameter check for Session Auto-Recovery
auth_token = st.query_params.get("st_token", None)

if not st.session_state.is_logged_in and auth_token:
    user_info = verify_session_token(auth_token)
    if user_info:
        st.session_state.is_logged_in = True
        st.session_state.user_data = {"username": user_info[0], "email": user_info[1], "token": auth_token}

# JavaScript bridge to save token in browser localStorage & URL
def keep_session_alive(token):
    js_code = f"""
    <script>
        localStorage.setItem("student_ai_token", "{token}");
        const url = new URL(window.location.href);
        if (url.searchParams.get("st_token") !== "{token}") {{
            url.searchParams.set("st_token", "{token}");
            window.history.replaceState({{}}, "", url);
        }}
    </script>
    """
    components.html(js_code, height=0)

if not st.session_state.is_logged_in and not auth_token:
    js_restore = """
    <script>
        const savedToken = localStorage.getItem("student_ai_token");
        if (savedToken) {
            const url = new URL(window.location.href);
            if (!url.searchParams.get("st_token")) {
                url.searchParams.set("st_token", savedToken);
                window.location.href = url.toString();
            }
        }
    </script>
    """
    components.html(js_restore, height=0)

# =========================================================
# 4. AI ENGINE (OPENROUTER / GEMINI)
# =========================================================
def call_ai(prompt, image=None):
    if not api_key:
        return "⚠️ API Key Missing! Secrets me GEMINI_API_KEY add karein."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    content_payload = [{"type": "text", "text": prompt}]

    if image:
        try:
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            content_payload.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_str}"}
            })
        except Exception as img_err:
            return f"Image Processing Error: {str(img_err)}"

    payload = {
        "model": "google/gemini-2.5-flash",
        "messages": [{"role": "user", "content": content_payload}],
        "max_tokens": 2000
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        return f"API Error ({response.status_code}): {response.text}"
    except Exception as e:
        return f"Network Error: {str(e)}"

# =========================================================
# 5. AUTHENTICATION UI
# =========================================================
if not st.session_state.is_logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align:center; font-size:32px;'>🛡️ Student AI Pro</h1>", unsafe_allow_html=True)
        st.caption("<p style='text-align:center;'>Sign in to continue learning</p>", unsafe_allow_html=True)
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
                    u_name, u_email, u_token = user
                    st.session_state.is_logged_in = True
                    st.session_state.user_data = {"username": u_name, "email": u_email, "token": u_token}
                    st.query_params["st_token"] = u_token
                    keep_session_alive(u_token)
                    st.success("Login Successful!")
                    st.rerun()
                else:
                    st.error("❌ Invalid Username or Password")

        with auth_tab2:
            with st.form(key="reg_form"):
                reg_email = st.text_input("📧 Email")
                reg_user = st.text_input("Username")
                reg_pass = st.text_input("Password", type="password")
                submit_reg = st.form_submit_button("Sign Up", type="primary", use_container_width=True)

            if submit_reg:
                if reg_user and reg_pass and reg_email:
                    success, msg, u_token = register_user(reg_user.strip(), reg_pass.strip(), reg_email.strip())
                    if success:
                        st.session_state.is_logged_in = True
                        st.session_state.user_data = {"username": reg_user.strip(), "email": reg_email.strip(), "token": u_token}
                        st.query_params["st_token"] = u_token
                        keep_session_alive(u_token)
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

# =========================================================
# 6. MAIN APPLICATION DASHBOARD
# =========================================================
else:
    username = st.session_state.user_data["username"]
    token = st.session_state.user_data["token"]
    keep_session_alive(token)

    is_pro, expiry_info, days_left = check_user_pro_validity(username)
    app_display_name = "Student AI Pro" if is_pro else "Student AI"

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "active_page" not in st.session_state:
        st.session_state.active_page = "chat"

    # --- SIDEBAR NAVIGATION ---
    with st.sidebar:
        st.markdown(f"### 🛡️ {app_display_name}")
        st.caption(f"Logged in as: **@{username}**")
        st.markdown(f"Plan: **{'👑 PRO' if is_pro else '🆓 Free Plan'}**")
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

        # Pro Activation Section in Sidebar
        with st.expander("⚡ Activate / Upgrade Pro"):
            if is_pro:
                st.success(f"PRO Active! Days Left: {days_left}")
            else:
                st.link_button("💳 Pay ₹79 via Razorpay", RAZORPAY_PAY_LINK, use_container_width=True)
                st.markdown("---")
                passcode_input = st.text_input("Enter Passcode / UTR Key:", key="side_pass_in")
                if st.button("Activate Pro Mode", use_container_width=True):
                    if passcode_input.strip() == PRO_PASSCODE:
                        ok, exp = update_pro_status(username)
                        if ok:
                            st.success("🎉 Pro Plan Activated!")
                            st.rerun()
                    else:
                        st.error("❌ Invalid Passcode / Key!")

        if st.button("🚪 Logout Account", use_container_width=True):
            st.session_state.is_logged_in = False
            st.session_state.user_data = None
            st.query_params.clear()
            components.html("<script>localStorage.removeItem('student_ai_token');</script>", height=0)
            st.rerun()

    # --- CLEAN & CENTERED TOP TITLE BAR ---
    pro_tag_html = '<span class="pro-badge">PRO</span>' if is_pro else ''
    st.markdown(
        f"""
        <div class="main-app-header">
            <span style="font-size: 28px;">🛡️</span>
            <span class="app-title-large">{app_display_name}</span>
            {pro_tag_html}
        </div>
        """, 
        unsafe_allow_html=True
    )

    # =========================================================
    # PAGE 1: CHAT INTERFACE
    # =========================================================
    if st.session_state.active_page == "chat":
        if not st.session_state.messages:
            st.markdown(f"<h3 style='text-align: center; margin-top: 15px;'>Hi {username}! 👋</h3>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #8E8E93;'>Apne Doubts, PDF Notes, ya Exam Questions upload karke solution paayein!</p>", unsafe_allow_html=True)

        for msg in st.session_state.messages:
            if msg["role"] == "user":
                st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-ai">{msg["content"]}</div>', unsafe_allow_html=True)

        st.markdown("<div style='clear: both;'></div>", unsafe_allow_html=True)

        # Attachment Popover
        with st.popover("📎 Attach PDF Notes / Photo Problem"):
            st.markdown("### Attach Document / Image")
            attach_type = st.radio("Choose Mode:", ["PDF Exam Solver", "Photo Problem Solver"])

            if attach_type == "PDF Exam Solver":
                uploaded_pdf = st.file_uploader("Upload PDF Notes:", type=["pdf"])
                pdf_feature = st.selectbox("Output Format:", ["⚡ Quick Revision Notes", "🎯 Important Exam Questions", "🧪 Practice Quiz (MCQs)"])
                
                if uploaded_pdf and st.button("🚀 Process PDF", type="primary", use_container_width=True):
                    try:
                        reader = PdfReader(io.BytesIO(uploaded_pdf.getvalue()))
                        page_count = len(reader.pages)
                        
                        if page_count > 3 and not is_pro:
                            st.error("🔒 Free version mein maximum 3 pages allowed hain! Pro version mein Upgrade karein.")
                        else:
                            max_pages = page_count if is_pro else min(page_count, 3)
                            extracted_text = "".join([p.extract_text() or "" for p in reader.pages[:max_pages]])
                            prompt_text = f"Analyze document and generate '{pdf_feature}':\n\n{extracted_text[:80000]}"
                            
                            st.session_state.messages.append({"role": "user", "content": f"📂 Analyzed PDF: {uploaded_pdf.name}"})
                            with st.spinner("Processing PDF..."):
                                res = call_ai(prompt_text)
                                st.session_state.messages.append({"role": "assistant", "content": res})
                            st.rerun()
                    except Exception as pdf_err:
                        st.error(f"Error parsing PDF: {str(pdf_err)}")

            elif attach_type == "Photo Problem Solver":
                if not is_pro:
                    st.error("🔒 Photo Solver feature Pro version mein available hai.")
                else:
                    uploaded_img = st.file_uploader("Upload Image:", type=["jpg", "png", "jpeg"])
                    if uploaded_img and st.button("⚡ Solve Photo Question", type="primary", use_container_width=True):
                        try:
                            img = Image.open(uploaded_img)
                            st.session_state.messages.append({"role": "user", "content": f"📷 Photo Question Uploaded"})
                            with st.spinner("Solving Question..."):
                                res = call_ai("Solve this question with step-by-step detail:", image=img)
                                st.session_state.messages.append({"role": "assistant", "content": res})
                            st.rerun()
                        except Exception as img_err:
                            st.error(f"Error processing image: {str(img_err)}")

        user_prompt = st.chat_input("Kuch bhi puchein...")
        st.markdown(f"<div class='plan-notice'>Plan Mode: {'Pro (Unlimited PDF Pages & Photo Solver)' if is_pro else 'Free Tier (Max 3 Pages per PDF)'}</div>", unsafe_allow_html=True)

        if user_prompt:
            st.session_state.messages.append({"role": "user", "content": user_prompt})
            with st.spinner("Thinking..."):
                res = call_ai(user_prompt)
                st.session_state.messages.append({"role": "assistant", "content": res})
            st.rerun()

    # =========================================================
    # PAGE 2: ABOUT APP & PRO UPGRADE
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
                    <li><b>Instant Activation</b>.</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

        st.divider()

        if not is_pro:
            st.subheader("💳 Activate Pro Membership")
            st.link_button("💳 Pay ₹79 via Razorpay", RAZORPAY_PAY_LINK, type="primary", use_container_width=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            with st.form("about_pro_activate_form"):
                passcode_key_input = st.text_input("Enter Passcode Key / Activation Code:", placeholder="Enter your key here...")
                submit_key = st.form_submit_button("⚡ Activate Pro Plan Now", type="primary", use_container_width=True)

            if submit_key:
                if passcode_key_input.strip() == PRO_PASSCODE:
                    ok, exp = update_pro_status(username)
                    if ok:
                        st.success(f"🎉 Pro Plan Activated Successfully! Valid till: {exp}")
                        st.rerun()
                else:
                    st.error("❌ Invalid Passcode / Key! Correct Key Enter Karein.")
        else:
            st.success(f"🎉 Pro Active! Days Left: {days_left}")

    # =========================================================
    # PAGE 3: DEVELOPER PROFILE PAGE
    # =========================================================
    elif st.session_state.active_page == "developer":
        st.markdown("## 👨‍💻 Developer Profile")
        st.divider()

        dev_col1, dev_col2 = st.columns([1, 2])

        PROFILE_IMG_URL = "https://raw.githubusercontent.com/Gaurav7474675/student-ai/main/profile.jpeg"

        with dev_col1:
            st.markdown(f"""
            <div style="text-align: center; padding: 20px; background-color: #121212; border-radius: 12px; border: 1px solid #222;">
                <img src="{PROFILE_IMG_URL}" style="width: 110px; height: 110px; border-radius: 50%; object-fit: cover; border: 2px solid #38BDF8; margin-bottom: 10px;">
                <h3 style="margin-bottom: 0px;">Cyber Gaurav</h3>
                <p style="color: #38BDF8; font-size: 14px; margin-top: 4px;">Lead Developer & AI Creator</p>
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
