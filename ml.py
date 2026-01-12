# ================= ULTRA ADVANCED ML COLLEGE CHATBOT =================

import pandas as pd
import os
import re
import numpy as np
import string
from difflib import SequenceMatcher

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ---------------- LOAD MULTIPLE CSV FILES ----------------
CSV_FILES = ["data.csv", "gcoek_data.csv"]

questions = []
answers = []
files = []

for csv_file in CSV_FILES:
    if not os.path.exists(csv_file):
        print(f"⚠️ Warning: {csv_file} not found, skipping...")
        continue

    df = pd.read_csv(csv_file)

    for i in range(len(df)):
        q = str(df.loc[i, "question"])
        a = str(df.loc[i, "answer"])
        f = ""
        if "file" in df.columns:
            f = str(df.loc[i, "file"])

        questions.append(q)
        answers.append(a)
        files.append(f)

print(f"✅ Loaded {len(questions)} questions")

# ---------------- TEXT NORMALIZATION ----------------
def normalize(text):
    text = text.lower()
    text = text.strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text

questions_norm = [normalize(q) for q in questions]

# ---------------- QUERY EXPANSION (BASIC) ----------------
SYNONYMS = {
    "fees": ["fee", "payment", "charges"],
    "syllabus": ["course", "curriculum"],
    "exam": ["examination", "test"],
    "admission": ["apply", "application", "entry"],
    "calendar": ["schedule", "timetable"]
}

def expand_query(q):
    words = q.split()
    expanded = words.copy()
    for w in words:
        if w in SYNONYMS:
            expanded.extend(SYNONYMS[w])
    return " ".join(expanded)

# ---------------- ML MODELS ----------------

# Word-level semantic model
word_vectorizer = TfidfVectorizer(
    stop_words="english",
    ngram_range=(1, 3),
    min_df=1
)
X_word = word_vectorizer.fit_transform(questions_norm)

# Character-level model (for spelling mistakes)
char_vectorizer = TfidfVectorizer(
    analyzer="char_wb",
    ngram_range=(3, 5)
)
X_char = char_vectorizer.fit_transform(questions_norm)

# ---------------- SIMILARITY FUNCTIONS ----------------
def jaccard_similarity(a, b):
    set1 = set(a.split())
    set2 = set(b.split())
    if not set1 or not set2:
        return 0
    return len(set1 & set2) / len(set1 | set2)

# ---------------- BUILD ANSWER ----------------
def build_answer(ans, file):
    if file and str(file).strip() != "" and str(file).lower() != "nan":
        return f"{ans}\n📄 PDF: {file}"
    else:
        return ans

# ---------------- ULTRA SMART CHATBOT ----------------
def chatbot(user_input):
    user_input = normalize(user_input)
    user_input = expand_query(user_input)

    # Vectorize
    user_word_vec = word_vectorizer.transform([user_input])
    user_char_vec = char_vectorizer.transform([user_input])

    # Similarities
    sim_word = cosine_similarity(user_word_vec, X_word)[0]
    sim_char = cosine_similarity(user_char_vec, X_char)[0]

    # Other scores
    sim_jaccard = np.array([jaccard_similarity(user_input, q) for q in questions_norm])
    sim_seq = np.array([SequenceMatcher(None, user_input, q).ratio() for q in questions_norm])

    # 🔥 ENSEMBLE SCORE (Weighted)
    final_score = (
        0.45 * sim_word +
        0.25 * sim_char +
        0.15 * sim_jaccard +
        0.15 * sim_seq
    )

    best_idx = np.argmax(final_score)
    best_score = final_score[best_idx]

    # Dynamic threshold
    if best_score < 0.12:
        return "🤖 Sorry, I am not confident about this. Please contact college office."

    return build_answer(answers[best_idx], files[best_idx])

# ---------------- CHAT LOOP ----------------
print("\n🤖 ULTRA Advanced AI College Chatbot Started")
print("Type 'exit' to stop\n")

while True:
    user = input("You: ")
    if user.lower() == "exit":
        print("Bot: Thank you! Have a nice day 😊")
        break

    reply = chatbot(user)
    print("Bot:", reply)

# ================= END =================
