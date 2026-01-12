from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import csv, json, os, re
from pydub import AudioSegment
import speech_recognition as sr
import os
from pydub import AudioSegment


# NLP
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

app = Flask(__name__)
app.secret_key = "super_secret_key_123"

# ---------------- CONFIG ----------------
USERS_FILE = "users.json"
CHAT_FILE = "chats.json"
UNKNOWN_CSV = "unknown_questions.csv"

# 🔥 MULTIPLE CSV FILES
CSV_FILES = ["data.csv", "gcoek_data.csv"]

ADMIN_EMAIL = "admin@gmail.com"
ADMIN_PASSWORD = "admin123"

# ---------------- SAFE JSON ----------------
def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def load_users():
    return load_json(USERS_FILE, {})

def save_users(users):
    save_json(USERS_FILE, users)

def load_chats():
    return load_json(CHAT_FILE, {})

def save_chats(chats):
    save_json(CHAT_FILE, chats)

# ---------------- NORMALIZE ----------------
def normalize(text):
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()

# ---------------- BUILD ANSWER (PDF SUPPORT) ----------------
def build_answer(answer, file):
    if file and file.strip() != "":
        filename = file.replace("static/", "")
        link = url_for("static", filename=filename)
        return f"""{answer}<br><a href="{link}" target="_blank">📄 Download PDF</a>"""
    else:
        return answer

# ---------------- SMART NLP MULTI-CSV ANSWER ----------------
def get_answer_from_csv(raw_question):
    user_q = normalize(raw_question)

    all_questions = []
    all_answers = []
    all_files = []

    # Load from ALL CSV files
    for csv_file in CSV_FILES:
        if not os.path.exists(csv_file):
            continue

        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                q = normalize(row.get("question", ""))
                a = row.get("answer", "")
                file = row.get("file", "")

                if q:
                    all_questions.append(q)
                    all_answers.append(a)
                    all_files.append(file)

    if not all_questions:
        return None

    # 1) Direct contains match
    for i, q in enumerate(all_questions):
        if q in user_q or user_q in q:
            return build_answer(all_answers[i], all_files[i])

    # 2) Keyword overlap match
    user_words = set(user_q.split())
    best_i = -1
    best_common = 0

    for i, q in enumerate(all_questions):
        q_words = set(q.split())
        common = len(user_words & q_words)
        if common > best_common:
            best_common = common
            best_i = i

    if best_common >= 1 and best_i != -1:
        return build_answer(all_answers[best_i], all_files[best_i])

    # 3) TF-IDF semantic match
    corpus = all_questions + [user_q]
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    tfidf = vectorizer.fit_transform(corpus)
    similarity = cosine_similarity(tfidf[-1], tfidf[:-1])

    best_score = similarity.max()
    best_idx = similarity.argmax()

    if best_score >= 0.15:
        return build_answer(all_answers[best_idx], all_files[best_idx])

    return None

# ---------------- UNKNOWN ----------------
def save_unknown_question(q):
    if not os.path.exists(UNKNOWN_CSV):
        with open(UNKNOWN_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["question"])
            writer.writeheader()

    with open(UNKNOWN_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["question"])
        writer.writerow({"question": q})

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return redirect("/login")

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET","POST"])
def login():
    if "user" in session:
        return redirect("/dashboard")

    users = load_users()

    if request.method == "POST":
        identity = request.form["identity"].lower().strip()
        password = request.form["password"]

        for username, data in users.items():
            if identity in [username.lower(), data.get("email","").lower(), data.get("phone","")]:
                if check_password_hash(data["password"], password):
                    session.clear()
                    session["user"] = username
                    return redirect("/dashboard")

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

# ---------------- REGISTER ----------------
@app.route("/register", methods=["POST"])
def register():
    users = load_users()

    username = request.form["username"].strip()
    email = request.form["email"].strip()
    phone = request.form["phone"].strip()
    password = request.form["password"]
    confirm = request.form["confirm"]

    if password != confirm:
        return render_template("login.html", error="Password mismatch")

    if username in users:
        return render_template("login.html", error="Username exists")

    users[username] = {
        "email": email,
        "phone": phone,
        "password": generate_password_hash(password)
    }

    save_users(users)
    return redirect("/login")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")
    return render_template("dashboard.html", user=session["user"])

# ---------------- CHAT ----------------
@app.route("/chat", methods=["POST"])
def chat():
    if "user" not in session:
        return jsonify({"reply":"Session expired"})

    msg = request.json["message"]

    answer = get_answer_from_csv(msg)
    if answer is None:
        answer = "I don't know yet. Saved 😊"
        save_unknown_question(msg)

    chats = load_chats()
    user = session["user"]
    chats.setdefault(user, []).append({"question":msg,"answer":answer})
    save_chats(chats)

    return jsonify({"reply":answer})

# ---------------- VOICE ----------------
@app.route("/voice", methods=["POST"])
def voice():
    if "user" not in session:
        return jsonify({"text": "", "reply": "Session expired"})

    if "audio" not in request.files:
        return jsonify({"text": "", "reply": "No audio received"})

    audio_file = request.files["audio"]

    webm_path = "temp.webm"
    wav_path = "temp.wav"

    audio_file.save(webm_path)

    try:
        # Convert webm to wav
        sound = AudioSegment.from_file(webm_path)
        sound = sound.set_channels(1).set_frame_rate(16000)
        sound.export(wav_path, format="wav")

        # Speech recognition
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio = r.record(source)
            text = r.recognize_google(audio)

    except Exception as e:
        print("VOICE ERROR:", e)
        return jsonify({"text": "", "reply": "Sorry, I could not understand your voice"})

    # Delete temp files
    try:
        os.remove(webm_path)
        os.remove(wav_path)
    except:
        pass

    # Get answer from your CSV NLP system
    answer = get_answer_from_csv(text)
    if answer is None:
        answer = "I don't know yet. Saved 😊"
        save_unknown_question(text)

    chats = load_chats()
    user = session["user"]
    chats.setdefault(user, []).append({"question": text, "answer": answer, "type": "voice"})
    save_chats(chats)

    return jsonify({"text": text, "reply": answer})

# ---------------- CHANGE PASSWORD ----------------
@app.route("/change_password", methods=["GET","POST"])
def change_password():
    users = load_users()

    if request.method == "POST":
        identity = request.form.get("username","").lower().strip()
        old_password = request.form.get("old_password")
        new_password = request.form.get("new_password")

        for username, data in users.items():
            if identity in [username.lower(), data.get("email","").lower(), data.get("phone","")]:
                if check_password_hash(data["password"], old_password):
                    users[username]["password"] = generate_password_hash(new_password)
                    save_users(users)
                    session.clear()
                    return redirect(url_for("login"))

        return render_template("change_password.html", error="Invalid credentials")

    return render_template("change_password.html")

# ---------------- RESET PASSWORD ----------------
@app.route("/reset_password", methods=["POST"])
def reset_password():
    data = request.get_json()
    phone = data.get("phone")
    new_password = data.get("password")

    users = load_users()

    for username, u in users.items():
        if u.get("phone") == phone:
            users[username]["password"] = generate_password_hash(new_password)
            save_users(users)
            return jsonify({"success": True})

    return jsonify({"success": False, "msg": "Phone number not found"})

# ================= ADMIN PANEL =================
@app.route("/admin", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        if request.form["email"] == ADMIN_EMAIL and request.form["password"] == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin/dashboard")
        return render_template("admin_login.html", error="Wrong credentials")
    return render_template("admin_login.html")

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect("/admin")

    users = load_users()
    chats = load_chats()
    total_chats = sum(len(v) for v in chats.values())

    return render_template("admin_dashboard.html",
        total_users=len(users),
        total_chats=total_chats
    )

@app.route("/admin/users")
def admin_users():
    if not session.get("admin"):
        return redirect("/admin")

    users = load_users()
    return render_template("admin_users.html", users=users)

@app.route("/admin/edit_user/<username>")
def admin_edit_user(username):
    if not session.get("admin"):
        return redirect("/admin")

    users = load_users()
    return render_template("admin_edit_user.html", username=username, user=users[username])

@app.route("/admin/update_user", methods=["POST"])
def admin_update_user():
    if not session.get("admin"):
        return redirect("/admin")

    users = load_users()
    username = request.form["username"]

    users[username]["email"] = request.form["email"]
    users[username]["phone"] = request.form["phone"]

    if request.form["password"].strip():
        users[username]["password"] = generate_password_hash(request.form["password"])

    save_users(users)
    return redirect("/admin/users")

@app.route("/admin/delete_user/<username>")
def admin_delete_user(username):
    if not session.get("admin"):
        return redirect("/admin")

    users = load_users()
    chats = load_chats()

    if username in users:
        del users[username]
        save_users(users)

    if username in chats:
        del chats[username]
        save_chats(chats)

    return redirect("/admin/users")

@app.route("/admin/chats")
def admin_chats():
    if not session.get("admin"):
        return redirect("/admin")

    chats = load_chats()
    return render_template("admin_chats.html", chats=chats)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/login")

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
