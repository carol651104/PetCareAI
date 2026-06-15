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
from werkzeug.utils import secure_filename
from groq import Groq
from datetime import datetime
import os
import uuid

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "petcareai-dev-secret-key")

database_url = os.getenv("DATABASE_URL", "sqlite:///petcare.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_FOLDER = os.path.join("static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "請先登入後再使用此功能。"

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


# =========================
# 工具函式
# =========================

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_photo(file):
    if not file or file.filename == "":
        return None

    if not allowed_file(file.filename):
        return None

    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[1].lower()
    new_filename = f"{uuid.uuid4().hex}.{ext}"

    save_path = os.path.join(app.config["UPLOAD_FOLDER"], new_filename)
    file.save(save_path)

    return f"/static/uploads/{new_filename}"


def parse_date(date_string):
    if not date_string:
        return datetime.utcnow().date()

    return datetime.strptime(date_string, "%Y-%m-%d").date()


def get_user_pet_or_404(pet_id):
    return Pet.query.filter_by(id=pet_id, user_id=current_user.id).first_or_404()


def get_user_health_record_or_404(record_id):
    record = HealthRecord.query.get_or_404(record_id)
    pet = get_user_pet_or_404(record.pet_id)
    return record, pet


def get_user_medical_record_or_404(record_id):
    record = MedicalRecord.query.get_or_404(record_id)
    pet = get_user_pet_or_404(record.pet_id)
    return record, pet


def get_user_reminder_or_404(reminder_id):
    reminder = Reminder.query.get_or_404(reminder_id)
    pet = get_user_pet_or_404(reminder.pet_id)
    return reminder, pet


# =========================
# 資料庫 Model
# =========================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    pets = db.relationship(
        "Pet",
        backref="owner",
        lazy=True,
        cascade="all, delete-orphan"
    )


class Pet(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    name = db.Column(db.String(100), nullable=False)
    species = db.Column(db.String(50), nullable=False)
    breed = db.Column(db.String(100))
    gender = db.Column(db.String(20))
    age = db.Column(db.String(50))
    weight = db.Column(db.Float)
    photo_url = db.Column(db.String(255))
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
    note = db.Column(db.Text)

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
    pet_id = db.Column(db.Integer, db.ForeignKey("pet.id"), nullable=True)

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
# AI 風險評分
# =========================

def calculate_risk_score(age, weight, symptom):
    score = 0
    symptom = symptom.lower() if symptom else ""

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

    if weight <= 2 and weight > 0:
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


# =========================
# 首頁 / AI 助理頁 / 健康檢查
# =========================

@app.route("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/ai-assistant")
@login_required
def ai_assistant():
    pets = Pet.query.filter_by(user_id=current_user.id).order_by(Pet.created_at.desc()).all()
    return render_template("home.html", pets=pets)


@app.route("/features")
def features():
    return render_template("features.html")


@app.route("/healthz")
def healthz():
    return "OK", 200


# =========================
# 會員註冊 / 登入 / 登出
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

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

        login_user(new_user)
        flash("註冊成功，已自動登入。")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if not user:
            flash("尚無此帳號，請先註冊。")
            return redirect(url_for("login"))

        if not check_password_hash(user.password_hash, password):
            flash("Email 或密碼錯誤。")
            return redirect(url_for("login"))

        login_user(user)
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# =========================
# Dashboard / 健康趨勢圖表
# =========================

@app.route("/dashboard")
@login_required
def dashboard():
    pets = Pet.query.filter_by(user_id=current_user.id).order_by(Pet.created_at.desc()).all()
    pet_ids = [pet.id for pet in pets]

    if pet_ids:
        total_health_records = HealthRecord.query.filter(
            HealthRecord.pet_id.in_(pet_ids)
        ).count()

        total_medical_records = MedicalRecord.query.filter(
            MedicalRecord.pet_id.in_(pet_ids)
        ).count()

        total_all_reminders = Reminder.query.filter(
            Reminder.pet_id.in_(pet_ids)
        ).count()

        total_pending_reminders = Reminder.query.filter(
            Reminder.pet_id.in_(pet_ids),
            Reminder.is_done == False
        ).count()

        upcoming_reminders = Reminder.query.filter(
            Reminder.pet_id.in_(pet_ids),
            Reminder.is_done == False
        ).order_by(Reminder.reminder_date.asc()).limit(5).all()

        latest_health_records = HealthRecord.query.filter(
            HealthRecord.pet_id.in_(pet_ids)
        ).order_by(HealthRecord.record_date.desc()).limit(5).all()

        latest_health_record = HealthRecord.query.filter(
            HealthRecord.pet_id.in_(pet_ids)
        ).order_by(HealthRecord.record_date.desc(), HealthRecord.id.desc()).first()

    else:
        total_health_records = 0
        total_medical_records = 0
        total_all_reminders = 0
        total_pending_reminders = 0
        upcoming_reminders = []
        latest_health_records = []
        latest_health_record = None

    total_ai_records = AIConsultation.query.filter_by(user_id=current_user.id).count()

    return render_template(
        "dashboard.html",
        pets=pets,

        # 上排統計卡片使用
        pet_count=len(pets),
        health_record_count=total_health_records,
        medical_record_count=total_medical_records,
        pending_reminder_count=total_pending_reminders,

        # 如果你的舊 dashboard.html 還有用這些變數，也可以正常顯示
        total_health_records=total_health_records,
        total_medical_records=total_medical_records,
        total_reminders=total_pending_reminders,
        total_all_reminders=total_all_reminders,
        total_ai_records=total_ai_records,

        # 下排四張卡片使用
        pending_reminders=upcoming_reminders,
        upcoming_reminders=upcoming_reminders,
        latest_health_record=latest_health_record,
        latest_health_records=latest_health_records,
        ai_consult_count=total_ai_records,
    )


@app.route("/health-trends")
@login_required
def health_trends():
    pets = Pet.query.filter_by(user_id=current_user.id).order_by(Pet.created_at.desc()).all()
    pet_ids = [pet.id for pet in pets]

    health_records = []
    weight_trend_data = []
    appetite_stats = {
        "正常": 0,
        "偏少": 0,
        "偏多": 0,
        "未填寫": 0,
    }
    activity_stats = {
        "正常": 0,
        "偏低": 0,
        "活躍": 0,
        "未填寫": 0,
    }

    if pet_ids:
        health_records = HealthRecord.query.filter(
            HealthRecord.pet_id.in_(pet_ids)
        ).order_by(HealthRecord.record_date.asc(), HealthRecord.id.asc()).all()

        for record in health_records:
            if record.weight is not None:
                weight_trend_data.append({
                    "date": record.record_date.strftime("%Y-%m-%d") if record.record_date else "",
                    "pet_name": record.pet.name if record.pet else "未指定寵物",
                    "weight": record.weight,
                })

            appetite = record.appetite.strip() if record.appetite else "未填寫"
            if appetite in appetite_stats:
                appetite_stats[appetite] += 1
            else:
                appetite_stats["未填寫"] += 1

            activity = record.activity.strip() if record.activity else "未填寫"
            if activity in activity_stats:
                activity_stats[activity] += 1
            else:
                activity_stats["未填寫"] += 1

    return render_template(
        "health_trends.html",
        pets=pets,
        health_records=health_records,
        weight_trend_data=weight_trend_data,
        appetite_stats=appetite_stats,
        activity_stats=activity_stats,
    )


# 同時保留底線版本，避免模板裡如果寫 url_for("health_trends") 或連到 /health_trends 發生錯誤
@app.route("/health_trends")
@login_required
def health_trends_alias():
    return redirect(url_for("health_trends"))


# =========================
# 寵物資料 CRUD
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

        if not name or not species:
            flash("請至少填寫寵物名稱與物種。")
            return redirect(url_for("add_pet"))

        photo_file = request.files.get("photo_file")
        photo_url = save_uploaded_photo(photo_file)

        new_pet = Pet(
            user_id=current_user.id,
            name=name,
            species=species,
            breed=breed,
            gender=gender,
            age=age,
            weight=float(weight) if weight else None,
            photo_url=photo_url,
            note=note,
        )

        db.session.add(new_pet)
        db.session.commit()

        flash("寵物資料新增成功。")
        return redirect(url_for("pets"))

    return render_template("pet_form.html", mode="add", pet=None)


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

    ai_records = AIConsultation.query.filter_by(
        user_id=current_user.id,
        pet_id=pet.id
    ).order_by(AIConsultation.created_at.desc()).all()

    return render_template(
        "pet_detail.html",
        pet=pet,
        health_records=health_records,
        medical_records=medical_records,
        reminders=reminders,
        ai_records=ai_records,
    )


@app.route("/pets/<int:pet_id>/edit", methods=["GET", "POST"])
@login_required
def edit_pet(pet_id):
    pet = get_user_pet_or_404(pet_id)

    if request.method == "POST":
        pet.name = request.form.get("name")
        pet.species = request.form.get("species")
        pet.breed = request.form.get("breed")
        pet.gender = request.form.get("gender")
        pet.age = request.form.get("age")

        weight = request.form.get("weight")
        pet.weight = float(weight) if weight else None

        pet.note = request.form.get("note")

        photo_file = request.files.get("photo_file")
        new_photo_url = save_uploaded_photo(photo_file)

        if new_photo_url:
            pet.photo_url = new_photo_url

        db.session.commit()

        flash("寵物資料已更新。")
        return redirect(url_for("pet_detail", pet_id=pet.id))

    return render_template("pet_form.html", mode="edit", pet=pet)


@app.route("/pets/<int:pet_id>/delete", methods=["POST"])
@login_required
def delete_pet(pet_id):
    pet = get_user_pet_or_404(pet_id)

    db.session.delete(pet)
    db.session.commit()

    flash("寵物資料已刪除。")
    return redirect(url_for("pets"))


# =========================
# 健康紀錄 CRUD
# =========================

@app.route("/health-records")
@login_required
def health_records():
    user_pets = Pet.query.filter_by(user_id=current_user.id).all()
    pet_ids = [pet.id for pet in user_pets]

    records = []
    if pet_ids:
        records = HealthRecord.query.filter(
            HealthRecord.pet_id.in_(pet_ids)
        ).order_by(HealthRecord.record_date.desc()).all()

    return render_template("health_records.html", records=records)


@app.route("/pets/<int:pet_id>/health/add", methods=["GET", "POST"])
@login_required
def add_health_record(pet_id):
    pet = get_user_pet_or_404(pet_id)

    if request.method == "POST":
        record = HealthRecord(
            pet_id=pet.id,
            record_date=parse_date(request.form.get("record_date")),
            weight=float(request.form.get("weight")) if request.form.get("weight") else None,
            appetite=request.form.get("appetite"),
            activity=request.form.get("activity"),
            symptoms=request.form.get("symptoms"),
            medication=request.form.get("medication"),
            note=request.form.get("note"),
        )

        db.session.add(record)
        db.session.commit()

        flash("健康紀錄新增成功。")
        return redirect(url_for("pet_detail", pet_id=pet.id))

    return render_template("health_form.html", mode="add", pet=pet, record=None)


@app.route("/health/<int:record_id>/edit", methods=["GET", "POST"])
@login_required
def edit_health_record(record_id):
    record, pet = get_user_health_record_or_404(record_id)

    if request.method == "POST":
        record.record_date = parse_date(request.form.get("record_date"))
        record.weight = float(request.form.get("weight")) if request.form.get("weight") else None
        record.appetite = request.form.get("appetite")
        record.activity = request.form.get("activity")
        record.symptoms = request.form.get("symptoms")
        record.medication = request.form.get("medication")
        record.note = request.form.get("note")

        db.session.commit()

        flash("健康紀錄已更新。")
        return redirect(url_for("pet_detail", pet_id=pet.id))

    return render_template("health_form.html", mode="edit", pet=pet, record=record)


@app.route("/health/<int:record_id>/delete", methods=["POST"])
@login_required
def delete_health_record(record_id):
    record, pet = get_user_health_record_or_404(record_id)

    db.session.delete(record)
    db.session.commit()

    flash("健康紀錄已刪除。")
    return redirect(url_for("pet_detail", pet_id=pet.id))


# =========================
# 就醫紀錄 CRUD
# =========================

@app.route("/medical-records")
@login_required
def medical_records():
    user_pets = Pet.query.filter_by(user_id=current_user.id).all()
    pet_ids = [pet.id for pet in user_pets]

    records = []
    if pet_ids:
        records = MedicalRecord.query.filter(
            MedicalRecord.pet_id.in_(pet_ids)
        ).order_by(MedicalRecord.visit_date.desc()).all()

    return render_template("medical_records.html", records=records)


@app.route("/pets/<int:pet_id>/medical/add", methods=["GET", "POST"])
@login_required
def add_medical_record(pet_id):
    pet = get_user_pet_or_404(pet_id)

    if request.method == "POST":
        record = MedicalRecord(
            pet_id=pet.id,
            visit_date=parse_date(request.form.get("visit_date")),
            clinic_name=request.form.get("clinic_name"),
            diagnosis=request.form.get("diagnosis"),
            medicine=request.form.get("medicine"),
            doctor_advice=request.form.get("doctor_advice"),
            note=request.form.get("note"),
        )

        db.session.add(record)
        db.session.commit()

        flash("就醫紀錄新增成功。")
        return redirect(url_for("pet_detail", pet_id=pet.id))

    return render_template("medical_form.html", mode="add", pet=pet, record=None)


@app.route("/medical/<int:record_id>/edit", methods=["GET", "POST"])
@login_required
def edit_medical_record(record_id):
    record, pet = get_user_medical_record_or_404(record_id)

    if request.method == "POST":
        record.visit_date = parse_date(request.form.get("visit_date"))
        record.clinic_name = request.form.get("clinic_name")
        record.diagnosis = request.form.get("diagnosis")
        record.medicine = request.form.get("medicine")
        record.doctor_advice = request.form.get("doctor_advice")
        record.note = request.form.get("note")

        db.session.commit()

        flash("就醫紀錄已更新。")
        return redirect(url_for("pet_detail", pet_id=pet.id))

    return render_template("medical_form.html", mode="edit", pet=pet, record=record)


@app.route("/medical/<int:record_id>/delete", methods=["POST"])
@login_required
def delete_medical_record(record_id):
    record, pet = get_user_medical_record_or_404(record_id)

    db.session.delete(record)
    db.session.commit()

    flash("就醫紀錄已刪除。")
    return redirect(url_for("pet_detail", pet_id=pet.id))


# =========================
# 提醒事項 CRUD
# =========================

@app.route("/reminders")
@login_required
def reminders():
    user_pets = Pet.query.filter_by(user_id=current_user.id).all()
    pet_ids = [pet.id for pet in user_pets]

    reminders_list = []
    if pet_ids:
        reminders_list = Reminder.query.filter(
            Reminder.pet_id.in_(pet_ids)
        ).order_by(Reminder.is_done.asc(), Reminder.reminder_date.asc()).all()

    return render_template("reminders.html", reminders=reminders_list)


@app.route("/pets/<int:pet_id>/reminder/add", methods=["GET", "POST"])
@login_required
def add_reminder(pet_id):
    pet = get_user_pet_or_404(pet_id)

    if request.method == "POST":
        reminder = Reminder(
            pet_id=pet.id,
            reminder_type=request.form.get("reminder_type"),
            reminder_date=parse_date(request.form.get("reminder_date")),
            note=request.form.get("note"),
            is_done=False,
        )

        db.session.add(reminder)
        db.session.commit()

        flash("提醒事項新增成功。")
        return redirect(url_for("pet_detail", pet_id=pet.id))

    return render_template("reminder_form.html", mode="add", pet=pet, reminder=None)


@app.route("/reminder/<int:reminder_id>/edit", methods=["GET", "POST"])
@login_required
def edit_reminder(reminder_id):
    reminder, pet = get_user_reminder_or_404(reminder_id)

    if request.method == "POST":
        reminder.reminder_type = request.form.get("reminder_type")
        reminder.reminder_date = parse_date(request.form.get("reminder_date"))
        reminder.note = request.form.get("note")
        reminder.is_done = True if request.form.get("is_done") == "on" else False

        db.session.commit()

        flash("提醒事項已更新。")
        return redirect(url_for("pet_detail", pet_id=pet.id))

    return render_template("reminder_form.html", mode="edit", pet=pet, reminder=reminder)


@app.route("/reminder/<int:reminder_id>/done", methods=["POST"])
@login_required
def toggle_reminder_done(reminder_id):
    reminder, pet = get_user_reminder_or_404(reminder_id)

    reminder.is_done = not reminder.is_done
    db.session.commit()

    flash("提醒狀態已更新。")
    return redirect(request.referrer or url_for("reminders"))


@app.route("/reminder/<int:reminder_id>/delete", methods=["POST"])
@login_required
def delete_reminder(reminder_id):
    reminder, pet = get_user_reminder_or_404(reminder_id)

    db.session.delete(reminder)
    db.session.commit()

    flash("提醒事項已刪除。")
    return redirect(url_for("pet_detail", pet_id=pet.id))


# =========================
# AI 個人化健康助理
# =========================

@app.route("/ai", methods=["POST"])
@login_required
def ai():
    pet_id = request.form.get("pet_id")

    selected_pet = None
    if pet_id:
        selected_pet = Pet.query.filter_by(id=pet_id, user_id=current_user.id).first()

    if selected_pet:
        pet_name = selected_pet.name
        species = selected_pet.species
        breed = selected_pet.breed or ""
        gender = selected_pet.gender or ""
        age = selected_pet.age or ""
        weight = str(selected_pet.weight or "")

        recent_health_records = HealthRecord.query.filter_by(pet_id=selected_pet.id)\
            .order_by(HealthRecord.record_date.desc())\
            .limit(5)\
            .all()

        recent_medical_records = MedicalRecord.query.filter_by(pet_id=selected_pet.id)\
            .order_by(MedicalRecord.visit_date.desc())\
            .limit(3)\
            .all()

        pending_reminders = Reminder.query.filter_by(
            pet_id=selected_pet.id,
            is_done=False
        ).order_by(Reminder.reminder_date.asc()).limit(5).all()
    else:
        pet_name = request.form.get("pet_name", "")
        species = request.form.get("species", "")
        breed = request.form.get("breed", "")
        gender = request.form.get("gender", "")
        age = request.form.get("age", "")
        weight = request.form.get("weight", "")

        recent_health_records = []
        recent_medical_records = []
        pending_reminders = []

    symptom = request.form.get("symptom", "")

    risk_score, risk_level, risk_color, risk_advice = calculate_risk_score(
        age, weight, symptom
    )

    health_history_text = "無近期健康紀錄"
    if recent_health_records:
        health_history_text = "\n".join([
            f"{r.record_date}：體重 {r.weight or '未填寫'} kg，食慾 {r.appetite or '未填寫'}，活動量 {r.activity or '未填寫'}，症狀 {r.symptoms or '無'}，用藥 {r.medication or '無'}"
            for r in recent_health_records
        ])

    medical_history_text = "無近期就醫紀錄"
    if recent_medical_records:
        medical_history_text = "\n".join([
            f"{r.visit_date}：診所 {r.clinic_name or '未填寫'}，診斷 {r.diagnosis or '未填寫'}，藥物 {r.medicine or '無'}，醫囑 {r.doctor_advice or '無'}"
            for r in recent_medical_records
        ])

    reminder_text = "無待完成提醒"
    if pending_reminders:
        reminder_text = "\n".join([
            f"{r.reminder_date}：{r.reminder_type}，備註 {r.note or '無'}"
            for r in pending_reminders
        ])

    prompt = f"""
你是一位寵物健康照護助理。

請使用繁體中文回答。
只能提供一般照護建議，不能取代獸醫診斷。
請避免使用 Markdown 星號格式。

以下是系統中已建立的寵物基本資料：
名稱：{pet_name}
物種：{species}
品種：{breed}
性別：{gender}
年齡：{age} 歲
體重：{weight} 公斤

以下是近期健康紀錄：
{health_history_text}

以下是近期就醫紀錄：
{medical_history_text}

以下是目前待完成提醒：
{reminder_text}

使用者這次描述的問題或症狀：
{symptom}

系統初步風險評分：
{risk_score} 分
風險等級：{risk_level}
系統建議：{risk_advice}

請根據寵物基本資料、歷史健康紀錄、就醫紀錄、提醒事項，以及這次使用者描述的問題，提供較個人化的初步照護建議。

請依照以下格式回答：

一、可能原因
二、需要觀察的重點
三、居家照護建議
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

    consultation = AIConsultation(
        user_id=current_user.id,
        pet_id=selected_pet.id if selected_pet else None,
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

    pets = Pet.query.filter_by(user_id=current_user.id).order_by(Pet.created_at.desc()).all()

    return render_template(
        "home.html",
        pets=pets,
        answer=answer,
        pet_info=pet_info,
        risk_score=risk_score,
        risk_level=risk_level,
        risk_color=risk_color,
        risk_advice=risk_advice,
    )


# =========================
# 健康報告
# =========================

@app.route("/report")
@login_required
def report():
    pets = Pet.query.filter_by(user_id=current_user.id).order_by(Pet.created_at.desc()).all()
    ai_records = AIConsultation.query.filter_by(user_id=current_user.id).order_by(AIConsultation.created_at.desc()).all()

    return render_template("report.html", pets=pets, ai_records=ai_records)


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
