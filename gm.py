import streamlit as st
import requests
from pypdf import PdfReader
from PIL import Image
import os
import base64
import io

# Secrets se API Key connect karna
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

# OpenRouter Helper Function (Free Model & Limit Fixed)
def call_ai(prompt, image=None):
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
        "model": "google/gemini-2.5-flash:free",
        "messages": [{"role": "user", "content": content_payload}],
        "max_tokens": 2000
    }
    
    response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    else:
        raise Exception(f"API Response Error: {response.text}")
# Page Configuration
st.set_page_config(page_title="GM Cyber & Student AI", page_icon="🛡️", layout="centered")

# Custom CSS
st.markdown("""
    <style>
    stButton>button { width: 100%; border-radius: 8px; height: 3em; background-color: #0080FF; color: white; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ----------------- HEADER & PROFILE SECTION -----------------
col1, col2 = st.columns([1, 4])
with col1:
    try:
        st.image("profile.jpeg", width=85)
    except:
        st.write("🛡️")

with col2:
    st.title("🛡️ STUDENT AI")
    st.caption("Created by *MG Gangwar* | Instant Cyber Assistance, Exam Notes & MCQs")

st.markdown("---")

# ----------------- SIDEBAR PAYMENT & PLAN SECTION -----------------
st.sidebar.header("👑 Member Access")
user_mode = st.sidebar.radio("Select Mode:", ["🆓 Free User (3 Pages Max)", "💎 Pro User (Full Book)"])

is_pro = False

if user_mode == "💎 Pro User (Full Book)":
    st.sidebar.markdown("---")
    st.sidebar.subheader("💳 Upgrade to Pro (₹99/mo)")
    
    try:
        st.sidebar.image("qr.png", caption="Scan to pay ₹99 via UPI", width=180)
    except:
        st.sidebar.info("📱 *Pay ₹99 to UPI ID:* yourname@upi")
    
    st.sidebar.write("1. QR Code scan karke ₹99 pay karein.")
    st.sidebar.write("2. Payment ke baad Access Passcode daalein:")
    
    passcode = st.sidebar.text_input("Enter Passcode:", type="password")
    
    if passcode == "GMCYBER2026":
        st.sidebar.success("✅ Pro Access Unlocked!")
        is_pro = True
    elif passcode:
        st.sidebar.error("❌ Invalid Passcode!")

# ----------------- MAIN INPUT TABS -----------------
tab1, tab2, tab3 = st.tabs(["📂 PDF Analysis", "📷 Image / Photo Solver", "💬 Direct Ask Question"])

# ================= TAB 1: PDF Notes & MCQs =================
with tab1:
    st.subheader("📂 Upload College Notes / Book PDF")
    uploaded_file = st.file_uploader("PDF File Yahan Drop Karein:", type=["pdf"], key="pdf_uploader")

    feature = st.radio(
        "Aapko kya generate karna hai?",
        ["⚡ Quick Revision Notes", "🎯 Important Exam Questions", "🧪 Practice Quiz (MCQs)", "🛡️ Cyber Security & Code Analysis"],
        key="pdf_radio"
    )

    if st.button("🚀 Process PDF", key="btn_pdf"):
        if not uploaded_file:
            st.warning("Pehle koi PDF upload karein!")
        elif not api_key:
            st.error("API Key nahi mil rahi! Kripya Streamlit Secrets me GEMINI_API_KEY save karein.")
        else:
            try:
                with st.spinner("GM AI is reading your document..."):
                    reader = PdfReader(uploaded_file)
                    extracted_text = ""
                    
                    max_pages = 100 if is_pro else 3
                    for page in reader.pages[:max_pages]:
                        extracted_text += page.extract_text() or ""

                    text_limit = 500000 if is_pro else 8000
                    final_text = extracted_text[:text_limit]

                    if not final_text.strip():
                        st.error("PDF se text read nahi ho paya. Clean text PDF use karein.")
                    else:
                        if "Quick Revision Notes" in feature:
                            prompt = f"Provide structured, high-yield quick revision notes with bold key terms from this content:\n\n{final_text}"
                        elif "Important Exam Questions" in feature:
                            prompt = f"Create 10 important exam questions with concise answers based on this content:\n\n{final_text}"
                        elif "Practice Quiz" in feature:
                            prompt = f"Create a 10-question MCQ Quiz with options (A, B, C, D), correct answers, and explanations based on this content:\n\n{final_text}"
                        else:
                            prompt = f"Perform a cybersecurity assessment, threat analysis, and security summary for this content:\n\n{final_text}"

                        res_text = call_ai(prompt)

                        st.success("✨ Processing Complete!")
                        st.markdown(res_text)
                        
                        if not is_pro:
                            st.info("💡 Free Plan limits scanning to first 3 pages. Select 'Pro User' in sidebar to scan full books!")

            except Exception as e:
                st.error(f"Error: {e}")

# ================= TAB 2: Image / Photo Solver =================
with tab2:
    st.subheader("📷 Photo/Screenshot Solver")
    uploaded_img = st.file_uploader("Upload Image (Question Paper / Diagram / Book photo):", type=["jpg", "jpeg", "png"], key="img_uploader")
    img_prompt = st.text_input("Koi specific question poochhna hai image ke baare me? (Optional)", placeholder="e.g. Solve Question No. 3 or Explain this diagram")

    if st.button("🔍 Analyze Image", key="btn_img"):
        if not uploaded_img:
            st.warning("Pehle koi Image upload karein!")
        elif not api_key:
            st.error("API Key nahi mil rahi! Kripya Streamlit Secrets me GEMINI_API_KEY save karein.")
        else:
            try:
                with st.spinner("GM AI is analyzing image..."):
                    image = Image.open(uploaded_img)
                    st.image(image, caption="Uploaded Image", use_container_width=True)
                    
                    user_query = img_prompt if img_prompt.strip() else "Explain this image in detail and solve any questions present in it."
                    
                    res_text = call_ai(user_query, image=image)

                    st.success("✨ Analysis Complete!")
                    st.markdown(res_text)
            except Exception as e:
                st.error(f"Error: {e}")

# ================= TAB 3: Direct Ask Question =================
with tab3:
    st.subheader("💬 Direct Ask Question")
    user_text_question = st.text_area("Apna question ya topic yahan likhein:", placeholder="e.g. Explain SQL Injection with code example, or What is Cyber Law?")

    if st.button("⚡ Get Answer", key="btn_text"):
        if not user_text_question.strip():
            st.warning("Pehle apna sawaal/text likhein!")
        elif not api_key:
            st.error("API Key nahi mil rahi! Kripya Streamlit Secrets me GEMINI_API_KEY save karein.")
        else:
            try:
                with st.spinner("GM AI is thinking..."):
                    res_text = call_ai(user_text_question)

                    st.success("✨ Answer Generated!")
                    st.markdown(res_text)
            except Exception as e:
                st.error(f"Error: {e}")
