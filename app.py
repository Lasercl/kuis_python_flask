from flask import Flask, render_template, request, redirect, url_for, session, flash
import json, os
import requests
from datetime import datetime
import sqlite3
import random

app = Flask(__name__)


app.secret_key = "rahasia123"
QUIZ_FILE = "quiz.json"

# Load soal dari file JSON
def load_quiz():
    with open(QUIZ_FILE, "r") as f:
        return json.load(f)

# --- koneksi DB ---
def get_db_connection():
    conn = sqlite3.connect("quiz.db")
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/', methods=['GET', 'POST'])
def home():
    weather_data = None

    if request.method == 'POST':
        city = request.form['city']

        # --- 1. Cari koordinat kota ---
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}"
        geo_res = requests.get(geo_url).json()

        if not geo_res.get("results"):
            weather_data = {"error": "Kota tidak ditemukan."}
        else:
            lat = geo_res["results"][0]["latitude"]
            lon = geo_res["results"][0]["longitude"]
            city_name = geo_res["results"][0]["name"]

            # --- 2. Ambil data prakiraan cuaca ---
            forecast_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min&forecast_days=3&timezone=auto"
            weather_res = requests.get(forecast_url).json()

            daily = weather_res["daily"]

            forecast = []
            for i in range(len(daily["time"])):
                date = datetime.strptime(daily["time"][i], "%Y-%m-%d").strftime("%A, %d %B %Y")
                day_temp = daily["temperature_2m_max"][i]
                night_temp = daily["temperature_2m_min"][i]

                forecast.append({
                    "date": date,
                    "day_temp": day_temp,
                    "night_temp": night_temp
                })

            weather_data = {"city": city_name, "forecast": forecast}

    return render_template("home.html", weather=weather_data)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            flash("Registrasi berhasil! Silakan login.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username sudah digunakan!", "error")
        finally:
            conn.close()
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()

        if user:
            session["user"] = username
            flash(f"Selamat datang, {username}!", "success")
            return redirect(url_for("home"))
        else:
            flash("Username atau password salah!", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Anda telah logout.", "info")
    return redirect(url_for("home"))

# @app.route("/quiz", methods=["GET", "POST"])
# def quiz():
#     if "user" not in session:
#         flash("Silakan login terlebih dahulu untuk mengakses kuis.", "error")
#         return redirect(url_for("login"))

#     quiz_data = load_quiz()

#     if request.method == "POST":
#         user_answers = request.form
#         correct = 0
#         total = len(user_answers)

#         for i, q in enumerate(quiz_data):
#             selected = user_answers.get(f"q{i}")
#             if selected == q["answer"]:
#                 correct += 1

#         score = int(correct / total * 100)

#         conn = get_db_connection()
#         c = conn.cursor()
#         c.execute(
#             "INSERT INTO scores (username, score, timestamp) VALUES (?, ?, ?)",
#             (session["user"], score, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
#         )
#         conn.commit()
#         conn.close()

#         return render_template("result.html", score=score, total=total)

#     # GET → tampilkan 5 soal acak
#     quiz_data = random.sample(quiz_data, 5)
#     return render_template("quiz.html", quiz=quiz_data)
@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    if "user" not in session:
        flash("Silakan login terlebih dahulu untuk mengakses kuis.", "error")
        return redirect(url_for("login"))

    quiz_data = load_quiz()

    # POST: hitung skor
    if request.method == "POST":
        user_answers = request.form
        correct = 0
        total = len(user_answers)
        username = session["user"]

        # gunakan daftar soal yang terakhir ditampilkan dari session
        last_quiz = session.get("last_quiz")
        if not last_quiz:
            flash("Sesi kuis berakhir. Silakan coba lagi.", "error")
            return redirect(url_for("quiz"))

        for i, q in enumerate(last_quiz):
            selected = user_answers.get(f"q{i}")
            if selected == q["answer"]:
                correct += 1

        score = int(correct / total * 100) if total > 0 else 0

        # Simpan ke database
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM scores WHERE username = ?", (username,))
        existing = c.fetchone()

        if existing:
            if score > existing["score"]:
                # c.execute("UPDATE scores SET score = ? WHERE username = ?", (score, username))
                 c.execute(
                     "UPDATE scores SET score = ?, timestamp = ? WHERE username = ?",
                    (score, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username),
                 )
        else:
            c.execute(
                "INSERT INTO scores (username, score, timestamp) VALUES (?, ?, ?)",
                (session["user"], score, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )

    
        conn.commit()
        conn.close()

        # hapus kuis dari session biar gak dipakai ulang
        session.pop("last_quiz", None)

        return render_template("result.html", score=score, total=total)

    # GET: tampilkan soal acak
    quiz_data = random.sample(quiz_data, 5)
    session["last_quiz"] = quiz_data  # simpan soal yang ditampilkan

    return render_template("quiz.html", quiz=quiz_data)



@app.route("/leaderboard")
def leaderboard():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("quiz.db")
    c = conn.cursor()
    c.execute("""
        SELECT username, score, timestamp
        FROM scores
        ORDER BY score DESC, timestamp ASC
        LIMIT 10
    """)
    data = c.fetchall()
    conn.close()

    return render_template("leaderboard.html", data=data)


if __name__ == "__main__":
    app.run(debug=True)






# @app.route('/quiz/submit', methods=['POST'])
# def quiz_submit():
#     if "user" not in session:
#         return redirect(url_for('login'))

#     score = 0
#     conn = get_db_connection()
#     cur = conn.cursor()
#     cur.execute("SELECT * FROM questions")
#     questions = cur.fetchall()

#     for q in questions:
#         selected = request.form.get(str(q["id"]))
#         if selected == q["correct_answer"]:
#             score += 1

#     # simpan skor user ke DB
#     cur.execute("INSERT INTO scores (username, score) VALUES (?, ?)", (session["user"], score))
#     conn.commit()
#     conn.close()

#     return render_template('quiz_result.html', score=score)
