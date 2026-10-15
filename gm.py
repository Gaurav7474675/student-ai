import streamlit as st
import streamlit.components.v1 as components
import requests
from pypdf import PdfReader
from PIL import Image
from google import genai
import os
import base64
import io
import psycopg2
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
import time

# =========================================================
# 1. PAGE CONFIG & STYLES
# =========================================================
st.set_page_config(
    page_title="Student AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
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

# Clean & Safe Secrets Loader Function
def get_env_or_secret(key, default=""):
    try:
        val = st.secrets.get(key)
        if val:
            return val
    except Exception:
        pass
    return os.environ.get(key, default)

# Load Secrets Safely
PRO_PASSCODE = get_env_or_secret("PRO_PASSCODE", "")
APP_PASSWORD = get_env_or_secret("APP_PASSWORD", "")
RAZORPAY_KEY_ID = get_env_or_secret("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = get_env_or_secret("RAZORPAY_KEY_SECRET", "")
DB_URL = get_env_or_secret("DATABASE_URL", "")
GEMINI_API_KEY = get_env_or_secret("GEMINI_API_KEY", "")
MAX_FREE_QUESTIONS = 5 
# =========================================================
# 3. DATABASE & USAGE TRACKING (POSTGRESQL / SUPABASE)
# =========================================================
def get_db_connection():
    if not DB_URL:
        st.error("DATABASE_URL environment secret is missing!")
        st.stop()
    return psycopg2.connect(DB_URL)

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def init_db():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
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
                c.execute('''CREATE TABLE IF NOT EXISTS pro_keys (
                    key_code TEXT PRIMARY KEY, is_used INTEGER DEFAULT 0, 
                    used_by TEXT, created_at TEXT)''')
            conn.commit()
    except Exception as e:
        st.error(f"Database Initialization Error: {e}")

init_db()

def generate_unique_pro_key():
    """Generates a random unique single-use key and saves to DB"""
    new_key = f"PRO-{secrets.token_hex(4).upper()}"
    created_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO pro_keys (key_code, is_used, created_at) VALUES (%s, 0, %s)",
                         (new_key, created_time))
        conn.commit()
    return new_key

def redeem_pro_key(user_code, username):
    """Redeems passcode and enforces single-use policy"""
    code_clean = user_code.strip().upper()
    
    if code_clean == PRO_PASSCODE:
        expiry_date, _ = update_pro_status(username, code_clean)
        return True, f"🎉 Master Admin Key Accepted! PRO Active till {expiry_date}"

    with get_db_connection() as conn:
        with conn.cursor() as c:
            c.execute("SELECT is_used, used_by FROM pro_keys WHERE key_code=%s", (code_clean,))
            row = c.fetchone()
            
            if not row:
                return False, "❌ Invalid Passcode! Key match nahi hui."
            
            if row[0] == 1:
                return False, f"❌ Ye Key Pehle Hi Kisi User (@{row[1]}) Dwara Use Ho Chuki Hai!"

            c.execute("UPDATE pro_keys SET is_used=1, used_by=%s WHERE key_code=%s", (username, code_clean))
        conn.commit()
        
    expiry_date, _ = update_pro_status(username, code_clean)
    return True, f"🎉 Success! Unique Passcode Verified. PRO Active till {expiry_date}"

def register_user(username, password, email):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO users (username, password, email, is_pro) VALUES (%s, %s, %s, 0)",
                          (username, hash_password(password), email))
            conn.commit()
        return True, "Account Created! Please Login."
    except psycopg2.IntegrityError:
        return False, "Username Already Exists!"
    except Exception as e:
        return False, f"Registration Error: {str(e)}"

def validate_login(username, password):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                c.execute("SELECT username, email FROM users WHERE username=%s AND password=%s",
                          (username, hash_password(password)))
                return c.fetchone()
    except Exception:
        return None

def update_pro_status(username, key_used="SYSTEM_AUTO", days=30):
    expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE users SET is_pro=1, pro_expiry=%s, passcode=%s WHERE username=%s",
                         (expiry_date, key_used, username))
        conn.commit()
    return expiry_date, key_used

def check_user_pro_validity(username):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as c:
                c.execute("SELECT is_pro, pro_expiry, passcode FROM users WHERE username=%s", (username,))
                row = c.fetchone()
                if not row or row[0] == 0 or not row[1]:
                    return False, "Free Tier", 0, None
                expiry_dt = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
                if datetime.now() > expiry_dt:
                    c.execute("UPDATE users SET is_pro=0 WHERE username=%s", (username,))
                    conn.commit()
                    return False, "Expired", 0, None
                days_left = (expiry_dt - datetime.now()).days
                return True, row[1], max(0, days_left), row[2]
    except Exception:
        return False, "Free Tier", 0, None

def get_today_question_count(username):
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db_connection() as conn:
        with conn.cursor() as c:
            c.execute("SELECT count FROM usage_tracker WHERE username=%s AND usage_date=%s", (username, today))
            row = c.fetchone()
            return row[0] if row else 0

def increment_question_count(username):
    today = datetime.now().strftime("%Y-%m-%d")
    current = get_today_question_count(username)
    with get_db_connection() as conn:
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO usage_tracker (username, usage_date, count) 
                VALUES (%s, %s, %s)
                ON CONFLICT (username, usage_date) 
                DO UPDATE SET count = EXCLUDED.count
            """, (username, today, current + 1))
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
                with conn.cursor() as c:
                    c.execute("""
                        INSERT INTO payments (order_id, username, status, timestamp) 
                        VALUES (%s, %s, 'CREATED', %s)
                        ON CONFLICT (order_id) DO NOTHING
                    """, (order["id"], username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
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
        with conn.cursor() as c:
            c.execute("SELECT status FROM payments WHERE order_id=%s", (order_id,))
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

            auto_key = f"PRO-RZP-{secrets.token_hex(4).upper()}"
            created_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("INSERT INTO pro_keys (key_code, is_used, used_by, created_at) VALUES (%s, 1, %s, %s)",
                         (auto_key, username, created_time))
            c.execute("UPDATE payments SET payment_id=%s, signature=%s, status='PAID' WHERE order_id=%s",
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
# 6. GEMINI AI CLIENT
# =========================================================
def get_gemini_client():
    gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        return None
    gemini_key = str(gemini_key).strip().replace('"', '').replace("'", "")
    return genai.Client(api_key=gemini_key)

def call_ai(prompt, image=None):
    client = get_gemini_client()
    if client is None:
        return "⚠️ Gemini API key missing hai. Streamlit Secrets check karein."

    contents = []
    if image:
        contents.append(image)
    contents.append(str(prompt)[:15000])

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents
            )
            if response and response.text:
                return response.text
            return "⚠️ AI ne koi response nahi diya."
        except Exception as e:
            error_text = str(e)
            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                return (
                    "⚠️ **Student AI quota temporarily exhausted.**\n\n"
                    "Google Gemini ki current API quota limit reach ho gayi hai. "
                    "Ye Student AI ke 5-question limit ka issue nahi hai.\n\n"
                    "Please try again after the Gemini quota resets."
                )
            if ("503" in error_text or "UNAVAILABLE" in error_text) and attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return f"⚠️ Gemini service error: {error_text}"
    return "⚠️ AI service temporarily unavailable. Please try again."

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
# 8. MAIN APP DASHBOARD & PAGES
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

    with st.expander("💳 Upgrade / Activate Pro", expanded=not is_pro):
        if is_pro:
            st.success(f"PRO Active! Days Left: {days_left}")
            if passcode_key:
                st.code(f"Passcode: {passcode_key}")
        else:
            st.markdown("### 👑 Go Pro - ₹79 Only")
            st.write("Unlock unlimited questions & priority speed for 30 days!")
            
            if st.button("🚀 Pay ₹79 via Razorpay", use_container_width=True):
                order = create_razorpay_order(username)
                if order:
                    render_razorpay_checkout(order, username, get_app_url())
                else:
                    st.error("Razorpay order create nahi ho paya. Keys check karein.")

            st.markdown("---")
            st.markdown("**Or Pay via UPI / QR:**")
            st.image(PAYMENT_QR_URL, use_container_width=True)
            st.markdown(f"[💬 Send Payment Screenshot on Telegram]({TELEGRAM_LINK})")

            st.markdown("---")
            entered_key = st.text_input("🔑 Enter Pro Passcode", type="password")
            if st.button("Verify Passcode", use_container_width=True):
                ok, msg = redeem_pro_key(entered_key, username)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()

    if username in ["admin", "Gaurav", "Gg"] or is_pro:
        with st.expander("⚙️ Admin Tools (Key Gen)"):
            if st.button("Generate New PRO Key"):
                k = generate_unique_pro_key()
                st.success(f"New Key Generated: `{k}`")

    st.divider()
    if st.button("🚪 Log Out", use_container_width=True):
        st.session_state.is_logged_in = False
        st.session_state.messages = []
        st.rerun()

# =========================================================
# PAGE 1: CHAT AI INTERFACE
# =========================================================
if st.session_state.active_page == "chat":
    st.markdown(f"""
        <div class="top-bar-custom">
            <div class="app-title-text">Hi {username}! 👋</div>
            <div>
                <span style="font-size:12px; color:#888;">Plan Mode:</span>
                <span class="pro-badge">{'PRO' if is_pro else 'Free Tier'}</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    st.caption("Apne Doubts, PDF Notes, ya Exam Questions upload karke solution paayein!")

    uploaded_file = st.file_uploader("📎 Attach PDF Notes / Photo Problem", type=["png", "jpg", "jpeg", "pdf"])

    # Render previous messages
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-ai">{msg["content"]}</div>', unsafe_allow_html=True)

    user_query = st.chat_input("Kuch bhi puchein...")

    if user_query:
        if not is_pro and used_questions >= MAX_FREE_QUESTIONS:
            st.error("🚨 Aaj ka aapka 5 free questions ka limit khatm ho gaya hai! Unlimited access ke liye sidebar se PRO upgrade karein.")
            st.stop()

        st.session_state.messages.append({"role": "user", "content": user_query})
        st.markdown(f'<div class="chat-user">{user_query}</div>', unsafe_allow_html=True)

        extracted_text = ""
        pil_img = None

        if uploaded_file:
            if uploaded_file.type == "application/pdf":
                try:
                    pdf_reader = PdfReader(uploaded_file)
                    for page in pdf_reader.pages:
                        t = page.extract_text()
                        if t:
                            extracted_text += t + "\n"
                except Exception:
                    pass
            else:
                try:
                    pil_img = Image.open(uploaded_file)
                except Exception:
                    pass

        full_prompt = user_query
        if extracted_text:
            full_prompt = f"Context from uploaded PDF:\n{extracted_text[:4000]}\n\nQuestion: {user_query}"

        with st.spinner("🧠 AI Thinking..."):
            ai_reply = call_ai(full_prompt, image=pil_img)

        if not is_pro:
            increment_question_count(username)

        st.session_state.messages.append({"role": "assistant", "content": ai_reply})
        st.markdown(f'<div class="chat-ai">{ai_reply}</div>', unsafe_allow_html=True)
        st.rerun()

# =========================================================
# PAGE 2: ABOUT APP & PLANS
# =========================================================
elif st.session_state.active_page == "about":
    st.markdown("## 📱 About Student AI & Plans")
    st.write("Student AI ek advanced educational assistant hai jo students ko unke homework, study notes, aur exam preparations mein madad karta hai.")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
            <div class="feature-card">
                <h3>🆓 Free Plan</h3>
                <p>• 5 Questions daily free limit</p>
                <p>• AI Chat & Image problem solver</p>
                <p>• Basic PDF text extraction</p>
            </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
            <div class="feature-card">
                <h3>👑 PRO Plan (₹79 / Month)</h3>
                <p>• <b>Unlimited Questions</b> (No daily cap)</p>
                <p>• Priority AI model speed</p>
                <p>• Advanced PDF & Image analysis</p>
                <p>• 30 Days full validity</p>
            </div>
        """, unsafe_allow_html=True)

# =========================================================
# PAGE 3: DEVELOPER PROFILE
# =========================================================
elif st.session_state.active_page == "developer":
    col_d1, col_d2 = st.columns([1, 2])
    with col_d1:
        st.image(PROFILE_IMG_URL, use_container_width=True)
    with col_d2:
        st.markdown("## 👨‍💻 Developer Profile")
        st.write("**Name:** Gaurav")
        st.write("**Expertise:** Full-Stack Developer & AI Systems")
        st.write("Student AI ko students ke liye study ko aasan banane ke liye banaya gaya hai.")
        st.markdown(f"[💬 Contact on Telegram]({TELEGRAM_LINK})")
