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
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. CONFIG & SECRETS
# =========================================================
api_key = st.secrets.get("OPENROUTER_API_KEY") or st.secrets.get("GEMINI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
PRO_PASSCODE = st.secrets.get("PRO_PASSCODE") or os.environ.get("PRO_PASSCODE") or "GMCYBER2026"

RAZORPAY_KEY_ID = st.secrets.get("RAZORPAY_KEY_ID") or os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = st.secrets.get("RAZORPAY_KEY_SECRET") or os.environ.get("RAZORPAY_KEY_SECRET", "")
PRO_PRICE_PAISE = 7900  # ₹79

PAYMENT_QR_URL = "https://raw.githubusercontent.com/Gaurav7474675/student-ai/main/payment_qr.png"

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
    return f"PRO-{secrets.token_hex(4).upper()}"

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, password TEXT, email TEXT,
            is_pro INTEGER DEFAULT 0, pro_expiry TEXT, passcode TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS transactions (
            txn_id TEXT PRIMARY KEY, username TEXT, status TEXT, timestamp TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY, username TEXT, created_at TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS payments (
            order_id TEXT PRIMARY KEY, username TEXT, payment_id TEXT,
            signature TEXT, status TEXT, timestamp TEXT)''')
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

def update_pro_status(username, days=30):
    expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    new_passcode = generate_passcode()
    with get_db_connection() as conn:
        conn.execute("UPDATE users SET is_pro=1, pro_expiry=?, passcode=? WHERE username=?",
                     (expiry_date, new_passcode, username))
        conn.commit()
    return expiry_date, new_passcode

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
            return False, "⚠️ Ye payment pehle se use ho chuka hai!", None
        
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

        conn.execute("UPDATE payments SET payment_id=?, signature=?, status='PAID' WHERE order_id=?",
                     (payment_id, signature, order_id))
        conn.commit()
    expiry, pass_key = update_pro_status(username, days=30)
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
# 5. SESSION & APP URL HELPERS
# =========================================================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "active_page" not in st.session_state:
    st.session_state.active_page = "chat"

cookies = CookieController()
SESSION_COOKIE = "student_ai_session"

def get_app_url():
    try:
        headers = st.context.headers
        host = headers.get("Host", "localhost:8501")
        proto = "https" if "streamlit.app" in host or headers.get("X-Forwarded-Proto") == "https" else "http"
        return f"{proto}://{host}/"
    except Exception:
        return "http://localhost:8501/"

if not st.session_state.get("is_logged_in", False):
    cookie_token = cookies.get(SESSION_COOKIE)
    user_rec = get_user_from_token(cookie_token)
    if user_rec:
        st.session_state.is_logged_in = True
        st.session_state.user_data = {"username": user_rec[0], "email": user_rec[1]}
        st.rerun()

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
# =========================================================
# 6. AI ENGINE (DIRECT GEMINI API)
# =========================================================
def call_ai(prompt, image=None):
    # Secrets se Gemini key uthayein
    gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    
    if not gemini_key or "YOUR_" in gemini_key:
        return "⚠️ Gemini API Key Missing! Secrets.toml mein GEMINI_API_KEY set karein."
    
    gemini_key = gemini_key.strip().replace('"', '').replace("'", "")
    
    # Gemini 2.5 Flash API Endpoint
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
    headers = {"Content-Type": "application/json"}
    
    parts = []
    
    # Agar image upload hui hai
    if image:
        try:
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": img_str
                }
            })
        except Exception as img_err:
            return f"Image Processing Error: {str(img_err)}"
            
    # Text Prompt Add Karein
    parts.append({"text": prompt})
    
    payload = {
        "contents": [{
            "parts": parts
        }]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            res_json = response.json()
            return res_json["candidates"][0]["content"]["parts"][0]["text"]
        else:
            return f"Gemini API Error ({response.status_code}): {response.text}"
    except requests.exceptions.Timeout:
        return "⚠️ Timeout Error. Kripya punah prayas karein."
    except Exception as e:
        return f"Network Error: {str(e)}"


# =========================================================
# 7. LOGIN / REGISTER SCREEN
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

    with st.expander("💳 Upgrade / Activate Pro", expanded=not is_pro):
        if is_pro:
            st.success(f"PRO Active! Days Left: {days_left}")
            if passcode_key:
                st.code(f"Passcode: {passcode_key}")
        else:
            st.write("🔥 **Unlock Unlimited Direct Questions, Unlimited PDF Pages & Photo Solver!**")
            
            st.image(PAYMENT_QR_URL, caption="Scan QR to Pay ₹79", use_container_width=True)
            st.markdown("""
            **Pro Version Activate Karne Ka Tareeka:**
            1. QR Code par ₹79 ka payment karein.
            2. Screenshot aur Username admin ko bhejein.
            3. Received Passcode neeche daal kar activate karein.
            """)

            if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
                if st.button("💳 Pay ₹79 Securely (Auto-Verify)", type="primary", use_container_width=True):
                    order = create_razorpay_order(username)
                    if order:
                        st.session_state.rzp_order = order
                    else:
                        st.error("Order creation failed. Check Razorpay credentials.")
                if st.session_state.get("rzp_order"):
                    render_razorpay_checkout(st.session_state.rzp_order, username, get_app_url())
            else:
                st.info("Direct online payment ke alawa aap Passcode se bhi activate kar sakte hain.")
            
            admin_code = st.text_input("Admin Passcode:", key="side_admin_key")
            if st.button("Activate via Passcode", use_container_width=True):
                if admin_code.strip() == PRO_PASSCODE:
                    exp, pass_k = update_pro_status(username)
                    st.success("🎉 Passcode Accepted! PRO Activated.")
                    st.rerun()
                else:
                    st.error("❌ Invalid Passcode!")

    if st.button("🚪 Logout Account", use_container_width=True):
        delete_session_token(cookies.get(SESSION_COOKIE))
        cookies.set(SESSION_COOKIE, "", max_age=0)
        st.session_state.is_logged_in = False
        st.session_state.user_data = None
        st.rerun()

if st.session_state.get("rzp_result"):
    ok, msg, pk = st.session_state.rzp_result
    (st.success if ok else st.error)(msg)
    if ok and pk:
        st.code(f"Your Passcode Key: {pk}")
    st.session_state.rzp_result = None

# --- TOP HEADER BAR ---
h_col1, h_col2, h_col3 = st.columns([1, 4, 1])
with h_col1:
    with st.popover("☰ Menu"):
        st.markdown("### Navigation Drawer")
        if st.button("💬 Chat Interface", key="pop_chat", use_container_width=True):
            st.session_state.active_page = "chat"; st.rerun()
        if st.button("📱 About & Plans", key="pop_about", use_container_width=True):
            st.session_state.active_page = "about"; st.rerun()
        if st.button("👨‍💻 Developer Profile", key="pop_dev", use_container_width=True):
            st.session_state.active_page = "developer"; st.rerun()
with h_col2:
    pro_tag = '<span class="pro-badge">PRO</span>' if is_pro else ''
    st.markdown(f"<div style='text-align:center;'><span class='app-title-text'>🛡️ {app_display_name}</span>{pro_tag}</div>", unsafe_allow_html=True)
with h_col3:
    with st.popover("⋮ More"):
        st.markdown(f"**User:** @{username}")
        st.caption(f"Status: {'👑 PRO Active' if is_pro else '🆓 Free Plan'}")
        st.divider()
        if st.button("👨‍💻 Developer Profile", key="top_dev_btn", use_container_width=True):
            st.session_state.active_page = "developer"; st.rerun()

st.divider()

# --- PAGE 1: CHAT ---
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
                        st.error("🔒 Free version mein maximum 3 pages allowed hain! Pro lein unlimited pages ke liye.")
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
                st.error("🔒 Photo Solver feature strictly Pro version me available hai!")
            else:
                uploaded_img = st.file_uploader("Upload Image:", type=["jpg", "png", "jpeg"])
                if uploaded_img and st.button("⚡ Solve Photo Question", type="primary", use_container_width=True):
                    try:
                        img = Image.open(uploaded_img)
                        st.session_state.messages.append({"role": "user", "content": "📷 Photo Question Uploaded"})
                        with st.spinner("Solving Question..."):
                            res = call_ai("Solve this question with step-by-step detail:", image=img)
                            st.session_state.messages.append({"role": "assistant", "content": res})
                        st.rerun()
                    except Exception as img_err:
                        st.error(f"Error processing image: {str(img_err)}")

    if not is_pro and used_questions >= MAX_FREE_QUESTIONS:
        st.error("🚨 **Daily Limit Reached!** Aapne aaj ke 5 Free Questions complete kar liye hain.")
        st.markdown("""
        <div style="background-color: #1E1010; border: 2px solid #FF4D4D; border-radius: 12px; padding: 20px; text-align: center; margin-top: 10px; margin-bottom: 25px;">
            <h2 style="color: #FF4D4D; margin-top: 0;">🔒 Upgrade to Pro to Continue</h2>
            <p style="color: #CCCCCC; font-size: 15px;">Aaj ki daily limit (5 Questions) poori ho chuki hai. Unlimited questions, Photo Question Solver, aur full PDF scanning ke liye abhi <b>Pro Upgrade</b> karein!</p>
            <h3 style="color: #FFD700;">Kewal ₹79 / Month</h3>
        </div>
        """, unsafe_allow_html=True)
        
        if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
            if st.button("👑 Unlock Unlimited Questions (Pay ₹79)", type="primary", use_container_width=True):
                order = create_razorpay_order(username)
                if order:
                    st.session_state.rzp_order = order
                else:
                    st.error("Order create nahi ho saka.")
            if st.session_state.get("rzp_order"):
                render_razorpay_checkout(st.session_state.rzp_order, username, get_app_url())
        else:
            st.info("Payment setup karne ke liye secrets.toml mein Razorpay Keys dalein.")
    else:
        user_prompt = st.chat_input("Kuch bhi puchein...")
        status_text = "Plan Mode: Pro (Unlimited Access)" if is_pro else f"Plan Mode: Free Tier ({remaining_questions} Questions Left Today)"
        st.markdown(f"<div class='plan-notice'>{status_text}</div>", unsafe_allow_html=True)

        if user_prompt:
            st.session_state.messages.append({"role": "user", "content": user_prompt})
            if not is_pro:
                increment_question_count(username)
            with st.spinner("Thinking..."):
                res = call_ai(user_prompt)
                st.session_state.messages.append({"role": "assistant", "content": res})
            st.rerun()

# --- PAGE 2: ABOUT ---
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
                <li><b>Daily Limit</b>: Maximum <b>5 Direct Questions/Day</b>.</li>
                <li><b>PDF Page Limit</b>: Strictly <b>3 Pages</b> per document.</li>
                <li><b>Standard Speed</b>.</li>
                <li><b>Photo Solver</b>: Not Included.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    with col_f2:
        st.markdown("""
        <div class="feature-card" style="border: 1px solid #38BDF8;">
            <h3 style="color: #38BDF8;">👑 Pro Version (Student AI Pro)</h3>
            <ul>
                <li><b>Unlimited Questions</b>: Koi daily limit nahi.</li>
                <li><b>Unlimited PDF Scanning</b>: Complete books & syllabus extract karein.</li>
                <li><b>Photo Question Solver</b>: Math/Science photos ka instant answer.</li>
                <li><b>Fast Response Speed</b>.</li>
                <li><b>Secure Auto-Verified Payment</b>.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    st.divider()

    if not is_pro:
        st.subheader("💳 Activate Pro Membership (Auto-Verified)")
        
        qr_col1, qr_col2 = st.columns([1, 2])
        with qr_col1:
            st.image(PAYMENT_QR_URL, caption="Scan QR & Pay ₹79", width=220)
        with qr_col2:
            st.markdown("""
            ### 📌 How to Activate Pro Version:
            1. **QR Code Scan Karein**: Diye gaye QR code ko kisi bhi UPI App se scan karke **₹79** ka payment karein.
            2. **Screenshot Bhejein**: Payment ka screenshot aur apna registered **Username** developer ko WhatsApp par bhejein.
            3. **Passcode Enter Karein**: Admin dwara praapt Passcode ko neeche box mein daal kar **Activate via Admin Passcode** par click karein.
            """)
        st.divider()

        st.info("✅ Direct Razorpay payment auto-verify hoti hai.")
        if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
            if st.button("💳 Pay ₹79 Securely Now", type="primary", use_container_width=True):
                order = create_razorpay_order(username)
                if order:
                    st.session_state.rzp_order = order
                else:
                    st.error("Order creation failed.")
            if st.session_state.get("rzp_order"):
                render_razorpay_checkout(st.session_state.rzp_order, username, get_app_url())
        else:
            st.warning("Razorpay keys absent. QR Payment ya Passcode use karein.")
        
        admin_code = st.text_input("Admin Passcode (special):", key="about_admin_key")
        if st.button("⚡ Activate via Admin Passcode", use_container_width=True):
            if admin_code.strip() == PRO_PASSCODE:
                exp, pass_k = update_pro_status(username)
                st.success(f"🎉 Admin Passcode Accepted! PRO Active till {exp}")
                st.rerun()
            else:
                st.error("❌ Invalid Admin Passcode!")
    else:
        st.success(f"🎉 Pro Active! Days Left: {days_left}")
        if passcode_key:
            st.code(f"Passcode Key: {passcode_key}")

# --- PAGE 3: DEVELOPER ---
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
        - **Tech Stack**: Python, Streamlit, OpenRouter API, SQLite3, Razorpay Integration.
        """)
        st.link_button("💬 Contact Developer on WhatsApp", "https://wa.me/910000000000", use_container_width=True)
