import streamlit as st
import requests
from pypdf import PdfReader
from PIL import Image
import os
import base64
import io


# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Student AI - GM Cyber",
    page_icon="🛡️",
    layout="centered",
    initial_sidebar_state="expanded"
)


# =========================================================
# API KEY & PASSCODE
# =========================================================
api_key = (
    st.secrets.get("GEMINI_API_KEY")
    or os.environ.get("GEMINI_API_KEY")
)

PRO_PASSCODE = (
    st.secrets.get("PRO_PASSCODE")
    or os.environ.get("PRO_PASSCODE")
    or "GMCYBER2026"
)


# =========================================================
# SESSION STATE
# =========================================================
if "is_pro" not in st.session_state:
    st.session_state.is_pro = False

if "show_pro_popup" not in st.session_state:
    st.session_state.show_pro_popup = False


# =========================================================
# PROFESSIONAL CSS (Smooth & Non-Flashing)
# =========================================================
st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(circle at top left, rgba(25, 45, 80, 0.28), transparent 35%),
                    radial-gradient(circle at top right, rgba(0, 150, 136, 0.10), transparent 30%),
                    #080c14;
        color: #f4f7fb;
    }
    .block-container {
        max-width: 900px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }
    .profile-card {
        background: linear-gradient(145deg, rgba(25, 32, 48, 0.95), rgba(12, 17, 27, 0.95));
        border: 1px solid rgba(100, 116, 139, 0.22);
        border-radius: 18px;
        padding: 20px;
        margin-bottom: 20px;
        text-align: center;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
    }
    .profile-name {
        font-size: 30px;
        font-weight: 800;
        color: #ffffff;
        margin-top: 8px;
    }
    .profile-subtitle {
        color: #aeb7c6;
        font-size: 13px;
        margin-top: 4px;
    }
    .stButton > button {
        width: 100%;
        min-height: 42px;
        border-radius: 10px;
        border: 1px solid #344054;
        background: #111827;
        color: #f8fafc;
        font-weight: 650;
    }
    .stButton > button:hover {
        border-color: #4ade80;
        color: #ffffff;
        background: #172033;
    }
    div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(135deg, #16a34a, #15803d) !important;
        border: 1px solid #22c55e !important;
        color: white !important;
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1320 0%, #080c14 100%);
        border-right: 1px solid #202938;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background: #0d1320;
        border-radius: 12px;
        padding: 4px;
        border: 1px solid #202938;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        color: #aeb7c6;
        font-weight: 600;
        font-size: 13px;
    }
    .stTabs [aria-selected="true"] {
        background: #172033;
        color: #ffffff !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# AI FUNCTION
# =========================================================
def call_ai(prompt, image=None):
    if not api_key:
        raise Exception("GEMINI_API_KEY missing. Please configure Streamlit Secrets.")

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
# PREMIUM DIALOG (Secured & Clean UI)
# =========================================================
@st.dialog("💎 Student AI Pro")
def premium_popup():
    st.markdown("### 👑 Unlock Pro Access")
    st.write("Get full PDF scans, photo solvers, and limitless AI assistance for ₹99/month.")
    
    try:
        st.image("qr.png", caption="Scan & Pay ₹99 via UPI", use_container_width=True)
    except Exception:
        st.info("📱 Pay ₹99 via UPI to: mg@upi")

    passcode_input = st.text_input("🔐 Enter Pro Passcode", type="password", key="dialog_pass_input")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Verify & Unlock", type="primary"):
            if passcode_input == PRO_PASSCODE:
                st.session_state.is_pro = True
                st.session_state.show_pro_popup = False
                st.success("Unlocked Successfully!")
                st.rerun()
            else:
                st.error("Invalid Passcode")
    with col2:
        if st.button("Cancel"):
            st.session_state.show_pro_popup = False
            st.rerun()

if st.session_state.show_pro_popup:
    premium_popup()


# =========================================================
# HEADER PROFILE
# =========================================================
st.markdown('<div class="profile-card">', unsafe_allow_html=True)
try:
    cols = st.columns([1, 1, 1])
    with cols[1]:
        st.image("profile.jpeg", width=90)
except Exception:
    pass

st.markdown(
    """
    <div class="profile-name">🛡️ STUDENT AI</div>
    <div class="profile-subtitle">Created by <b>MG Gangwar</b> | Smart Cyber Assistance & Exam Hub</div>
    </div>
    """,
    unsafe_allow_html=True
)


# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown("## 👑 Account Plan")
    st.markdown("---")
    
    if not st.session_state.is_pro:
        st.info("🆓 Free Plan\n• PDF: First 3 pages\n• Image Solver: Pro\n• Direct Ask: Active")
        if st.button("💎 Upgrade to Pro", type="primary"):
            st.session_state.show_pro_popup = True
            st.rerun()
    else:
        st.success("👑 PRO ACTIVE\nAll restrictions removed.")
        
    st.markdown("---")
    st.markdown("### ✨ Capabilities\n- PDF Analysis\n- Image Solver\n- Instant AI Queries\n- MCQ Generators")


# =========================================================
# MAIN INTERACTION TABS (ChatGPT/Gemini Style Layout)
# =========================================================
tab1, tab2, tab3 = st.tabs(["📂 PDF Notes", "📷 Image Solver", "💬 Direct Ask"])

# --- TAB 1: PDF ---
with tab1:
    uploaded_file = st.file_uploader("Upload Study PDF:", type=["pdf"], key="pdf_up")
    
    pdf_page_count = 0
    if uploaded_file:
        try:
            reader_cnt = PdfReader(io.BytesIO(uploaded_file.getvalue()))
            pdf_page_count = len(reader_cnt.pages)
            if pdf_page_count > 3 and not st.session_state.is_pro:
                st.warning(f"🔒 PDF has {pdf_page_count} pages. Free tier processes 3 pages.")
        except:
            pass

    feature = st.selectbox("Select Output Format:", ["⚡ Quick Revision Notes", "🎯 Exam Questions", "🧪 Practice MCQs", "🛡️ Cyber/Code Analysis"])
    
    if st.button("🚀 Process Document", type="primary", key="proc_pdf"):
        if not uploaded_file:
            st.warning("Please upload a PDF file.")
        elif pdf_page_count > 3 and not st.session_state.is_pro:
            st.session_state.show_pro_popup = True
            st.rerun()
        else:
            with st.spinner("Analyzing document..."):
                reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
                max_p = len(reader.pages) if st.session_state.is_pro else min(3, len(reader.pages))
                extracted_text = "".join([p.extract_text() or "" for p in reader.pages[:max_p]])
                
                prompt = f"Analyze this study text and format as {feature}:\n\n{extracted_text[:10000]}"
                response_text = call_ai(prompt)
                st.markdown("---")
                st.markdown(response_text)

# --- TAB 2: IMAGE SOLVER ---
with tab2:
    uploaded_img = st.file_uploader("Upload Question/Diagram Image:", type=["jpg", "jpeg", "png"], key="img_up")
    img_prompt = st.text_input("Optional instructions for image:", placeholder="e.g. Solve question #2")
    
    if uploaded_img and not st.session_state.is_pro:
        st.session_state.show_pro_popup = True
        st.rerun()
        
    if st.button("🔍 Analyze Image", type="primary", key="proc_img"):
        if not uploaded_img:
            st.warning("Please upload an image first.")
        else:
            with st.spinner("Processing image..."):
                img = Image.open(uploaded_img)
                st.image(img, width=300)
                q = img_prompt if img_prompt else "Solve or explain this image step-by-step."
                response_text = call_ai(q, image=img)
                st.markdown("---")
                st.markdown(response_text)

# --- TAB 3: DIRECT ASK ---
with tab3:
    user_query = st.text_area("Ask a question or topic:", placeholder="e.g. Explain SQL Injection...", height=100)
    if st.button("⚡ Generate Answer", type="primary", key="proc_txt"):
        if not user_query.strip():
            st.warning("Please type a question.")
        else:
            with st.spinner("Thinking..."):
                response_text = call_ai(user_query)
                st.markdown("---")
                st.markdown(response_text)

# Footer
st.markdown("---")
st.markdown("<div style='text-align:center; color:#7f8a9a; font-size:12px;'>🛡️ Student AI | Built by MG Gangwar</div>", unsafe_allow_html=True)
