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
# API KEY
# =========================================================
api_key = (
    st.secrets.get("GEMINI_API_KEY")
    or os.environ.get("GEMINI_API_KEY")
)

# Pro Passcode
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
# PROFESSIONAL CSS
# =========================================================
st.markdown(
    """
    <style>

    /* ---------------- GLOBAL ---------------- */

    .stApp {
        background:
            radial-gradient(
                circle at top left,
                rgba(25, 45, 80, 0.28),
                transparent 35%
            ),
            radial-gradient(
                circle at top right,
                rgba(0, 150, 136, 0.10),
                transparent 30%
            ),
            #080c14;
        color: #f4f7fb;
    }

    .main {
        background: transparent;
    }

    /* Main content width */
    .block-container {
        max-width: 1000px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }

    /* ---------------- HEADINGS ---------------- */

    h1, h2, h3 {
        color: #f8fafc !important;
        font-weight: 750 !important;
    }

    h1 {
        letter-spacing: -0.5px;
    }

    p, label, span {
        color: #d7dce5;
    }

    /* ---------------- PROFILE ---------------- */

    .profile-card {
        background: linear-gradient(
            145deg,
            rgba(25, 32, 48, 0.95),
            rgba(12, 17, 27, 0.95)
        );
        border: 1px solid rgba(100, 116, 139, 0.22);
        border-radius: 22px;
        padding: 28px 20px;
        margin-bottom: 25px;
        box-shadow:
            0 15px 45px rgba(0, 0, 0, 0.25);
        text-align: center;
    }

    .profile-name {
        font-size: 38px;
        font-weight: 800;
        color: #ffffff;
        margin-top: 10px;
    }

    .profile-subtitle {
        color: #aeb7c6;
        font-size: 14px;
        margin-top: 5px;
    }

    /* ---------------- DIVIDER ---------------- */

    hr {
        border: none !important;
        height: 1px !important;
        background: linear-gradient(
            90deg,
            transparent,
            #344054,
            transparent
        ) !important;
        margin: 25px 0 !important;
    }

    /* ---------------- BUTTONS ---------------- */

    .stButton > button {
        width: 100%;
        min-height: 44px;
        border-radius: 10px;
        border: 1px solid #344054;
        background: #111827;
        color: #f8fafc;
        font-weight: 650;
        transition: all 0.2s ease;
    }

    .stButton > button:hover {
        border-color: #4ade80;
        color: #ffffff;
        background: #172033;
        transform: translateY(-1px);
    }

    /* Green Process PDF button */
    div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(
            135deg,
            #16a34a,
            #15803d
        ) !important;
        border: 1px solid #22c55e !important;
        color: white !important;
        font-weight: 800 !important;
        box-shadow:
            0 8px 22px rgba(22, 163, 74, 0.25);
    }

    div[data-testid="stButton"] button[kind="primary"]:hover {
        background: linear-gradient(
            135deg,
            #22c55e,
            #16a34a
        ) !important;
        box-shadow:
            0 10px 28px rgba(34, 197, 94, 0.35);
    }

    /* ---------------- PRO BUTTON ---------------- */

    .pro-button-container {
        background: linear-gradient(
            135deg,
            rgba(124, 58, 237, 0.16),
            rgba(37, 99, 235, 0.12)
        );
        padding: 12px;
        border-radius: 15px;
        border: 1px solid rgba(139, 92, 246, 0.3);
        margin-bottom: 15px;
    }

    /* ---------------- SIDEBAR ---------------- */

    section[data-testid="stSidebar"] {
        background:
            linear-gradient(
                180deg,
                #0d1320 0%,
                #080c14 100%
            );
        border-right: 1px solid #202938;
    }

    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: #ffffff !important;
    }

    /* ---------------- TABS ---------------- */

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: #0d1320;
        border-radius: 14px;
        padding: 6px;
        border: 1px solid #202938;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        color: #aeb7c6;
        font-weight: 600;
        padding: 10px 14px;
    }

    .stTabs [aria-selected="true"] {
        background: #172033;
        color: #ffffff !important;
    }

    /* ---------------- FILE UPLOADER ---------------- */

    [data-testid="stFileUploader"] {
        background: #121824;
        border: 1px dashed #3b4658;
        border-radius: 14px;
        padding: 8px;
    }

    [data-testid="stFileUploader"]:hover {
        border-color: #22c55e;
    }

    /* ---------------- INPUTS ---------------- */

    textarea,
    input {
        background-color: #111827 !important;
        color: #ffffff !important;
        border-color: #344054 !important;
    }

    /* ---------------- INFO BOXES ---------------- */

    .stAlert {
        border-radius: 12px;
    }

    /* ---------------- PREMIUM CARD ---------------- */

    .premium-card {
        background: linear-gradient(
            145deg,
            #17132b,
            #101827
        );
        border: 1px solid rgba(139, 92, 246, 0.45);
        border-radius: 18px;
        padding: 22px;
        text-align: center;
        box-shadow:
            0 15px 45px rgba(0, 0, 0, 0.35);
    }

    .premium-title {
        color: #f5d76e;
        font-size: 26px;
        font-weight: 800;
    }

    .premium-price {
        color: #ffffff;
        font-size: 32px;
        font-weight: 800;
        margin: 8px 0;
    }

    .premium-text {
        color: #b9c2d0;
        font-size: 14px;
        line-height: 1.6;
    }

    /* ---------------- SUCCESS ---------------- */

    .success-card {
        background: rgba(22, 163, 74, 0.12);
        border: 1px solid rgba(34, 197, 94, 0.35);
        padding: 14px;
        border-radius: 12px;
    }

    /* Mobile */
    @media (max-width: 700px) {
        .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }

        .profile-name {
            font-size: 30px;
        }

        .stTabs [data-baseweb="tab"] {
            padding: 8px 8px;
            font-size: 12px;
        }
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
        raise Exception(
            "GEMINI_API_KEY nahi mili. "
            "Streamlit Secrets me API key add karein."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    content_payload = [
        {
            "type": "text",
            "text": prompt
        }
    ]

    if image:

        buffered = io.BytesIO()

        image.save(
            buffered,
            format="PNG"
        )

        img_str = base64.b64encode(
            buffered.getvalue()
        ).decode()

        content_payload.append(
            {
                "type": "image_url",
                "image_url": {
                    "url":
                    f"data:image/png;base64,{img_str}"
                }
            }
        )

    payload = {
        "model": "google/gemini-2.5-flash",
        "messages": [
            {
                "role": "user",
                "content": content_payload
            }
        ],
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

        raise Exception(
            f"API Response Error: {response.text}"
        )


# =========================================================
# PREMIUM POPUP
# =========================================================
@st.dialog("💎 Upgrade to Student AI Pro")
def premium_popup():

    st.markdown(
        """
        <div class="premium-card">

            <div class="premium-title">
                👑 STUDENT AI PRO
            </div>

            <div class="premium-price">
                ₹99 / month
            </div>

            <div class="premium-text">
                Unlock full PDF analysis, unlimited pages,
                image/photo solving and premium AI assistance.
            </div>

        </div>
        """,
        unsafe_allow_html=True
    )

    st.write("")

    st.markdown("### 🚀 Pro Features")

    col1, col2 = st.columns(2)

    with col1:
        st.success("✅ Full Book PDF")
        st.success("✅ Unlimited Pages")

    with col2:
        st.success("✅ Image Solver")
        st.success("✅ Advanced AI")

    st.markdown("---")

    # QR CODE
    try:
        qr_col1, qr_col2, qr_col3 = st.columns(
            [1, 2, 1]
        )

        with qr_col2:
            st.image(
                "qr.png",
                caption="Scan & Pay ₹99 via UPI",
                use_container_width=True
            )

    except Exception:
        st.info(
            "📱 Pay ₹99 to UPI ID: yourname@upi"
        )

    st.markdown("---")

    st.write(
        "💳 Payment complete hone ke baad "
        "apna Pro Access Passcode enter karein."
    )

    passcode = st.text_input(
        "🔐 Pro Access Passcode",
        type="password",
        placeholder="Enter your passcode"
    )

    unlock_col1, unlock_col2 = st.columns(2)

    with unlock_col1:

        if st.button(
            "👑 Unlock Pro",
            type="primary",
            use_container_width=True
        ):

            if passcode == PRO_PASSCODE:

                st.session_state.is_pro = True
                st.session_state.show_pro_popup = False

                st.success(
                    "🎉 Pro Access Successfully Unlocked!"
                )

                st.rerun()

            elif passcode:

                st.error(
                    "❌ Invalid Passcode!"
                )

    with unlock_col2:

        if st.button(
            "Close",
            use_container_width=True
        ):

            st.session_state.show_pro_popup = False
            st.rerun()


# =========================================================
# SHOW PREMIUM POPUP
# =========================================================
if st.session_state.show_pro_popup:

    premium_popup()


# =========================================================
# HEADER / PROFILE
# =========================================================
st.markdown(
    '<div class="profile-card">',
    unsafe_allow_html=True
)

# Center Profile Image
try:

    profile_col1, profile_col2, profile_col3 = st.columns(
        [1, 1, 1]
    )

    with profile_col2:

        st.image(
            "profile.jpeg",
            width=110
        )

except Exception:

    profile_col1, profile_col2, profile_col3 = st.columns(
        [1, 1, 1]
    )

    with profile_col2:
        st.markdown(
            "<div style='font-size:80px;'>🛡️</div>",
            unsafe_allow_html=True
        )


st.markdown(
    """
    <div class="profile-name">
        🛡️ STUDENT AI
    </div>

    <div class="profile-subtitle">
        Created by <b>MG Gangwar</b>
        |
        Instant Cyber Assistance,
        Exam Notes & MCQs
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown(
    "</div>",
    unsafe_allow_html=True
)


# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:

    st.markdown("## 👑 Member Access")

    st.markdown("---")

    # ---------------- FREE USER ----------------

    if not st.session_state.is_pro:

        st.info(
            "🆓 Free User\n\n"
            "• PDF: First 3 pages\n"
            "• Image Solver: Pro\n"
            "• Direct Ask: Available"
        )

        st.markdown(
            '<div class="pro-button-container">',
            unsafe_allow_html=True
        )

        if st.button(
            "💎 Pro",
            type="primary",
            use_container_width=True
        ):

            st.session_state.show_pro_popup = True
            st.rerun()

        st.markdown(
            "</div>",
            unsafe_allow_html=True
        )

        st.caption(
            "Upgrade to unlock all premium features."
        )

    # ---------------- PRO USER ----------------

    else:

        st.success(
            "👑 PRO USER\n\n"
            "Full Premium Access Enabled"
        )

        if st.button(
            "💎 Pro Active",
            use_container_width=True
        ):
            st.info(
                "Your Pro Access is already active."
            )

    st.markdown("---")

    st.markdown(
        """
        ### ✨ Features

        📂 PDF Analysis  
        📷 Image Solver  
        💬 Direct AI Ask  
        🧪 MCQ Generator  
        🎯 Exam Questions  
        🛡️ Cyber Analysis  
        👑 Pro Full Book Access
        """
    )


# =========================================================
# MAIN TABS
# =========================================================
tab1, tab2, tab3 = st.tabs(
    [
        "📂 PDF Analysis",
        "📷 Image / Photo Solver",
        "💬 Direct Ask Question"
    ]
)


# =========================================================
# TAB 1 - PDF
# =========================================================
with tab1:

    st.subheader(
        "📂 Upload College Notes / Book PDF"
    )

    uploaded_file = st.file_uploader(
        "PDF File Yahan Drop Karein:",
        type=["pdf"],
        key="pdf_uploader"
    )

    # -----------------------------------------------------
    # CHECK PDF PAGE COUNT ON UPLOAD
    # -----------------------------------------------------
    pdf_page_count = 0

    if uploaded_file:

        try:

            pdf_bytes = uploaded_file.getvalue()

            pdf_reader_for_count = PdfReader(
                io.BytesIO(pdf_bytes)
            )

            pdf_page_count = len(
                pdf_reader_for_count.pages
            )

            if (
                pdf_page_count > 3
                and not st.session_state.is_pro
            ):

                st.warning(
                    f"🔒 This PDF contains "
                    f"**{pdf_page_count} pages**. "
                    f"Free plan supports only 3 pages."
                )

                if not st.session_state.pdf_popup_shown:

                    st.session_state.pdf_popup_shown = True
                    st.session_state.show_pro_popup = True
                    st.rerun()

        except Exception as e:

            st.error(
                f"PDF page count read error: {e}"
            )

    # -----------------------------------------------------
    # FEATURE SELECTION
    # -----------------------------------------------------
    feature = st.radio(
        "Aapko kya generate karna hai?",
        [
            "⚡ Quick Revision Notes",
            "🎯 Important Exam Questions",
            "🧪 Practice Quiz (MCQs)",
            "🛡️ Cyber Security & Code Analysis"
        ],
        key="pdf_radio"
    )

    st.write("")

    # -----------------------------------------------------
    # CENTER PROCESS PDF BUTTON
    # -----------------------------------------------------
    process_col1, process_col2, process_col3 = st.columns(
        [1, 2, 1]
    )

    with process_col2:

        process_pdf = st.button(
            "🚀 Process PDF",
            type="primary",
            key="btn_pdf",
            use_container_width=True
        )

    # -----------------------------------------------------
    # PROCESS PDF
    # -----------------------------------------------------
    if process_pdf:

        if not uploaded_file:

            st.warning(
                "⚠️ Pehle koi PDF upload karein!"
            )

        elif not api_key:

            st.error(
                "API Key nahi mil rahi! "
                "Kripya Streamlit Secrets me "
                "GEMINI_API_KEY save karein."
            )

        elif (
            pdf_page_count > 3
            and not st.session_state.is_pro
        ):

            st.session_state.show_pro_popup = True
            st.rerun()

        else:

            try:

                with st.spinner(
                    "🤖 GM AI is reading your document..."
                ):

                    reader = PdfReader(
                        io.BytesIO(
                            uploaded_file.getvalue()
                        )
                    )

                    extracted_text = ""

                    # Pro = full book
                    # Free = first 3 pages
                    max_pages = (
                        len(reader.pages)
                        if st.session_state.is_pro
                        else min(
                            3,
                            len(reader.pages)
                        )
                    )

                    for page in reader.pages[:max_pages]:

                        extracted_text += (
                            page.extract_text() or ""
                        )

                    # Text limit
                    text_limit = (
                        500000
                        if st.session_state.is_pro
                        else 8000
                    )

                    final_text = extracted_text[
                        :text_limit
                    ]

                    if not final_text.strip():

                        st.error(
                            "PDF se text read nahi ho paya. "
                            "Clean text PDF use karein."
                        )

                    else:

                        # -------------------------------
                        # PROMPTS
                        # -------------------------------

                        if (
                            "Quick Revision Notes"
                            in feature
                        ):

                            prompt = f"""
You are an expert college study assistant.

Create structured, high-yield quick revision notes
from the following study material.

Requirements:
- Use clear headings
- Highlight important concepts
- Use bullet points
- Include definitions
- Include formulas where applicable
- Keep the explanation exam-focused
- Bold important keywords

Study Material:

{final_text}
"""

                        elif (
                            "Important Exam Questions"
                            in feature
                        ):

                            prompt = f"""
You are an expert college exam preparation assistant.

Create 10 important exam questions with concise,
accurate answers based only on the following content.

Include:
1. Question
2. Answer
3. Important keywords where useful

Study Material:

{final_text}
"""

                        elif (
                            "Practice Quiz"
                            in feature
                        ):

                            prompt = f"""
Create a 10-question college-level MCQ quiz
based on the following content.

For every question provide:

Question:
A)
B)
C)
D)

Correct Answer:
Explanation:

Make questions exam-oriented and avoid duplicate
questions.

Study Material:

{final_text}
"""

                        else:

                            prompt = f"""
Perform a cybersecurity assessment of the
following educational/content material.

Provide:
1. Security Summary
2. Potential Threats
3. Vulnerabilities
4. Risk Level
5. Recommended Mitigations
6. Secure Coding Recommendations if code exists

Keep the assessment educational and defensive.

Content:

{final_text}
"""

                        # -------------------------------
                        # AI CALL
                        # -------------------------------

                        res_text = call_ai(
                            prompt
                        )

                        st.success(
                            "✨ Processing Complete!"
                        )

                        st.markdown(
                            res_text
                        )

                        # Free plan information
                        if not st.session_state.is_pro:

                            st.info(
                                "💡 Free Plan: "
                                "Sirf first 3 pages scan ki gayi hain. "
                                "Full book scan karne ke liye "
                                "💎 Pro unlock karein."
                            )

                        else:

                            st.success(
                                "👑 Pro Mode: "
                                "Full PDF access enabled."
                            )

            except Exception as e:

                st.error(
                    f"Error: {e}"
                )


# =========================================================
# TAB 2 - IMAGE SOLVER
# =========================================================
with tab2:

    st.subheader(
        "📷 Photo / Screenshot Solver"
    )

    st.info(
        "💎 Image / Photo Solver is available in Pro."
    )

    uploaded_img = st.file_uploader(
        "Upload Image "
        "(Question Paper / Diagram / Book photo):",
        type=["jpg", "jpeg", "png"],
        key="img_uploader"
    )

    img_prompt = st.text_input(
        "Koi specific question poochhna hai image ke baare me? (Optional)",
        placeholder=(
            "e.g. Solve Question No. 3 "
            "or Explain this diagram"
        )
    )

    # -----------------------------------------------------
    # IMAGE UPLOAD => PREMIUM POPUP
    # -----------------------------------------------------
    if (
        uploaded_img
        and not st.session_state.is_pro
        and not st.session_state.image_popup_shown
    ):

        st.session_state.image_popup_shown = True
        st.session_state.show_pro_popup = True
        st.rerun()

    # -----------------------------------------------------
    # ANALYZE BUTTON
    # -----------------------------------------------------
    if st.button(
        "🔍 Analyze Image",
        key="btn_img",
        type="primary",
        use_container_width=True
    ):

        if not uploaded_img:

            st.warning(
                "⚠️ Pehle koi Image upload karein!"
            )

        elif not st.session_state.is_pro:

            st.session_state.show_pro_popup = True
            st.rerun()

        elif not api_key:

            st.error(
                "API Key nahi mil rahi! "
                "Kripya Streamlit Secrets me "
                "GEMINI_API_KEY save karein."
            )

        else:

            try:

                with st.spinner(
                    "🤖 GM AI is analyzing image..."
                ):

                    image = Image.open(
                        uploaded_img
                    )

                    st.image(
                        image,
                        caption="Uploaded Image",
                        use_container_width=True
                    )

                    user_query = (
                        img_prompt
                        if img_prompt.strip()
                        else
                        """
                        Analyze this image in detail.

                        If it contains questions:
                        solve them step-by-step.

                        If it contains a diagram:
                        explain the diagram clearly.

                        If it contains educational content:
                        explain the important concepts.
                        """
                    )

                    res_text = call_ai(
                        user_query,
                        image=image
                    )

                    st.success(
                        "✨ Analysis Complete!"
                    )

                    st.markdown(
                        res_text
                    )

            except Exception as e:

                st.error(
                    f"Error: {e}"
                )


# =========================================================
# TAB 3 - DIRECT ASK
# =========================================================
with tab3:

    st.subheader(
        "💬 Direct Ask Question"
    )

    user_text_question = st.text_area(
        "Apna question ya topic yahan likhein:",
        placeholder=(
            "e.g. Explain SQL Injection with "
            "code example, or What is Cyber Law?"
        ),
        height=150
    )

    ask_col1, ask_col2, ask_col3 = st.columns(
        [1, 2, 1]
    )

    with ask_col2:

        ask_question = st.button(
            "⚡ Get Answer",
            type="primary",
            key="btn_text",
            use_container_width=True
        )

    if ask_question:

        if not user_text_question.strip():

            st.warning(
                "⚠️ Pehle apna sawaal/text likhein!"
            )

        elif not api_key:

            st.error(
                "API Key nahi mil rahi! "
                "Kripya Streamlit Secrets me "
                "GEMINI_API_KEY save karein."
            )

        else:

            try:

                with st.spinner(
                    "🤖 GM AI is thinking..."
                ):

                    res_text = call_ai(
                        user_text_question
                    )

                    st.success(
                        "✨ Answer Generated!"
                    )

                    st.markdown(
                        res_text
                    )

            except Exception as e:

                st.error(
                    f"Error: {e}"
                )


# =========================================================
# FOOTER
# =========================================================
st.markdown("---")

st.markdown(
    """
    <div style="
        text-align:center;
        color:#7f8a9a;
        font-size:12px;
        padding:10px;
    ">
        🛡️ <b>Student AI</b> |
        Created by MG Gangwar |
        Smart Study & Cyber Assistance
    </div>
    """,
    unsafe_allow_html=True
)
