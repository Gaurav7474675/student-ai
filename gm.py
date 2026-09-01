import streamlit as st
from PyPDF2 import PdfReader

# 1. Page Configuration
st.set_page_config(page_title="STUDENT AI", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")

# 2. Custom CSS for Gemini/ChatGPT-style Stable Layout
st.markdown("""
    <style>
    /* Dark Modern Background */
    .stApp {
        background-color: #131314;
        color: #E3E3E3;
    }
    
    /* Clean Sidebar */
    [data-testid="stSidebar"] {
        background-color: #1E1F20;
        border-right: 1px solid #2D2E31;
    }
    
    /* Top Bar Header Alignment */
    .top-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 0px;
        margin-bottom: 20px;
    }
    
    /* Hide Default Streamlit Animations/Footers */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Fixed Bottom Input Area (Gemini Style) */
    .bottom-bar {
        position: fixed;
        bottom: 20px;
        width: 60%;
        left: 25%;
        background-color: #1E1F20;
        padding: 15px;
        border-radius: 16px;
        border: 1px solid #333537;
        box-shadow: 0px 4px 15px rgba(0,0,0,0.5);
    }
    
    /* Process/Submit Button Style */
    div.stButton > button {
        background-color: #1A73E8 !important;
        color: white !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        border: none !important;
        padding: 8px 16px !important;
    }
    div.stButton > button:hover {
        background-color: #1557B0 !important;
    }
    </style>
""", unsafe_allow_html=True)

# ----------------- SIDEBAR (Clean & Stable) -----------------
with st.sidebar:
    st.markdown("### 🛡️ **STUDENT AI**")
    st.caption("By MG Gangwar | Exam Notes & Analysis")
    st.divider()
    
    # Navigation
    menu = st.radio(
        "Select Mode:",
        ["💬 Ask AI / Quick Doubt", "📁 PDF Notes Generator", "📷 Image / Photo Solver"],
        index=0
    )
    
    st.divider()
    
    # Clean Pro Access Info (No HTML Code Leak)
    st.markdown("### 👑 Pro Membership")
    st.info("Unlock Unlimited Pages, Image Solver & Instant MCQs.")
    st.link_button("⭐ Upgrade @ ₹99", "https://imjo.in/HJVTwE", use_container_width=True)

# ----------------- TOP HEADER AREA -----------------
head_col1, head_col2 = st.columns([4, 1])

with head_col1:
    st.title("🛡️ STUDENT AI")
    st.caption("Smart Cyber Assistance & Exam Preparation Companion")

with head_col2:
    # Top Right Pro Button
    if st.button("⭐ PRO Access"):
        @st.dialog("🔒 Get PRO Access")
        def show_pro_info():
            st.write("Unlock all features without page limits!")
            st.link_button("Pay ₹99 via Instamojo", "https://imjo.in/HJVTwE", use_container_width=True)
        show_pro_info()

st.divider()

# ----------------- MAIN PAGES (Gemini Layout) -----------------

# OPTION 1: Direct Ask / Quick Doubt
if menu == "💬 Ask AI / Quick Doubt":
    st.subheader("💬 Ask Anything")
    user_query = st.text_input("Apna Question / Topic Type Karein:", placeholder="e.g. Explain SQL Injection with code example")
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("⚡ Get Answer"):
            if user_query:
                st.success("Generating response...")
            else:
                st.warning("Pehle koi topic type karein!")

# OPTION 2: PDF Processing
elif menu == "📁 PDF Notes Generator":
    st.subheader("📁 Upload College Notes / Book PDF")
    
    pdf_file = st.file_uploader("PDF Choose Karein:", type=["pdf"])
    
    pdf_mode = st.selectbox(
        "Kya generate karna hai?",
        ["⚡ Quick Revision Notes", "🎯 Important Exam Questions", "🧪 Practice Quiz (MCQs)"]
    )
    
    if st.button("🚀 Process PDF"):
        if pdf_file is not None:
            reader = PdfReader(pdf_file)
            pages = len(reader.pages)
            
            # 3 Page Restriction Logic
            if pages > 3:
                @st.dialog("🔒 Premium Feature Locked")
                def paywall():
                    st.error(f"Aapki PDF me {pages} pages hain!")
                    st.write("Free plan me sirf **3 pages** allow hain.")
                    st.link_button("⭐ Upgrade to Pro @ ₹99", "https://imjo.in/HJVTwE", use_container_width=True)
                paywall()
            else:
                st.success(f"{pages} pages processed successfully!")
        else:
            st.warning("Kripya pehle PDF file select karein.")

# OPTION 3: Image Solver
elif menu == "📷 Image / Photo Solver":
    st.subheader("📷 Photo / Screenshot Solver")
    
    img_file = st.file_uploader("Diagram ya Question Paper ki photo upload karein:", type=["jpg", "png", "jpeg"])
    
    if img_file is not None:
        @st.dialog("🔒 Image Solver Pro Feature")
        def img_paywall():
            st.info("Direct Photo Solver feature sirf **PRO users** ke liye hai.")
            st.link_button("⭐ Unlock Image Solver @ ₹99", "https://imjo.in/HJVTwE", use_container_width=True)
        img_paywall()
