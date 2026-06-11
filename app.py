from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
from groq import Groq
from datetime import datetime
import os

app = Flask(__name__)

# Render / Flask session 需要 secret key
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "petcareai-dev-secret-key")

# SQLite demo database
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "sqlite:///petcare.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "請先登入後再使用此功能。"

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


# =========================
# Database Models
# =========================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    pets = db.relationship("Pet", backref="owner", lazy=True, cascade="all, delete-orphan")


class Pet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    name = db.Column(db.String(100), nullable=False)
    species = db.Column(db.String(50), nullable=False)
    breed = db.Column(db.String(100))
    gender = db.Column(db.String(20))
    age = db.Column(db.String(50))
    weight = db.Column(db.Float)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    health_records = db.relationship(
        "HealthRecord",
        backref="pet",
        lazy=True,
        cascade="all, delete-orphan"
    )

    medical_records = db.relationship(
        "MedicalRecord",
        backref="pet",
        lazy=True,
        cascade="all, delete-orphan"
    )

    reminders = db.relationship(
        "Reminder",
        backref="pet",
        lazy=True,
        cascade="all, delete-orphan"
    )


class HealthRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pet_id = db.Column(db.Integer, db.ForeignKey("pet.id"), nullable=False)

    record_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    weight = db.Column(db.Float)
    appetite = db.Column(db.String(100))
    activity = db.Column(db.String(100))
    symptoms = db.Column(db.Text)
    medication = db.Column(db.Text)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MedicalRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pet_id = db.Column(db.Integer, db.ForeignKey("pet.id"), nullable=False)

    visit_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    clinic_name = db.Column(db.String(150))
    diagnosis = db.Column(db.String(200))
    medicine = db.Column(db.Text)
    doctor_advice = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pet_id = db.Column(db.Integer, db.ForeignKey("pet.id"), nullable=False)

    reminder_type = db.Column(db.String(100), nullable=False)
    reminder_date = db.Column(db.Date, nullable=False)
    note = db.Column(db.Text)
    is_done = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AIConsultation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    pet_name = db.Column(db.String(100))
    species = db.Column(db.String(50))
    breed = db.Column(db.String(100))
    gender = db.Column(db.String(20))
    age = db.Column(db.String(50))
    weight = db.Column(db.String(50))
    symptom = db.Column(db.Text)

    risk_score = db.Column(db.Integer)
    risk_level = db.Column(db.String(50))
    ai_answer = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# =========================
# Helper Functions
# =========================

def parse_date(date_string):
    if not date_string:
        return datetime.utcnow().date()
    return datetime.strptime(date_string, "%Y-%m-%d").date()


def calculate_risk_score(age, weight, symptom):
    score = 0
    symptom = symptom.lower()

    try:
        age = float(age)
    except:
        age = 0

    try:
        weight = float(weight)
    except:
        weight = 0

    if age >= 10:
        score += 20

    if weight <= 2:
        score += 15

    high_risk_keywords = [
        "吐血",
        "血尿",
        "抽搐",
        "昏倒",
        "呼吸困難",
        "不吃飯",
        "持續嘔吐",
    ]

    medium_risk_keywords = [
        "嘔吐",
        "拉肚子",
        "流鼻水",
        "咳嗽",
        "精神不好",
        "發燒",
    ]

    low_risk_keywords = [
        "打噴嚏",
        "抓癢",
        "掉毛",
        "食慾正常",
        "精神正常",
    ]

    for word in high_risk_keywords:
        if word in symptom:
            score += 40

    for word in medium_risk_keywords:
        if word in symptom:
            score += 20

    for word in low_risk_keywords:
        if word in symptom:
            score += 5

    if score >= 70:
        level = "高風險"
        color = "danger"
        advice = "建議盡快就醫或聯絡獸醫。"
    elif score >= 35:
        level = "中風險"
        color = "warning"
        advice = "建議持續觀察，若症狀加重應安排就醫。"
    else:
        level = "低風險"
        color = "success"
        advice = "目前可先觀察，並維持飲食、環境與精神狀況紀錄。"

    return score, level, color, advice


def get_user_pet_or_404(pet_id):
    return Pet.query.filter_by(id=pet_id, user_id=current_user.id).first_or_404()


# =========================
# Public Pages
# =========================

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/features")
def features():
    return render_template("features.html")


# =========================
# Auth
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")

        if not username or not email or not password:
            flash("請完整填寫註冊資料。")
            return redirect(url_for("register"))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("這個 Email 已經註冊過，請直接登入。")
            return redirect(url_for("login"))

        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
        )

        db.session.add(new_user)
        db.session.commit()

        flash("註冊成功，請登入。")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash("Email 或密碼錯誤。")
            return redirect(url_for("login"))

        login_user(user)
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))


# =========================
# Dashboard
# =========================

@app.route("/dashboard")
@login_required
def dashboard():
    pets = Pet.query.filter_by(user_id=current_user.id).order_by(Pet.created_at.desc()).all()

    total_health_records = 0
    total_medical_records = 0
    total_reminders = 0

    for pet in pets:
        total_health_records += len(pet.health_records)
        total_medical_records += len(pet.medical_records)
        total_reminders += len(pet.reminders)

    return render_template(
        "dashboard.html",
        pets=pets,
        total_health_records=total_health_records,
        total_medical_records=total_medical_records,
        total_reminders=total_reminders,
    )


# =========================
# Pet CRUD
# =========================

@app.route("/pets")
@login_required
def pets():
    all_pets = Pet.query.filter_by(user_id=current_user.id).order_by(Pet.created_at.desc()).all()
    return render_template("pets.html", pets=all_pets)


@app.route("/pets/add", methods=["GET", "POST"])
@login_required
def add_pet():
    if request.method == "POST":
        name = request.form.get("name")
        species = request.form.get("species")
        breed = request.form.get("breed")
        gender = request.form.get("gender")
        age = request.form.get("age")
        weight = request.form.get("weight")
        note = request.form.get("note")

        new_pet = Pet(
            user_id=current_user.id,
            name=name,
            species=species,
            breed=breed,
            gender=gender,
            age=age,
            weight=float(weight) if weight else None,
            note=note,
        )

        db.session.add(new_pet)
        db.session.commit()

        return redirect(url_for("pets"))

    return render_template("add_pet.html")


@app.route("/pets/<int:pet_id>")
@login_required
def pet_detail(pet_id):
    pet = get_user_pet_or_404(pet_id)

    health_records = HealthRecord.query.filter_by(pet_id=pet.id).order_by(
        HealthRecord.record_date.desc()
    ).all()

    medical_records = MedicalRecord.query.filter_by(pet_id=pet.id).order_by(
        MedicalRecord.visit_date.desc()
    ).all()

    reminders = Reminder.query.filter_by(pet_id=pet.id).order_by(
        Reminder.reminder_date.asc()
    ).all()

    return render_template(
        "pet_detail.html",
        pet=pet,
        health_records=health_records,
        medical_records=medical_records,
        reminders=reminders,
    )


@app.route("/pets/<int:pet_id>/delete", methods=["POST"])
@login_required
def delete_pet(pet_id):
    pet = get_user_pet_or_404(pet_id)
    db.session.delete(pet)
    db.session.commit()
    return redirect(url_for("pets"))


# =========================
# Health Records
# =========================

@app.route("/pets/<int:pet_id>/health/add", methods=["GET", "POST"])
@login_required
def add_health_record(pet_id):
    pet = get_user_pet_or_404(pet_id)

    if request.method == "POST":
        record_date = parse_date(request.form.get("record_date"))
        weight = request.form.get("weight")
        appetite = request.form.get("appetite")
        activity = request.form.get("activity")
        symptoms = request.form.get("symptoms")
        medication = request.form.get("medication")
        note = request.form.get("note")

        new_record = HealthRecord(
            pet_id=pet.id,
            record_date=record_date,
            weight=float(weight) if weight else None,
            appetite=appetite,
            activity=activity,
            symptoms=symptoms,
            medication=medication,
            note=note,
        )

        db.session.add(new_record)
        db.session.commit()

        return redirect(url_for("pet_detail", pet_id=pet.id))

    return render_template("add_health_record.html", pet=pet)


# =========================
# Medical Records
# =========================

@app.route("/pets/<int:pet_id>/medical/add", methods=["GET", "POST"])
@login_required
def add_medical_record(pet_id):
    pet = get_user_pet_or_404(pet_id)

    if request.method == "POST":
        visit_date = parse_date(request.form.get("visit_date"))
        clinic_name = request.form.get("clinic_name")
        diagnosis = request.form.get("diagnosis")
        medicine = request.form.get("medicine")
        doctor_advice = request.form.get("doctor_advice")

        new_record = MedicalRecord(
            pet_id=pet.id,
            visit_date=visit_date,
            clinic_name=clinic_name,
            diagnosis=diagnosis,
            medicine=medicine,
            doctor_advice=doctor_advice,
        )

        db.session.add(new_record)
        db.session.commit()

        return redirect(url_for("pet_detail", pet_id=pet.id))

    return render_template("add_medical_record.html", pet=pet)


# =========================
# Reminders
# =========================

@app.route("/pets/<int:pet_id>/reminder/add", methods=["GET", "POST"])
@login_required
def add_reminder(pet_id):
    pet = get_user_pet_or_404(pet_id)

    if request.method == "POST":
        reminder_type = request.form.get("reminder_type")
        reminder_date = parse_date(request.form.get("reminder_date"))
        note = request.form.get("note")

        new_reminder = Reminder(
            pet_id=pet.id,
            reminder_type=reminder_type,
            reminder_date=reminder_date,
            note=note,
        )

        db.session.add(new_reminder)
        db.session.commit()

        return redirect(url_for("pet_detail", pet_id=pet.id))

    return render_template("add_reminder.html", pet=pet)


@app.route("/reminders")
@login_required
def reminders():
    pets = Pet.query.filter_by(user_id=current_user.id).all()
    all_reminders = []

    for pet in pets:
        all_reminders.extend(pet.reminders)

    all_reminders = sorted(all_reminders, key=lambda item: item.reminder_date)

    return render_template("reminders.html", reminders=all_reminders)


# =========================
# Medical Record List
# =========================

@app.route("/medical-records")
@login_required
def medical_records():
    pets = Pet.query.filter_by(user_id=current_user.id).all()
    all_medical_records = []

    for pet in pets:
        all_medical_records.extend(pet.medical_records)

    all_medical_records = sorted(
        all_medical_records,
        key=lambda item: item.visit_date,
        reverse=True
    )

    return render_template("medical_records.html", medical_records=all_medical_records)


# =========================
# Health Record List
# =========================

@app.route("/health-records")
@login_required
def health_records():
    pets = Pet.query.filter_by(user_id=current_user.id).all()
    all_health_records = []

    for pet in pets:
        all_health_records.extend(pet.health_records)

    all_health_records = sorted(
        all_health_records,
        key=lambda item: item.record_date,
        reverse=True
    )

    return render_template("health_records.html", health_records=all_health_records)


# =========================
# Report
# =========================

@app.route("/report")
@login_required
def report():
    pets = Pet.query.filter_by(user_id=current_user.id).order_by(Pet.created_at.desc()).all()
    return render_template("report.html", pets=pets)


# =========================
# AI Consultation
# =========================

@app.route("/ai", methods=["POST"])
def ai():
    pet_name = request.form["pet_name"]
    species = request.form["species"]
    breed = request.form["breed"]
    gender = request.form["gender"]
    age = request.form["age"]
    weight = request.form["weight"]
    symptom = request.form["symptom"]

    risk_score, risk_level, risk_color, risk_advice = calculate_risk_score(
        age, weight, symptom
    )

    prompt = f"""
你是一位寵物健康照護助理。

請使用繁體中文回答。
只能提供一般照護建議，不能取代獸醫診斷。
請避免使用 Markdown 星號格式。

寵物基本資料：
名稱：{pet_name}
物種：{species}
品種：{breed}
性別：{gender}
年齡：{age} 歲
體重：{weight} 公斤

使用者描述的症狀：
{symptom}

系統初步風險評分：
{risk_score} 分
風險等級：{risk_level}
系統建議：{risk_advice}

請依照以下格式回答：

一、可能原因
二、居家觀察重點
三、照護建議
四、什麼情況需要就醫
五、提醒：本建議不能取代獸醫診斷
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "你是寵物健康照護助理，請用繁體中文回答，不能取代獸醫診斷。",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.5,
            max_tokens=900,
        )

        answer = response.choices[0].message.content.replace("**", "")

    except Exception as e:
        answer = f"AI 回覆產生失敗，請確認 Render 是否已設定 GROQ_API_KEY。錯誤訊息：{str(e)}"

    if current_user.is_authenticated:
        consultation = AIConsultation(
            user_id=current_user.id,
            pet_name=pet_name,
            species=species,
            breed=breed,
            gender=gender,
            age=age,
            weight=weight,
            symptom=symptom,
            risk_score=risk_score,
            risk_level=risk_level,
            ai_answer=answer,
        )
        db.session.add(consultation)
        db.session.commit()

    pet_info = {
        "pet_name": pet_name,
        "species": species,
        "breed": breed,
        "gender": gender,
        "age": age,
        "weight": weight,
        "symptom": symptom,
    }

    return render_template(
        "home.html",
        answer=answer,
        pet_info=pet_info,
        risk_score=risk_score,
        risk_level=risk_level,
        risk_color=risk_color,
        risk_advice=risk_advice,
    )


# =========================
# Initialize Database
# =========================

with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
