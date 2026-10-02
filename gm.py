import streamlit as st
import streamlit.components.v1 as components
import requests
from pypdf import PdfReader
from PIL import Image
import os
import base64
import io
import sqlite3
import hashlib
import hmac
import secrets
import json
from datetime import datetime, timedelta
from streamlit_cookies_controller import CookieController

# =========================================================
# 1. PAGE CONFIG & UI STYLES
# =========================================================
st.set_page_config(
    page_title="Student AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    #MainMenu, footer, header {visibility: hidden !important;}
    div[data-testid="stHeader"], div[data-testid="stToolbar"], div[data-testid="stDecoration"], div[data-testid="stStatusWidget"] {display: none !important;}
    .stApp {
        background-color: #000000 !important;
        color: #FFFFFF !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    section[data-testid="stSidebar"] {
        background-color: #0D0D0D !important;
        border-right: 1px solid #1A1A1A !important;
        width: 310px !important;
    }
    .block-container { padding-top: 0.5rem !important; padding-bottom: 7rem !important; max-width: 820px !important; }
    .top-bar-custom { display:flex; justify-content:space-between; align-items:center; padding-bottom:10px; border-bottom:1px solid #1F1F1F; margin-bottom:15px; }
    .app-title-text { font-size: 19px; font-weight: 700; color: #FFFFFF; }
    .pro-badge { background: linear-gradient(135deg, #FFD700 0%, #FF8C00 100%); color:#000; font-size:10px; font-weight:800; padding:2px 6px; border-radius:4px; margin-left:6px; }
    .chat-user { background-color:#212121; color:#FFF; padding:12px 18px; border-radius:22px; margin-bottom:14px; float:right; clear:both; max-width:82%; font-size:15px; line-height:1.5; }
    .chat-ai { color:#ECECF1; padding:4px 0px 14px 0px; margin-bottom:14px; float:left; clear:both; width:100%; font-size:15px; line-height:1.6; }
    .stChatInput > div { background-color:#171717 !important; border:1px solid #2F2F2F !important; border-radius:28px !important; }
    .plan-notice { font-size:12px; color:#FFA500; text-align:center; margin-top:6px; font-weight:600; }
    .feature-card { background-color:#121212; border:1px solid #222; padding:20px; border-radius:12px; margin-bottom:15px; }
    .payment-instruction { background-color:#1A1A1A; border:1px solid #333; padding:15px; border-radius:8px; margin-top:10px; }
    .step-number { background-color:#333; color:#FFF; padding:2px 7px; border-radius:50%; font-weight:bold; margin-right:5px; }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. CONFIG & SECRETS (Razorpay keys removed)
# =========================================================
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
PRO_PASSCODE = st.secrets.get("PRO_PASSCODE") or os.environ.get("PRO_PASSCODE") or "GMCYBER2026"

# Telegram contact link
TELEGRAM_LINK = "http://t.me/pintu9389"
QR_IMAGE_PATH = "payment_qr.png" # GitHub par upload ki hui image ka naam

DB_FILE = "users_database.db"
MAX_FREE_QUESTIONS = 5

# =========================================================
# 3. DATABASE & USAGE TRACKING
# =========================================================
def get_db_connection():
    return sqlite3.connect(DB_FILE, timeout=10)

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def generate_passcode():
    """Generates a unique passcode to give to the user."""
    return f"PRO-{secrets.token_hex(4).upper()}"

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, password TEXT, email TEXT,
            is_pro INTEGER DEFAULT 0, pro_expiry TEXT, passcode TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY, username TEXT, created_at TEXT)''')
        # Questions usage tracking table
        c.execute('''CREATE TABLE IF NOT EXISTS usage_tracker (
            username TEXT, usage_date TEXT, count INTEGER DEFAULT 0,
            PRIMARY KEY (username, usage_date))''')
        conn.commit()

init_db()

def register_user(username, password, email):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password, email, is_pro) VALUES (?, ?, ?, 0)",
                      (username, hash_password(password), email))
            conn.commit()
        return True, "Account Created! Please Login."
    except sqlite3.IntegrityError:
        return False, "Username Already Exists!"
    except Exception as e:
        return False, f"Registration Error: {str(e)}"

def validate_login(username, password):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT username, email FROM users WHERE username=? AND password=?",
                      (username, hash_password(password)))
            return c.fetchone()
    except Exception:
        return None

def create_session_token(username):
    token = secrets.token_urlsafe(32)
    with get_db_connection() as conn:
        conn.execute("INSERT INTO sessions (token, username, created_at) VALUES (?, ?, ?)",
                     (token, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    return token

def get_user_from_token(token):
    if not token:
        return None
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT username FROM sessions WHERE token=?", (token,))
            row = c.fetchone()
            if not row:
                return None
            c.execute("SELECT username, email FROM users WHERE username=?", (row[0],))
            return c.fetchone()
    except Exception:
        return None

def delete_session_token(token):
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()
    except Exception:
        pass

def activate_pro_manual(username, passcode_entered, days=30):
    """Activates PRO status if the user enters the master passcode."""
    if passcode_entered == PRO_PASSCODE:
        expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        # We use a special marker for manually activated accounts
        with get_db_connection() as conn:
            conn.execute("UPDATE users SET is_pro=1, pro_expiry=?, passcode='MANUAL_ACTIVATE' WHERE username=?",
                         (expiry_date, username))
            conn.commit()
        return True, expiry_date
    return False, None

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
                conn.execute("UPDATE users SET is_pro=0 WHERE username=?", (username,))
                conn.commit()
                return False, "Expired", 0
            days_left = (expiry_dt - datetime.now()).days
            return True, row[1], max(0, days_left)
    except Exception:
        return False, "Free Tier", 0

# --- DAILY QUESTION COUNTER LOGIC ---
def get_today_question_count(username):
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT count FROM usage_tracker WHERE username=? AND usage_date=?", (username, today))
        row = c.fetchone()
        return row[0] if row else 0

def increment_question_count(username):
    today = datetime.now().strftime("%Y-%m-%d")
    current = get_today_question_count(username)
    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO usage_tracker (username, usage_date, count) VALUES (?, ?, ?)",
                     (username, today, current + 1))
        conn.commit()

# =========================================================
# 4. SESSION & APP URL HELPERS
# =========================================================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "active_page" not in st.session_state:
    st.session_state.active_page = "chat"

cookies = CookieController()
SESSION_COOKIE = "student_ai_session"

if not st.session_state.get("is_logged_in", False):
    cookie_token = cookies.get(SESSION_COOKIE)
    user_rec = get_user_from_token(cookie_token)
    if user_rec:
        st.session_state.is_logged_in = True
        st.session_state.user_data = {"username": user_rec[0], "email": user_rec[1]}
        st.rerun()

# =========================================================
# 5. AI ENGINE
# =========================================================
def call_ai(prompt, image=None):
    if not api_key:
        return "⚠️ API Key Missing! Secrets mein GEMINI_API_KEY set karein."
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    content_payload = [{"type": "text", "text": prompt}]
    if image:
        try:
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            content_payload.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_str}"}})
        except Exception as img_err:
            return f"Image Processing Error: {str(img_err)}"
    payload = {"model": "google/gemini-2.5-flash",
               "messages": [{"role": "user", "content": content_payload}], "max_tokens": 2000}
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        return f"API Error ({response.status_code}): {response.text}"
    except requests.exceptions.Timeout:
        return "⚠️ Timeout Error. Kripya punah prayas karein."
    except Exception as e:
        return f"Network Error: {str(e)}"

# =========================================================
# 6. LOGIN / REGISTER SCREEN
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
                    token = create_session_token(user[0])
                    cookies.set(SESSION_COOKIE, token, max_age=60*60*24*365)
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
                    (st.success if success else st.error)(msg)
                else:
                    st.error("Sabhi fields bharein!")
    st.stop()

# =========================================================
# 7. MAIN APP DASHBOARD
# =========================================================
username = st.session_state.user_data["username"]
is_pro, expiry_info, days_left = check_user_pro_validity(username)
app_display_name = "Student AI Pro" if is_pro else "Student AI"

# Check usage counts
used_questions = get_today_question_count(username)
remaining_free = MAX_FREE_QUESTIONS - used_questions

# --- SIDEBAR NAV ---
with st.sidebar:
    st.markdown(f"### 🛡️ {app_display_name}")
    st.caption(f"Welcome, {username}")
    st.divider()
    
    if st.button("💬 Chat Assistant", use_container_width=True, type="secondary" if st.session_state.active_page=="chat" else "ghost"):
        st.session_state.active_page = "chat"
        st.rerun()
        
    if st.button("📚 My Plan & Upgrade", use_container_width=True, type="secondary" if st.session_state.active_page=="plan" else "ghost"):
        st.session_state.active_page = "plan"
        st.rerun()
        
    st.divider()
    if st.button("🚪 Log Out", use_container_width=True):
        token = cookies.get(SESSION_COOKIE)
        delete_session_token(token)
        cookies.remove(SESSION_COOKIE)
        st.session_state.clear()
        st.rerun()

# =========================================================
# 8. PAGE ROUTING
# =========================================================

# --- TOP BAR ---
st.markdown(f"""
    <div class="top-bar-custom">
        <div class="app-title-text">{app_display_name}{'<span class="pro-badge">PRO</span>' if is_pro else ''}</div>
        <div style="font-size:13px; color:#888;">{datetime.now().strftime("%d %B")}</div>
    </div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Page 1: Chat Assistant
# ---------------------------------------------------------
if st.session_state.active_page == "chat":
    # Display message history
    for message in st.session_state.messages:
        div_class = "chat-user" if message["role"] == "user" else "chat-ai"
        st.markdown(f'<div class="{div_class}">{message["content"]}</div>', unsafe_allow_html=True)

    # Free plan notice
    if not is_pro:
        st.markdown(f'<div class="plan-notice">Free Tier: {remaining_free} questions left today</div>', unsafe_allow_html=True)

    # Chat Input Zone
    st.markdown('<div class="chat-input-spacer"></div>', unsafe_allow_html=True)
    
    # Check if questions available
    can_ask = is_pro or remaining_free > 0
    
    if not can_ask:
        st.error("⚠️ Aaj ki Free limit khatam! Kal fir se puchein ya PRO plan lein.")
        if st.button("Upgrade to PRO now", type="primary"):
            st.session_state.active_page = "plan"
            st.rerun()
    else:
        # File uploader outside form for better UX
        uploaded_file = st.file_uploader("📁 Upload image or PDF (Optional)", type=["png", "jpg", "jpeg", "pdf"], label_visibility="collapsed")
        
        # User input form
        with st.form(key="chat_input_form", clear_on_submit=True):
            cols = st.columns([8, 2])
            user_input = cols[0].text_input("Ask Student AI...", placeholder="Type question or upload file...", label_visibility="collapsed")
            submit_chat = cols[1].form_submit_button("Send", type="primary", use_container_width=True)

        if submit_chat and (user_input or uploaded_file):
            # Record user message
            content_text = user_input if user_input else "Uploaded a file."
            st.session_state.messages.append({"role": "user", "content": content_text})
            
            # Show processing
            with st.spinner("Student AI is thinking..."):
                final_prompt = user_input
                ai_image = None
                
                # Handle file uploader
                if uploaded_file:
                    if uploaded_file.type == "application/pdf":
                        try:
                            reader = PdfReader(uploaded_file)
                            pdf_text = ""
                            for page in reader.pages[:3]: # limit to first 3 pages
                                pdf_text += page.extract_text()
                            final_prompt = f"Context from PDF:\n{pdf_text}\n\nUser Question: {user_input}"
                        except Exception as e:
                            final_prompt = f"Error reading PDF: {str(e)}. Attempted Question: {user_input}"
                    else:
                        # It's an image
                        try:
                            ai_image = Image.open(uploaded_file)
                        except Exception as e:
                            final_prompt = f"Error reading Image: {str(e)}. Attempted Question: {user_input}"

                # Call AI
                response = call_ai(final_prompt, ai_image)
                st.session_state.messages.append({"role": "ai", "content": response})
                
                # Update usage tracker for free users
                if not is_pro:
                    increment_question_count(username)
            
            st.rerun()

# =========================================================
# (Apne pure code mein 'Page 2: My Plan & Upgrade' wala section dhoondein)
# Aur use is corrected code se replace kar dein.
# =========================================================

# ---------------------------------------------------------
# Page 2: My Plan & Upgrade (Manual Telegram Process) - Corrected
# ---------------------------------------------------------
elif st.session_state.active_page == "plan":
    st.markdown("### 📚 Account Subscription")
    
    # Status Card
    if is_pro:
        st.success(f"✅ Aapka PRO Plan Active hai! Expiry: {expiry_info} ({days_left} days left)")
        st.info("💡 Expiry khatam hone par niche diye process se renew karein.")
    else:
        st.warning(f"⚠️ Aap abhi Free Plan use kar rahe hain. ({remaining_free} questions left today)")

    st.divider()
    
    # Master Passcode Activation Section
    st.markdown("#### 🔐 Activate PRO via Passcode")
    st.caption("Agar aapne payment kar diya hai aur admin se Passcode mila hai, toh yahan enter karein.")
    
    with st.form("manual_activate_form"):
        passcode_entered = st.text_input("Enter 10-Digit PRO Passcode", placeholder="E.g., PRO-ABC12345")
        submit_pass = st.form_submit_button("Activate PRO", type="primary")
        
    if submit_pass:
        if passcode_entered:
            # Check master passcode
            ok, expiry = activate_pro_manual(username, passcode_entered.strip())
            if ok:
                st.success(f"🎉 🎉 🎉 PRO Plan Activated Successfully! Valid till {expiry}. System reload ho raha hai...")
                # Page refresh after successful activation
                st.components.v1.html("<script>setTimeout(function(){window.parent.location.reload();}, 3000);</script>", height=1)
            else:
                st.error("❌ Galat Passcode! Kripya sahi code enter karein ya payment screenshot Telegram par send karein.")
        else:
            st.error("Passcode enter karein!")

    st.divider()

    # MANUAL PAYMENT & TELEGRAM SECTION
    st.markdown("#### 🚀 Upgrade to PRO Plan (₹79 / 30 Days)")
    st.caption("Automatic payment band kar diya gaya hai. Ab aap niche diye process se manual payment karke account active kara sakte hain.")

    # --- YAHAN THI ERROR --- Fixed line below:
    pay_col1, pay_col2 = st.columns([1.2, 1])

    with pay_col1:
        st.markdown('<div class="feature-card">', unsafe_allow_html=True)
        st.markdown("💎 **PRO Plan Benefits:**")
        st.markdown("- ✅ Unlimited Daily Questions (No Limit)")
        st.markdown("- ✅ Faster Response AI Model")
        st.markdown("- ✅ Image & PDF Upload Support")
        st.markdown("- ✅ Priority Support via Telegram")
        st.markdown(f"**Price:** ₹79 for 30 Days")
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown("#### 📝 Payment & Activation Process:")
        st.markdown(f"""
            <div class="payment-instruction">
                1️⃣ <span class="step-number">1</span> Saamne diye gaye **UPI QR Code** ko scan karein.<br>
                2️⃣ <span class="step-number">2</span> Kisi bhi UPI app (GPay, PhonePe, Paytm) se **₹79** pay karein.<br>
                3️⃣ <span class="step-number">3</span> Payment successful hone ke baad uska **Screenshot** le lein.<br>
                4️⃣ <span class="step-number">4</span> Niche diye button par click karke mere **Telegram** par Screenshot aur apna **Username** (`{username}`) send karein.<br>
                5️⃣ <span class="step-number">5</span> Main verification ke baad aapko 10-digit ka **Passcode** dunga.<br>
                6️⃣ <span class="step-number">6</span> Us Passcode ko upar wale box mein dalkar **Activate** karein.
            </div>
        """, unsafe_allow_html=True)
        st.write("")
        st.link_button("📤 Send Screenshot on Telegram", TELEGRAM_LINK, type="primary", use_container_width=True)

    with pay_col2:
        st.markdown("<p style='text-align:center; font-weight:bold;'>Scan to Pay ₹79</p>", unsafe_allow_html=True)
        if os.path.exists(QR_IMAGE_PATH):
            try:
                qr_img = Image.open(QR_IMAGE_PATH)
                # Resize image slightly to fit better if needed
                st.image(qr_img, use_container_width=True)
                st.caption("<p style='text-align:center;'>Scan with GPay, PhonePe, Paytm or any UPI app</p>", unsafe_allow_html=True)
            except Exception as pay_err:
                st.error(f"Error loading QR Image: {str(pay_err)}")
        else:
            st.error(f"⚠️ Payment QR Image (`{QR_IMAGE_PATH}`) GitHub par nahi mili! Kripya upload karein.")

    st.divider()
    st.markdown("#### ⚖️ Policy & Terms")
    with st.expander("Payment & Refund Policy"):
        st.write("""
            * **Manual Activation:** Payment screenshot received hone ke baad verification mein 10 minute se 4 ghante tak lag sakte hain. 
            * **Passcode:** Admin dwara diya gaya Passcode sirf ek baar use ho sakta hai. Use kisi aur ke saath share na karein.
            * **No Refund:**PRO Plan ki digital delivery ke baad kisi bhi situation mein refund provide nahi kiya jayega.
            * **Support:** Agar payment ke baad 12 ghante tak passcode nahi milta, toh fir se Telegram par message karein.
        """)
