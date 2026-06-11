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

# Flask session 需要 secret key
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "petcareai-dev-secret-key")

# SQLite 資料庫
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///petcare.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# 圖片上傳設定
UPLOAD_FOLDER = os.path.join("static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)

# Flask-Login 設定
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "請先登入後再使用此功能。"

# Groq AI Client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


# =========================
# 工具函式
# =========================

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_photo(file):
    """
    儲存上傳圖片，回傳可供 HTML 顯示的路徑，例如：
    /static/uploads/xxxx.jpg
    """
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


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# =========================
# AI 風險評分
# =========================

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

    high_risk_keywords = ["吐血", "血尿", "抽搐", "昏倒", "呼吸困難", "不吃飯", "持續嘔吐"]
    medium_risk_keywords = ["嘔吐", "拉肚子", "流鼻水", "咳嗽", "精神不好", "發燒"]
    low_risk_keywords = ["打噴嚏", "抓癢", "掉毛", "食慾正常", "精神正常"]

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
# 首頁與功能頁
# =========================

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/features")
def features():
    return render_template("features.html")


# =========================
# 註冊 / 登入 / 登出
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

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

    return render_template(
        "dashboard.html",
        pets=pets,
        pet_count=len(pets)
    )


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

    return render_template("add_pet.html")


@app.route("/pets/<int:pet_id>")
@login_required
def pet_detail(pet_id):
    pet = Pet.query.filter_by(id=pet_id, user_id=current_user.id).first_or_404()
    return render_template("pet_detail.html", pet=pet)


@app.route("/pets/<int:pet_id>/edit", methods=["GET", "POST"])
@login_required
def edit_pet(pet_id):
    pet = Pet.query.filter_by(id=pet_id, user_id=current_user.id).first_or_404()

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

    return render_template("edit_pet.html", pet=pet)


@app.route("/pets/<int:pet_id>/delete", methods=["POST"])
@login_required
def delete_pet(pet_id):
    pet = Pet.query.filter_by(id=pet_id, user_id=current_user.id).first_or_404()

    db.session.delete(pet)
    db.session.commit()

    flash("寵物資料已刪除。")
    return redirect(url_for("pets"))


# =========================
# AI 初步健康建議
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
# 初始化資料庫
# =========================

with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
