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
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# API KEY & CONFIGS
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

if "image_popup_shown" not in st.session_state:
    st.session_state.image_popup_shown = False

if "pdf_popup_shown" not in st.session_state:
    st.session_state.pdf_popup_shown = False

# =========================================================
# PROFESSIONAL CSS (Gemini App Layout & Zero Animation)
# =========================================================
st.markdown(
    """
    <style>
    /* Global Clean App Background */
    .stApp {
        background-color: #0E1117;
        color: #F4F7FB;
    }
    
    .main {
        background: transparent;
    }

    /* Stop Animation & Unwanted Margin Shifting */
    * {
        transition: none !important;
        animation: none !important;
    }

    .block-container {
        max-width: 950px;
        padding-top: 1rem;
        padding-bottom: 7rem;
    }

    /* Top Bar Header */
    .header-box {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 0px;
        border-bottom: 1px solid #202938;
        margin-bottom: 20px;
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #121824;
        border-right: 1px solid #202938;
    }

    /* Buttons Style */
    .stButton > button {
        border-radius: 10px;
        border: 1px solid #344054;
        background: #111827;
        color: #F8FAFC;
        font-weight: 600;
    }

    .stButton > button:hover {
        border-color: #22C55E;
        background: #172033;
    }

    /* Green Process PDF button */
    div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(135deg, #16A34A, #15803D) !important;
        border: 1px solid #22C55E !important;
        color: white !important;
        font-weight: 800 !important;
    }

    /* Gemini-Style Fixed Bottom Dock */
    .gemini-bottom-dock {
        position: fixed;
        bottom: 15px;
        left: 55%;
        transform: translateX(-50%);
        width: 60%;
        max-width: 750px;
        background-color: #1E2638;
        border: 1px solid #344054;
        border-radius: 20px;
        padding: 10px 20px;
        box-shadow: 0px 8px 30px rgba(0,0,0,0.6);
        z-index: 999;
    }

    @media (max-width: 768px) {
        .gemini-bottom-dock {
            width: 90%;
            left: 50%;
        }
    }
    </style>
    """,
    unsafe_allow_html=True
)

# =========================================================
# AI ENGINE
# =========================================================
def call_ai(prompt, image=None):
    if not api_key:
        raise Exception("GEMINI_API_KEY nahi mili. Streamlit Secrets me API key add karein.")

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
        data = response.json()
        return data["choices"][0]["message"]["content"]
    else:
        raise Exception(f"API Response Error: {response.text}")

# =========================================================
# PRO POPUP DIALOG
# =========================================================
@st.dialog("💎 Upgrade to Student AI Pro")
def premium_popup():
    st.markdown("### 👑 STUDENT AI PRO")
    st.write("**₹99 / month** - Unlock full PDF analysis, unlimited pages & Image Solver.")
    
    st.markdown("---")
    try:
        st.image("qr.png", caption="Scan & Pay ₹99 via UPI", width=200)
    except Exception:
        st.info("📱 Pay ₹99 to UPI Link: https://imjo.in/HJVTwE")

    st.markdown("---")
    passcode = st.text_input("🔐 Enter Pro Access Passcode", type="password")

    unlock_col, close_col = st.columns(2)
    with unlock_col:
        if st.button("👑 Unlock Pro", type="primary", use_container_width=True):
            if passcode == PRO_PASSCODE:
                st.session_state.is_pro = True
                st.session_state.show_pro_popup = False
                st.success("🎉 Pro Access Successfully Unlocked!")
                st.rerun()
            elif passcode:
                st.error("❌ Invalid Passcode!")
    with close_col:
        if st.button("Close", use_container_width=True):
            st.session_state.show_pro_popup = False
            st.rerun()

if st.session_state.show_pro_popup:
    premium_popup()

# =========================================================
# HEADER & TOP PRO BUTTON
# =========================================================
head_col1, head_col2 = st.columns([4, 1])

with head_col1:
    st.title("🛡️ STUDENT AI")
    st.caption("Created by **MG Gangwar** | Instant Cyber Assistance, Exam Notes & MCQs")

with head_col2:
    if not st.session_state.is_pro:
        if st.button("⭐ PRO", type="primary"):
            st.session_state.show_pro_popup = True
            st.rerun()
    else:
        st.success("👑 Active")

st.divider()

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown("### 👑 Member Status")
    
    if not st.session_state.is_pro:
        st.info("🆓 Free Tier\n- PDF: First 3 pages\n- Image Solver: Pro locked")
        if st.button("💎 Upgrade @ ₹99", use_container_width=True):
            st.session_state.show_pro_popup = True
            st.rerun()
    else:
        st.success("👑 PRO UNLOCKED\nFull Access Enabled")

    st.divider()
    st.markdown("""
    **✨ Features Included:**
    - 📂 PDF Analysis
    - 📷 Photo / Image Solver
    - 💬 Direct AI Ask
    - 🧪 MCQ & Notes Generator
    """)

# =========================================================
# MAIN NAVIGATION TABS
# =========================================================
tab1, tab2, tab3 = st.tabs([
    "📂 PDF Analysis",
    "📷 Image Solver",
    "💬 Direct Ask Question"
])

# ----------------- TAB 1: PDF ANALYSIS -----------------
with tab1:
    st.subheader("📂 PDF Notes Generator")
    uploaded_file = st.file_uploader("PDF File Upload Karein:", type=["pdf"], key="pdf_uploader")

    pdf_page_count = 0
    if uploaded_file:
        try:
            pdf_bytes = uploaded_file.getvalue()
            pdf_reader_for_count = PdfReader(io.BytesIO(pdf_bytes))
            pdf_page_count = len(pdf_reader_for_count.pages)

            if pdf_page_count > 3 and not st.session_state.is_pro:
                st.warning(f"🔒 PDF me **{pdf_page_count} pages** hain. Free plan allows 3 pages.")
                if not st.session_state.pdf_popup_shown:
                    st.session_state.pdf_popup_shown = True
                    st.session_state.show_pro_popup = True
                    st.rerun()
        except Exception as e:
            st.error(f"PDF Reading Error: {e}")

    feature = st.radio(
        "Generate Output:",
        ["⚡ Quick Revision Notes", "🎯 Exam Questions", "🧪 Practice MCQs", "🛡️ Code Analysis"],
        horizontal=True
    )

    if st.button("🚀 Process PDF", type="primary", use_container_width=True):
        if not uploaded_file:
            st.warning("⚠️ Pehle PDF upload karein!")
        elif pdf_page_count > 3 and not st.session_state.is_pro:
            st.session_state.show_pro_popup = True
            st.rerun()
        else:
            try:
                with st.spinner("🤖 Reading PDF..."):
                    reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
                    extracted_text = ""
                    max_pages = len(reader.pages) if st.session_state.is_pro else min(3, len(reader.pages))

                    for page in reader.pages[:max_pages]:
                        extracted_text += page.extract_text() or ""

                    text_limit = 500000 if st.session_state.is_pro else 8000
                    final_text = extracted_text[:text_limit]

                    prompt = f"Create structured {feature} from the following text:\n\n{final_text}"
                    response = call_ai(prompt)
                    st.markdown("### 📋 AI Result")
                    st.write(response)
            except Exception as e:
                st.error(f"Error: {e}")

# ----------------- TAB 2: IMAGE SOLVER -----------------
with tab2:
    st.subheader("📷 Photo / Screenshot Solver")
    if not st.session_state.is_pro:
        st.info("🔒 Image Solver is a Pro Feature.")
        if st.button("Unlock Image Solver @ ₹99"):
            st.session_state.show_pro_popup = True
            st.rerun()
    else:
        uploaded_img = st.file_uploader("Upload Question / Diagram Image:", type=["jpg", "png", "jpeg"])
        if uploaded_img:
            image = Image.open(uploaded_img)
            st.image(image, caption="Uploaded Image", width=300)
            if st.button("⚡ Solve Image", type="primary"):
                with st.spinner("Analyzing image..."):
                    res = call_ai("Solve and explain this image content step by step:", image=image)
                    st.markdown("### 💡 Solution")
                    st.write(res)

# ----------------- TAB 3: DIRECT ASK (Gemini-Style Dock) -----------------
with tab3:
    st.subheader("💬 Direct Ask Question")
    st.write("Type your question below or use the Gemini-style dock.")

    direct_query = st.text_input("Apna Doubt/Topic Yahan Type Karein:", placeholder="e.g. What is SQL Injection?")
    if st.button("⚡ Get Answer", key="direct_btn"):
        if direct_query:
            with st.spinner("Generating..."):
                ans = call_ai(f"Explain in detail with code examples if needed: {direct_query}")
                st.write(ans)
        else:
            st.warning("Please type a question!")
