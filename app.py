import streamlit as st
import PyPDF2
from docx import Document
import requests
import re
import pandas as pd
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

st.set_page_config(page_title="Quiz Me APP", layout="wide")
st.title("🧠 Quiz Me from a Document!")

OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

uploaded_file = st.file_uploader("📄 Upload a PDF or DOCX file", type=["pdf", "docx"])

@st.cache_data
def extract_text(file):
    if file.name.endswith(".pdf"):
        reader = PyPDF2.PdfReader(file)
        return "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
    elif file.name.endswith(".docx"):
        doc = Document(file)
        return "\n".join([para.text for para in doc.paragraphs])
    return ""

document_text = ""
if uploaded_file:
    document_text = extract_text(uploaded_file)
    st.success("✅ Document text extracted successfully!")

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
    return response.json()["choices"][0]["message"]["content"]

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

# Initialize session state keys
for key in ["quiz_running", "question_num", "last_question", "score", "history", "answer_submitted", "feedback", "user_choice"]:
    if key not in st.session_state:
        if key in ["question_num", "score"]:
            st.session_state[key] = 0
        elif key == "history":
            st.session_state[key] = []
        elif key == "answer_submitted":
            st.session_state[key] = False
        else:
            st.session_state[key] = None

def load_next_question():
    st.session_state.question_num += 1
    output = generate_question(document_text)
    parsed = parse_question(output) if output else None
    if parsed:
        st.session_state.last_question = parsed
        st.session_state.feedback = None
        st.session_state.answer_submitted = False
        st.session_state.user_choice = None
    else:
        st.error("❌ Could not generate or parse the question.")
        st.session_state.quiz_running = False

def start_quiz():
    st.session_state.quiz_running = True
    st.session_state.question_num = 0
    st.session_state.score = 0
    st.session_state.last_question = None
    st.session_state.history = []
    st.session_state.answer_submitted = False
    st.session_state.feedback = None
    st.session_state.user_choice = None
    load_next_question()

def submit_answer():
    if st.session_state.user_choice:
        q = st.session_state.last_question
        user_choice = st.session_state.user_choice
        correct = user_choice == q["correct"]
        feedback = "✅ Correct!" if correct else f"❌ Incorrect. Correct answer: {q['correct']}) {q['options'][q['correct']]}"
        st.session_state.score += int(correct)
        st.session_state.history.append({
            "question": q["question"],
            "options": q["options"],
            "your_answer": user_choice,
            "correct": q["correct"],
            "feedback": feedback,
        })
        st.session_state.feedback = feedback
        st.session_state.answer_submitted = True

def next_question():
    load_next_question()

if document_text and not st.session_state.quiz_running:
    if st.button("🚀 Start Quiz", on_click=start_quiz):
        pass

if st.session_state.quiz_running and st.session_state.last_question:
    q = st.session_state.last_question
    st.markdown(f"### 📝 Question {st.session_state.question_num}")
    st.markdown(f"**{q['question']}**")

    if not st.session_state.answer_submitted:
        st.radio(
            "Choose your answer:",
            options=list(q["options"].keys()),
            format_func=lambda x: f"{x}) {q['options'][x]}",
            key="user_choice",
            index=0,
        )
        if st.button("✅ Submit Answer", on_click=submit_answer):
            pass
    else:
        st.success(st.session_state.feedback)
        col1, col2 = st.columns([1, 3])
        with col2:
            if st.button("➡️ Next Question", on_click=next_question):
                st.session_state.user_choice = None  # reset choice for next q

    if st.button("🛑 End Quiz"):
        st.session_state.quiz_running = False

# Final Results
if not st.session_state.quiz_running and st.session_state.history:
    total = len(st.session_state.history)
    score = st.session_state.score
    percent = (score / total) * 100
    st.header("📋 Final Results")
    st.markdown(f"**Score:** `{score}` out of `{total}` ({percent:.2f}%)")

    if percent == 100:
        st.success("🏆 Perfect score! You're a master of this topic!")
    elif percent >= 75:
        st.info("💡 Great job! A little review could make it perfect.")
    else:
        st.warning("🧐 Needs improvement. Review the material and try again!")

    def convert_to_csv():
        df = pd.DataFrame([
            {
                "Question": h["question"],
                "Your Answer": h["your_answer"],
                "Correct Answer": h["correct"],
                "Result": "Correct" if h["your_answer"] == h["correct"] else "Incorrect",
                "Feedback": h["feedback"]
            }
            for h in st.session_state.history
        ])
        return df.to_csv(index=False).encode("utf-8")

    def convert_to_pdf():
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        c.setFont("Helvetica-Bold", 16)
        y = height - 50
        c.drawCentredString(width / 2, y, "Quiz Results")
        y -= 40

        for i, h in enumerate(st.session_state.history, 1):
            c.setFont("Helvetica-Bold", 12)
            c.drawString(40, y, f"Q{i}: {h['question']}")
            y -= 20

            c.setFont("Helvetica", 12)
            for key, val in h["options"].items():
                if key == h["correct"]:
                    mark = "✅"
                elif key == h["your_answer"]:
                    mark = "🟠"
                else:
                    mark = "  "
                c.drawString(60, y, f"{mark} {key}) {val}")
                y -= 15

            c.drawString(60, y, f"Feedback: {h['feedback']}")
            y -= 30

            if y < 100:
                c.showPage()
                y = height - 50
                c.setFont("Helvetica-Bold", 16)
                c.drawCentredString(width / 2, y, "Quiz Results (cont.)")
                y -= 40

        c.save()
        buffer.seek(0)
        return buffer

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📥 Download Results as CSV",
            convert_to_csv(),
            file_name="quiz_results.csv",
            mime="text/csv"
        )
    with col2:
        st.download_button(
            "📥 Download Results as PDF",
            data=convert_to_pdf(),
            file_name="quiz_results.pdf",
            mime="application/pdf"
        )

if st.sidebar.checkbox("📊 Show Quiz History") and st.session_state.history:
    st.sidebar.header("🕘 Quiz History")
    for i, entry in enumerate(st.session_state.history):
        st.sidebar.markdown(f"**Q{i+1}:** {entry['question']}")
        for k, v in entry["options"].items():
            prefix = (
                "✅" if k == entry["correct"] else "🟠" if k == entry["your_answer"] else "-"
            )
            st.sidebar.markdown(f"{prefix} {k}) {v}")
        st.sidebar.markdown(f"**Feedback:** {entry['feedback']}")
        st.sidebar.markdown("---")
