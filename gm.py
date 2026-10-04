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
from datetime import datetime, timedelta

# =========================================================
# 1. PAGE CONFIG & STYLES
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
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. CONFIG & SECRETS
# =========================================================
PRO_PASSCODE = st.secrets.get("PRO_PASSCODE") or os.environ.get("PRO_PASSCODE") or "GMCYBER2026"

RAZORPAY_KEY_ID = st.secrets.get("RAZORPAY_KEY_ID") or os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = st.secrets.get("RAZORPAY_KEY_SECRET") or os.environ.get("RAZORPAY_KEY_SECRET", "")
PRO_PRICE_PAISE = 7900  # ₹79

TELEGRAM_LINK = "https://t.me/pintu9389"
PAYMENT_QR_URL = "https://raw.githubusercontent.com/Gaurav7474675/student-ai/main/payment_qr.png"
PROFILE_IMG_URL = "https://raw.githubusercontent.com/Gaurav7474675/student-ai/main/profile.jpeg"

DB_FILE = "users_database.db"
MAX_FREE_QUESTIONS = 5

# =========================================================
# 3. DATABASE & USAGE TRACKING WITH SINGLE-USE KEYS
# =========================================================
def get_db_connection():
    return sqlite3.connect(DB_FILE, timeout=15)

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, password TEXT, email TEXT,
            is_pro INTEGER DEFAULT 0, pro_expiry TEXT, passcode TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS transactions (
            txn_id TEXT PRIMARY KEY, username TEXT, status TEXT, timestamp TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS payments (
            order_id TEXT PRIMARY KEY, username TEXT, payment_id TEXT,
            signature TEXT, status TEXT, timestamp TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS usage_tracker (
            username TEXT, usage_date TEXT, count INTEGER DEFAULT 0,
            PRIMARY KEY (username, usage_date))''')
        # Table for storing one-time single-use Pro Passcodes
        c.execute('''CREATE TABLE IF NOT EXISTS pro_keys (
            key_code TEXT PRIMARY KEY, is_used INTEGER DEFAULT 0, 
            used_by TEXT, created_at TEXT)''')
        conn.commit()

init_db()

def generate_unique_pro_key():
    """Generates a random unique single-use key and saves to DB"""
    new_key = f"PRO-{secrets.token_hex(4).upper()}"
    created_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        conn.execute("INSERT INTO pro_keys (key_code, is_used, created_at) VALUES (?, 0, ?)",
                     (new_key, created_time))
        conn.commit()
    return new_key

def redeem_pro_key(user_code, username):
    """Redeems passcode and enforces single-use policy"""
    code_clean = user_code.strip().upper()
    
    # Check Master Admin Key
    if code_clean == PRO_PASSCODE:
        expiry_date, _ = update_pro_status(username, code_clean)
        return True, f"🎉 Master Admin Key Accepted! PRO Active till {expiry_date}"

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT is_used, used_by FROM pro_keys WHERE key_code=?", (code_clean,))
        row = c.fetchone()
        
        if not row:
            return False, "❌ Invalid Passcode! Key match nahi hui."
        
        if row[0] == 1:
            return False, f"❌ Ye Key Pehle Hi Kisi User (@{row[1]}) Dwara Use Ho Chuki Hai!"

        # Key is valid -> mark as used and activate Pro
        conn.execute("UPDATE pro_keys SET is_used=1, used_by=? WHERE key_code=?", (username, code_clean))
        conn.commit()
        
    expiry_date, _ = update_pro_status(username, code_clean)
    return True, f"🎉 Success! Unique Passcode Verified. PRO Active till {expiry_date}"

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

def update_pro_status(username, key_used="SYSTEM_AUTO", days=30):
    expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        conn.execute("UPDATE users SET is_pro=1, pro_expiry=?, passcode=? WHERE username=?",
                     (expiry_date, key_used, username))
        conn.commit()
    return expiry_date, key_used

def check_user_pro_validity(username):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT is_pro, pro_expiry, passcode FROM users WHERE username=?", (username,))
            row = c.fetchone()
            if not row or row[0] == 0 or not row[1]:
                return False, "Free Tier", 0, None
            expiry_dt = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
            if datetime.now() > expiry_dt:
                conn.execute("UPDATE users SET is_pro=0 WHERE username=?", (username,))
                conn.commit()
                return False, "Expired", 0, None
            days_left = (expiry_dt - datetime.now()).days
            return True, row[1], max(0, days_left), row[2]
    except Exception:
        return False, "Free Tier", 0, None

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
# 4. RAZORPAY PAYMENT SYSTEM
# =========================================================
def create_razorpay_order(username):
    try:
        resp = requests.post(
            "https://api.razorpay.com/v1/orders",
            auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
            json={"amount": PRO_PRICE_PAISE, "currency": "INR",
                  "receipt": f"STUAI-{username}-{secrets.token_hex(4)}"},
            timeout=30)
        if resp.status_code == 200:
            order = resp.json()
            with get_db_connection() as conn:
                conn.execute("INSERT OR REPLACE INTO payments (order_id, username, status, timestamp) VALUES (?, ?, 'CREATED', ?)",
                             (order["id"], username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
            return order
        return None
    except Exception:
        return None

def verify_razorpay_signature(order_id, payment_id, signature):
    if not (RAZORPAY_KEY_SECRET and order_id and payment_id and signature):
        return False
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

def process_verified_payment(order_id, payment_id, signature, username):
    if not verify_razorpay_signature(order_id, payment_id, signature):
        return False, "❌ Payment signature verification FAILED!", None
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT status FROM payments WHERE order_id=?", (order_id,))
        row = c.fetchone()
        if row and row[0] == "PAID":
            return False, "⚠️ Ye payment pehle se verify ho chuka hai!", None
        
        try:
            pr = requests.get(f"https://api.razorpay.com/v1/payments/{payment_id}",
                              auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET), timeout=30)
            if pr.status_code == 200:
                pdata = pr.json()
                if pdata.get("status") != "captured" or pdata.get("order_id") != order_id:
                    return False, "❌ Payment capture nahi hua!", None
            else:
                return False, "❌ Razorpay verification failed.", None
        except Exception as e:
            return False, f"❌ Error: {str(e)}", None

        # Auto-generate unique key for Razorpay payment
        auto_key = f"PRO-RZP-{secrets.token_hex(4).upper()}"
        created_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO pro_keys (key_code, is_used, used_by, created_at) VALUES (?, 1, ?, ?)",
                     (auto_key, username, created_time))
        conn.execute("UPDATE payments SET payment_id=?, signature=?, status='PAID' WHERE order_id=?",
                     (payment_id, signature, order_id))
        conn.commit()
        
    expiry, pass_key = update_pro_status(username, auto_key, days=30)
    return True, f"🎉 Payment Verified! Pro Active Till {expiry}!", pass_key

def render_razorpay_checkout(order, username, app_url):
    checkout_html = f"""
    <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
    <div id="rzp-status" style="color:#fff;font-family:sans-serif;text-align:center;">Opening Razorpay Secure Checkout...</div>
    <script>
    var rzp = new Razorpay({{
        key: "{RAZORPAY_KEY_ID}",
        amount: "{order['amount']}",
        currency: "INR",
        name: "Student AI Pro",
        description: "30 Days Pro Membership - ₹79",
        order_id: "{order['id']}",
        prefill: {{ "name": "{username}" }},
        theme: {{ "color": "#38BDF8" }},
        handler: function(resp) {{
            var base = "{app_url}";
            var sep = base.indexOf("?") === -1 ? "?" : "&";
            window.parent.location.href = base + sep +
                "rzp_payment=" + resp.razorpay_payment_id +
                "&rzp_order=" + resp.razorpay_order_id +
                "&rzp_sig=" + resp.razorpay_signature;
        }},
        modal: {{ ondismiss: function() {{
            document.getElementById("rzp-status").innerText = "Payment cancelled.";
        }}}}
    }});
    rzp.open();
    </script>
    """
    components.html(checkout_html, height=150)

# =========================================================
# 5. SESSION & APP STATE
# =========================================================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "active_page" not in st.session_state:
    st.session_state.active_page = "chat"
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False

def get_app_url():
    try:
        headers = st.context.headers
        host = headers.get("Host", "localhost:8501")
        proto = "https" if "streamlit.app" in host or headers.get("X-Forwarded-Proto") == "https" else "http"
        return f"{proto}://{host}/"
    except Exception:
        return "http://localhost:8501/"

rzp_payment = st.query_params.get("rzp_payment")
rzp_order = st.query_params.get("rzp_order")
rzp_sig = st.query_params.get("rzp_sig")
if rzp_payment and rzp_order and rzp_sig:
    st.query_params.clear()
    if st.session_state.get("is_logged_in"):
        ok, msg, pk = process_verified_payment(rzp_order, rzp_payment, rzp_sig,
                                               st.session_state.user_data["username"])
        st.session_state.rzp_result = (ok, msg, pk)
        st.rerun()

# =========================================================
# 6. FAST & RELIABLE AI ENGINE
# =========================================================
def call_ai(prompt, image=None):
    gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    
    if not gemini_key or "YOUR_" in gemini_key:
        return "⚠️ Gemini API Key Missing! Secrets.toml mein GEMINI_API_KEY set karein."
    
    gemini_key = str(gemini_key).strip().replace('"', '').replace("'", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
    headers = {"Content-Type": "application/json"}
    
    parts = []
    if image:
        try:
            buffered = io.BytesIO()
            image.thumbnail((800, 800))
            image.save(buffered, format="JPEG", quality=75)
            img_str = base64.b64encode(buffered.getvalue()).decode()
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": img_str
                }
            })
        except Exception as img_err:
            return f"Image Processing Error: {str(img_err)}"
            
    parts.append({"text": prompt[:15000]})
    payload = {"contents": [{"parts": parts}]}
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        if response.status_code == 200:
            res_json = response.json()
            return res_json["candidates"][0]["content"]["parts"][0]["text"]
        elif response.status_code == 503:
            return "⚠️ Server busy (503 High Demand). Kripya 10 second baad dobara try karein."
        else:
            return f"Gemini API Error ({response.status_code}): {response.text}"
    except requests.exceptions.Timeout:
        return "⚠️ Timeout Error. Request lene mein zyaada time laga, dobara try karein."
    except Exception as e:
        return f"Network Error: {str(e)}"

# =========================================================
# 7. AUTH SCREEN (LOGIN & REGISTER)
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
# 8. MAIN APP DASHBOARD
# =========================================================
username = st.session_state.user_data["username"]
is_pro, expiry_info, days_left, passcode_key = check_user_pro_validity(username)
app_display_name = "Student AI Pro" if is_pro else "Student AI"

used_questions = get_today_question_count(username)
remaining_questions = max(0, MAX_FREE_QUESTIONS - used_questions)

with st.sidebar:
    st.markdown(f"### 🛡️ {app_display_name}")
    st.caption(f"Logged as **@{username}** ({'👑 PRO' if is_pro else '🆓 Free Plan'})")
    if not is_pro:
        st.info(f"📊 **Today's Free Usage**: {used_questions}/{MAX_FREE_QUESTIONS} Questions Used")
    st.divider()

    if st.button("💬 Chat AI Interface", use_container_width=True):
        st.session_state.active_page = "chat"; st.rerun()
    if st.button("📱 About App & Plans", use_container_width=True):
        st.session_state.active_page = "about"; st.rerun()
    if st.button("👨‍💻 Developer Profile", use_container_width=True):
        st.session_state.active_page = "developer"; st.rerun()
    st.divider()

    # SECRET ADMIN PANEL TO GENERATE KEYS
    if username.lower() == "admin":
        st.markdown("### 🔑 Admin Key Generator")
        if st.button("Generate New Unique Pro Key", type="primary", use_container_width=True):
            gen_key = generate_unique_pro_key()
            st.success("New Key Generated!")
            st.code(gen_key)
            st.caption("Is key ko code me paste kare")
