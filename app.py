import streamlit as st
import PyPDF2
from docx import Document
import requests
import re

st.set_page_config(page_title="Quiz Me from Document", layout="wide")
st.title("🧠 Quiz Me from a Document!")

# Load OpenRouter API key from secrets
OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# File uploader
uploaded_file = st.file_uploader("📄 Upload a PDF or DOCX file", type=["pdf", "docx"])

@st.cache_data
def extract_text(file):
    if file.name.endswith(".pdf"):
        reader = PyPDF2.PdfReader(file)
        texts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                texts.append(text)
        return "\n".join(texts)
    elif file.name.endswith(".docx"):
        doc = Document(file)
        return "\n".join([para.text for para in doc.paragraphs])
    return ""

document_text = ""
if uploaded_file:
    document_text = extract_text(uploaded_file)
    st.success("✅ Document text extracted successfully!")

# Generate quiz question via OpenRouter API
def generate_question(text):
    prompt = f"""
Based on the following document, generate a single multiple choice question (4 options: A, B, C, D) with a randomized correct answer.

Clearly format the output as:
Question: ...
A) ...
B) ...
C) ...
D) ...
Correct Answer: X

Document:
\"\"\"{text[:4000]}\"\"\"
"""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "meta-llama/llama-3-8b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1000,
    }
    response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload)
    if response.status_code != 200:
        st.error(f"API Error {response.status_code}: {response.text}")
        return None
    data = response.json()
    return data["choices"][0]["message"]["content"]

# Parse the question text into structured data
def parse_question(llm_output):
    pattern = (
        r"Question:\s*(.*?)\n"
        r"A\)\s*(.*?)\n"
        r"B\)\s*(.*?)\n"
        r"C\)\s*(.*?)\n"
        r"D\)\s*(.*?)\n"
        r".*Correct Answer:\s*([ABCD])"
    )
    match = re.search(pattern, llm_output, re.DOTALL)
    if not match:
        return None
    return {
        "question": match.group(1).strip(),
        "options": {
            "A": match.group(2).strip(),
            "B": match.group(3).strip(),
            "C": match.group(4).strip(),
            "D": match.group(5).strip(),
        },
        "correct": match.group(6).strip(),
        "raw": llm_output,
    }

# Initialize session state
if "quiz_running" not in st.session_state:
    st.session_state.quiz_running = False
if "question_num" not in st.session_state:
    st.session_state.question_num = 0
if "last_question" not in st.session_state:
    st.session_state.last_question = None
if "score" not in st.session_state:
    st.session_state.score = 0
if "history" not in st.session_state:
    st.session_state.history = []

# Start quiz button
if document_text and not st.session_state.quiz_running:
    if st.button("🚀 Start Quiz"):
        st.session_state.quiz_running = True
        st.session_state.question_num = 0
        st.session_state.score = 0
        st.session_state.last_question = None
        st.session_state.history = []

# Quiz UI and logic
if st.session_state.quiz_running:
    if st.session_state.last_question is None:
        output = generate_question(document_text)
        if output:
            parsed = parse_question(output)
            if parsed:
                st.session_state.last_question = parsed
            else:
                st.error("Failed to parse the question from the API response.")
                st.stop()
        else:
            st.error("Failed to generate question from the API.")
            st.stop()

    q = st.session_state.last_question
    st.markdown(f"### 📝 Question {st.session_state.question_num + 1}")
    st.write(q["question"])

    user_choice = st.radio(
        "Choose your answer:",
        options=list(q["options"].keys()),
        format_func=lambda x: f"{x}) {q['options'][x]}",
        key=st.session_state.question_num,
    )

    if st.button("✅ Submit Answer"):
        correct = (user_choice == q["correct"])
        feedback = (
            "✅ Correct!" if correct else f"❌ Incorrect. Correct answer: {q['correct']}) {q['options'][q['correct']]}"
        )
        st.session_state.score += int(correct)
        st.session_state.history.append(
            {
                "question": q["question"],
                "options": q["options"],
                "your_answer": user_choice,
                "correct": q["correct"],
                "feedback": feedback,
            }
        )
        st.success(feedback)
        st.session_state.last_question = None

    if st.button("➡️ Next Question"):
        st.session_state.question_num += 1
       

    if st.button("🛑 End Quiz"):
        st.session_state.quiz_running = False
        st.success("🎉 Quiz ended.")

# Show final results
if not st.session_state.quiz_running and st.session_state.history:
    total = len(st.session_state.history)
    score = st.session_state.score
    percent = (score / total) * 100
    st.header("📋 Final Results")
    st.markdown(f"**Score:** {score} out of {total} ({percent:.2f}%)")

    if percent == 100:
        st.success("🏆 Perfect score! You're a master of this topic!")
    elif percent >= 75:
        st.info("💡 Great job! A little review could make it perfect.")
    else:
        st.warning("🧐 Needs improvement. Review the material and try again!")

# Sidebar quiz history
if st.sidebar.checkbox("📊 Show Quiz History") and st.session_state.history:
    st.sidebar.header("🕘 Quiz History")
    for i, entry in enumerate(st.session_state.history):
        st.sidebar.markdown(f"**Q{i+1}:** {entry['question']}")
        for k, v in entry["options"].items():
            prefix = (
                "✅" if k == entry["correct"] else "❌" if k == entry["your_answer"] else "-"
            )
            st.sidebar.markdown(f"{prefix} {k}) {v}")
        st.sidebar.markdown(f"**Feedback:** {entry['feedback']}")
        st.sidebar.markdown("---")
