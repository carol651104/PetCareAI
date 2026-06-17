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
from sqlalchemy import text, inspect
import os
import uuid
import json
import re

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
# 免費版限制設定
# =========================

FREE_PET_LIMIT = 1
FREE_HEALTH_RECORD_LIMIT = 10
FREE_MEDICAL_RECORD_LIMIT = 5
FREE_REMINDER_LIMIT = 5
FREE_AI_LIMIT = 3


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


def is_premium_user(user=None):
    user = user or current_user
    return bool(getattr(user, "is_premium", False)) or getattr(user, "plan", "free") == "premium"


def get_current_user_pet_ids():
    pets = Pet.query.filter_by(user_id=current_user.id).all()
    return [pet.id for pet in pets]


def count_user_health_records():
    pet_ids = get_current_user_pet_ids()
    if not pet_ids:
        return 0

    return HealthRecord.query.filter(
        HealthRecord.pet_id.in_(pet_ids)
    ).count()


def count_user_medical_records():
    pet_ids = get_current_user_pet_ids()
    if not pet_ids:
        return 0

    return MedicalRecord.query.filter(
        MedicalRecord.pet_id.in_(pet_ids)
    ).count()


def count_user_reminders():
    pet_ids = get_current_user_pet_ids()
    if not pet_ids:
        return 0

    return Reminder.query.filter(
        Reminder.pet_id.in_(pet_ids)
    ).count()


# =========================
# 資料庫 Model
# =========================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    plan = db.Column(db.String(20), default="free")
    is_premium = db.Column(db.Boolean, default=False)
    ai_usage_count = db.Column(db.Integer, default=0)

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


def ensure_user_plan_columns():
    """
    如果舊資料庫沒有 plan / is_premium / ai_usage_count，可用這個函式補欄位。
    目前沒有在啟動時自動執行，避免 Render 部署時卡住。
    """
    inspector = inspect(db.engine)
    table_name = User.__tablename__

    if table_name not in inspector.get_table_names():
        return

    existing_columns = [col["name"] for col in inspector.get_columns(table_name)]

    with db.engine.begin() as conn:
        if "plan" not in existing_columns:
            conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN plan VARCHAR(20) DEFAULT \'free\''))

        if "is_premium" not in existing_columns:
            conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN is_premium BOOLEAN DEFAULT FALSE'))

        if "ai_usage_count" not in existing_columns:
            conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN ai_usage_count INTEGER DEFAULT 0'))

        conn.execute(text(f'UPDATE "{table_name}" SET plan = \'free\' WHERE plan IS NULL'))
        conn.execute(text(f'UPDATE "{table_name}" SET is_premium = FALSE WHERE is_premium IS NULL'))
        conn.execute(text(f'UPDATE "{table_name}" SET ai_usage_count = 0 WHERE ai_usage_count IS NULL'))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# =========================
# AI 語意風險評分 + 規則保底
# =========================

def get_risk_meta(score):
    score = max(0, min(int(score), 100))

    if score >= 70:
        return score, "高風險", "danger", "建議盡快就醫或聯絡獸醫，尤其若症狀持續、加重或伴隨精神食慾異常。"
    elif score >= 35:
        return score, "中風險", "warning", "建議持續觀察，記錄症狀頻率、食慾、精神與排便狀況；若惡化應安排就醫。"
    else:
        return score, "低風險", "success", "目前可先觀察，維持飲食、飲水、精神與排便紀錄；若症狀反覆仍建議諮詢獸醫。"


def extract_json_from_ai_text(text):
    if not text:
        return None

    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def apply_emergency_guardrail(score, symptom):
    symptom_text = symptom.lower().strip() if symptom else ""

    emergency_keywords = [
        "吐血",
        "血便",
        "血尿",
        "抽搐",
        "癲癇",
        "昏倒",
        "休克",
        "呼吸困難",
        "喘不過氣",
        "無法站立",
        "站不起來",
        "走路不穩",
        "意識不清",
        "癱瘓",
        "中毒",
        "誤食",
        "吃到藥",
        "吃到巧克力",
        "吃到洋蔥",
        "吃到葡萄",
        "完全不吃",
        "完全不喝",
    ]

    matched_keywords = []

    for word in emergency_keywords:
        if word in symptom_text:
            matched_keywords.append(word)

    if matched_keywords:
        score = max(score, 85)

    return score, matched_keywords


def calibrate_ai_score(score, symptom):
    """
    分數校正：
    避免 AI 對輕微症狀過度保守，例如「吐一次」被判成高風險。
    但如果有嚴重症狀，則不降分。
    """
    symptom_text = symptom.lower().strip() if symptom else ""

    mild_vomit_keywords = [
        "吐了一次",
        "吐一次",
        "只吐一次",
        "嘔吐一次",
        "又吐了一次",
        "今天吐了一次",
    ]

    stable_keywords = [
        "精神正常",
        "食慾正常",
        "活動正常",
        "有吃飯",
        "有喝水",
        "精神還好",
        "食慾還好",
        "看起來正常",
    ]

    severe_keywords = [
        "一直吐",
        "連續吐",
        "吐很多次",
        "吐好幾次",
        "不吃飯",
        "不喝水",
        "完全不吃",
        "完全不喝",
        "精神不好",
        "沒精神",
        "很虛弱",
        "吐血",
        "血便",
        "血尿",
        "呼吸困難",
        "喘不過氣",
        "抽搐",
        "昏倒",
        "站不起來",
        "中毒",
        "誤食",
    ]

    has_mild_vomit = any(word in symptom_text for word in mild_vomit_keywords)
    has_stable = any(word in symptom_text for word in stable_keywords)
    has_severe = any(word in symptom_text for word in severe_keywords)

    if has_mild_vomit and not has_severe:
        score = min(score, 35)

    if has_stable and not has_severe:
        score = min(score, 30)

    if has_mild_vomit and has_stable and not has_severe:
        score = min(score, 25)

    return max(0, min(int(score), 100))


def fallback_rule_risk_score(age, weight, symptom):
    score = 0
    symptom_text = symptom.lower().strip() if symptom else ""

    try:
        age_value = float(age)
    except Exception:
        age_value = 0

    try:
        weight_value = float(weight)
    except Exception:
        weight_value = 0

    if age_value >= 10:
        score += 15

    if weight_value > 0 and weight_value <= 2:
        score += 10

    high_risk_keywords = [
        "吐血",
        "血便",
        "血尿",
        "抽搐",
        "昏倒",
        "呼吸困難",
        "喘不過氣",
        "站不起來",
        "中毒",
        "誤食",
    ]

    medium_risk_keywords = [
        "吐",
        "嘔吐",
        "拉肚子",
        "腹瀉",
        "不吃",
        "不吃飯",
        "精神不好",
        "沒精神",
        "發燒",
        "咳嗽",
        "一直吐",
        "連續吐",
        "持續",
        "反覆",
    ]

    low_risk_keywords = [
        "打噴嚏",
        "抓癢",
        "掉毛",
        "食慾正常",
        "精神正常",
        "只吐一次",
        "一次",
    ]

    for word in high_risk_keywords:
        if word in symptom_text:
            score += 60

    for word in medium_risk_keywords:
        if word in symptom_text:
            score += 20

    for word in low_risk_keywords:
        if word in symptom_text:
            score -= 5

    score = calibrate_ai_score(score, symptom)
    score, emergency_keywords = apply_emergency_guardrail(score, symptom)
    score, level, color, advice = get_risk_meta(score)

    reason = "AI 評分失敗時使用備援規則。"
    if emergency_keywords:
        reason += " 偵測到高風險關鍵字：" + "、".join(emergency_keywords)

    return score, level, color, advice, reason


def calculate_ai_risk_score(
    pet_name,
    species,
    breed,
    gender,
    age,
    weight,
    symptom,
    health_history_text,
    medical_history_text,
    reminder_text
):
    risk_prompt = f"""
你是一位寵物健康風險評估助理。

請根據寵物基本資料、近期健康紀錄、就醫紀錄、提醒事項與使用者描述的症狀，評估目前健康風險。

重要限制：
1. 你不能提供正式診斷。
2. 你只能做初步健康風險分級。
3. 請使用繁體中文。
4. 請只回傳 JSON，不要加任何 Markdown，不要加任何說明文字。
5. risk_score 必須是 0 到 100 的整數。
6. risk_level 只能是「低風險」、「中風險」、「高風險」三種之一。
7. 不可以因為單一輕微症狀就直接評為高風險。
8. 若使用者描述症狀輕微，且精神、食慾、活動力仍正常，應傾向低風險或中低風險。
9. 若資訊不足，請保守評估為中低風險，不要直接評為高風險。
10. 若出現呼吸困難、抽搐、昏倒、吐血、血便、血尿、中毒、誤食、無法站立、完全不吃不喝等情況，才應評為高風險。

請依照以下評分標準：

0 到 20 分：
輕微症狀，且精神、食慾、活動力大致正常。
例如：偶爾吐一次、打噴嚏、輕微抓癢、短暫食慾變化。

21 到 34 分：
低到中度風險，需要觀察。
例如：吐一次但原因不明、輕微拉肚子、精神稍差但仍可活動。

35 到 69 分：
中風險，需要密切觀察，若持續或加重應就醫。
例如：反覆嘔吐、拉肚子多次、食慾明顯下降、精神不好、發燒、咳嗽加重。

70 到 100 分：
高風險，建議盡快就醫或聯絡獸醫。
例如：呼吸困難、抽搐、昏倒、吐血、血便、血尿、疑似中毒、誤食危險物、無法站立、完全不吃不喝、持續劇烈嘔吐。

特別注意：
- 「吐了一次」本身通常不應評為高風險。
- 「又吐了一次」若沒有其他嚴重症狀，通常應落在 20 到 35 分。
- 「吐了一次，但精神正常、食慾正常」通常應落在 10 到 25 分。
- 「一直吐、不吃飯、精神很差」才應落在 60 分以上。
- 「呼吸困難、抽搐、吐血、血便、站不起來」才應落在 80 分以上。

寵物基本資料：
名稱：{pet_name}
物種：{species}
品種：{breed}
性別：{gender}
年齡：{age} 歲
體重：{weight} 公斤

近期健康紀錄：
{health_history_text}

近期就醫紀錄：
{medical_history_text}

目前待完成提醒：
{reminder_text}

使用者描述的問題或症狀：
{symptom}

請回傳以下 JSON 格式：

{{
  "risk_score": 0,
  "risk_level": "低風險",
  "risk_reason": "請用一句話說明評分原因",
  "care_priority": "請用一句話說明目前最重要的觀察或處理方向"
}}
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "你是寵物健康風險評估助理，只能輸出 JSON，不能取代獸醫診斷。",
                },
                {
                    "role": "user",
                    "content": risk_prompt,
                },
            ],
            temperature=0.2,
            max_tokens=500,
        )

        raw_text = response.choices[0].message.content
        risk_data = extract_json_from_ai_text(raw_text)

        if not risk_data:
            raise ValueError("AI 未回傳有效 JSON")

        score = int(risk_data.get("risk_score", 0))
        risk_reason = risk_data.get("risk_reason", "AI 已根據症狀描述與歷史紀錄進行語意風險評估。")
        care_priority = risk_data.get("care_priority", "")

        score = max(0, min(score, 100))

        score = calibrate_ai_score(score, symptom)
        score, emergency_keywords = apply_emergency_guardrail(score, symptom)

        if emergency_keywords:
            risk_reason += " 系統同時偵測到高風險關鍵字：" + "、".join(emergency_keywords) + "，因此已提高風險等級。"

        score, level, color, advice = get_risk_meta(score)

        if care_priority:
            advice = care_priority + " " + advice

        return score, level, color, advice, risk_reason

    except Exception as e:
        score, level, color, advice, reason = fallback_rule_risk_score(age, weight, symptom)
        reason += f" AI 語意評分暫時失敗，已使用備援規則。錯誤：{str(e)}"
        return score, level, color, advice, reason


def calculate_risk_score(age, weight, symptom):
    score, level, color, advice, reason = fallback_rule_risk_score(age, weight, symptom)
    return score, level, color, advice


# =========================
# 首頁 / AI 助理頁 / 功能頁
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

    return render_template(
        "home.html",
        pets=pets,
        ai_usage_count=current_user.ai_usage_count or 0,
        ai_limit=FREE_AI_LIMIT,
        is_premium=is_premium_user(),
    )


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
            plan="free",
            is_premium=False,
            ai_usage_count=0,
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
# 商業模式 / 方案頁 / 模擬升級
# =========================

@app.route("/pricing")
@login_required
def pricing():
    return render_template(
        "pricing.html",
        is_premium=is_premium_user(),
        ai_usage_count=current_user.ai_usage_count or 0,
        ai_limit=FREE_AI_LIMIT,
    )


@app.route("/upgrade", methods=["POST"])
@login_required
def upgrade():
    current_user.plan = "premium"
    current_user.is_premium = True
    db.session.commit()

    flash("已成功模擬升級 Premium 方案，完整功能已開放。")
    return redirect(url_for("dashboard"))


@app.route("/downgrade", methods=["POST"])
@login_required
def downgrade():
    current_user.plan = "free"
    current_user.is_premium = False
    db.session.commit()

    flash("已切換回 Free 免費版。")
    return redirect(url_for("pricing"))


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
        pet_count=len(pets),
        health_record_count=total_health_records,
        medical_record_count=total_medical_records,
        pending_reminder_count=total_pending_reminders,
        total_health_records=total_health_records,
        total_medical_records=total_medical_records,
        total_reminders=total_pending_reminders,
        total_all_reminders=total_all_reminders,
        total_ai_records=total_ai_records,
        pending_reminders=upcoming_reminders,
        upcoming_reminders=upcoming_reminders,
        latest_health_record=latest_health_record,
        latest_health_records=latest_health_records,
        ai_consult_count=total_ai_records,
        is_premium=is_premium_user(),
        current_plan=current_user.plan or "free",
        ai_usage_count=current_user.ai_usage_count or 0,
        ai_limit=FREE_AI_LIMIT,
    )


@app.route("/health-trends")
@login_required
def health_trends():
    if not is_premium_user():
        flash("健康趨勢圖表為 Premium 付費版功能，請先升級後再使用。")
        return redirect(url_for("pricing"))

    pets = Pet.query.filter_by(user_id=current_user.id).order_by(Pet.created_at.desc()).all()
    pet_ids = [pet.id for pet in pets]

    health_records = []
    medical_records = []
    reminders = []

    weight_trend_data = []
    appetite_stats = {}
    activity_stats = {}
    care_trend_map = {}

    total_health_records = 0
    total_medical_records = 0
    total_reminders = 0
    total_care_records = 0

    if pet_ids:
        health_records = HealthRecord.query.filter(
            HealthRecord.pet_id.in_(pet_ids)
        ).order_by(HealthRecord.record_date.asc(), HealthRecord.id.asc()).all()

        medical_records = MedicalRecord.query.filter(
            MedicalRecord.pet_id.in_(pet_ids)
        ).order_by(MedicalRecord.visit_date.asc(), MedicalRecord.id.asc()).all()

        reminders = Reminder.query.filter(
            Reminder.pet_id.in_(pet_ids)
        ).order_by(Reminder.reminder_date.asc(), Reminder.id.asc()).all()

        total_health_records = len(health_records)
        total_medical_records = len(medical_records)
        total_reminders = len(reminders)
        total_care_records = total_health_records + total_medical_records + total_reminders

        for record in health_records:
            if record.weight is not None:
                weight_trend_data.append({
                    "date": record.record_date.strftime("%Y-%m-%d") if record.record_date else "",
                    "pet_name": record.pet.name if record.pet else "未指定寵物",
                    "weight": float(record.weight),
                })

            appetite = record.appetite.strip() if record.appetite else "未填寫"
            if appetite == "":
                appetite = "未填寫"
            appetite_stats[appetite] = appetite_stats.get(appetite, 0) + 1

            activity = record.activity.strip() if record.activity else "未填寫"
            if activity == "":
                activity = "未填寫"
            activity_stats[activity] = activity_stats.get(activity, 0) + 1

            if record.record_date:
                month_key = record.record_date.strftime("%Y-%m")
                if month_key not in care_trend_map:
                    care_trend_map[month_key] = {
                        "month": month_key,
                        "health": 0,
                        "medical": 0,
                        "reminder": 0,
                        "total": 0,
                    }
                care_trend_map[month_key]["health"] += 1
                care_trend_map[month_key]["total"] += 1

        for record in medical_records:
            if record.visit_date:
                month_key = record.visit_date.strftime("%Y-%m")
                if month_key not in care_trend_map:
                    care_trend_map[month_key] = {
                        "month": month_key,
                        "health": 0,
                        "medical": 0,
                        "reminder": 0,
                        "total": 0,
                    }
                care_trend_map[month_key]["medical"] += 1
                care_trend_map[month_key]["total"] += 1

        for reminder in reminders:
            if reminder.reminder_date:
                month_key = reminder.reminder_date.strftime("%Y-%m")
                if month_key not in care_trend_map:
                    care_trend_map[month_key] = {
                        "month": month_key,
                        "health": 0,
                        "medical": 0,
                        "reminder": 0,
                        "total": 0,
                    }
                care_trend_map[month_key]["reminder"] += 1
                care_trend_map[month_key]["total"] += 1

    appetite_chart_data = [
        {"label": key, "value": value}
        for key, value in appetite_stats.items()
    ]

    activity_chart_data = [
        {"label": key, "value": value}
        for key, value in activity_stats.items()
    ]

    care_trend_data = [
        care_trend_map[key]
        for key in sorted(care_trend_map.keys())
    ]

    return render_template(
        "health_trends.html",
        pets=pets,
        health_records=health_records,
        medical_records=medical_records,
        reminders=reminders,
        weight_trend_data=weight_trend_data,
        appetite_chart_data=appetite_chart_data,
        activity_chart_data=activity_chart_data,
        care_trend_data=care_trend_data,
        total_health_records=total_health_records,
        total_medical_records=total_medical_records,
        total_reminders=total_reminders,
        total_care_records=total_care_records,
    )


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
    if not is_premium_user():
        current_pet_count = Pet.query.filter_by(user_id=current_user.id).count()
        if current_pet_count >= FREE_PET_LIMIT:
            flash("免費版最多只能建立 1 隻寵物，升級 Premium 後可管理多隻寵物。")
            return redirect(url_for("pricing"))

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

    if not is_premium_user():
        if count_user_health_records() >= FREE_HEALTH_RECORD_LIMIT:
            flash("免費版健康紀錄最多 10 筆，升級 Premium 後可新增不限筆數健康紀錄。")
            return redirect(url_for("pricing"))

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

    if not is_premium_user():
        if count_user_medical_records() >= FREE_MEDICAL_RECORD_LIMIT:
            flash("免費版就醫紀錄最多 5 筆，升級 Premium 後可新增不限筆數就醫紀錄。")
            return redirect(url_for("pricing"))

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

    if not is_premium_user():
        if count_user_reminders() >= FREE_REMINDER_LIMIT:
            flash("免費版提醒事項最多 5 筆，升級 Premium 後可新增不限筆數提醒。")
            return redirect(url_for("pricing"))

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
    if not is_premium_user():
        current_ai_count = current_user.ai_usage_count or 0

        if current_ai_count >= FREE_AI_LIMIT:
            flash("免費版 AI 諮詢次數已用完，請升級 Premium 以繼續使用 AI 健康助理。")
            return redirect(url_for("pricing"))

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

    risk_score, risk_level, risk_color, risk_advice, risk_reason = calculate_ai_risk_score(
        pet_name=pet_name,
        species=species,
        breed=breed,
        gender=gender,
        age=age,
        weight=weight,
        symptom=symptom,
        health_history_text=health_history_text,
        medical_history_text=medical_history_text,
        reminder_text=reminder_text,
    )

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

AI 語意風險評分：
{risk_score} 分
風險等級：{risk_level}
AI 評分原因：
{risk_reason}

系統建議：
{risk_advice}

請根據寵物基本資料、歷史健康紀錄、就醫紀錄、提醒事項，以及這次使用者描述的問題，提供較個人化的初步照護建議。

請依照以下格式回答：

一、AI 風險判斷摘要
請用 2 到 3 句話說明目前為什麼是 {risk_level}，並整合以下原因：
{risk_reason}

二、可能原因
請列出可能造成此狀況的原因，但不要做確定診斷。

三、需要觀察的重點
請列出使用者接下來應該觀察的項目，例如食慾、精神、排便、飲水、嘔吐次數、症狀是否加重。

四、居家照護建議
請提供安全、保守的一般照護建議。

五、什麼情況需要就醫
請明確列出需要盡快就醫或聯絡獸醫的情況。

六、提醒
請提醒本建議不能取代獸醫診斷。
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
            max_tokens=1000,
        )

        answer = response.choices[0].message.content.replace("**", "")

    except Exception as e:
        answer = f"""
一、AI 風險判斷摘要
目前系統已完成風險評分，但 AI 建議文字產生失敗。

二、可能原因
暫時無法產生完整 AI 建議。

三、需要觀察的重點
請先觀察寵物的精神、食慾、飲水、排便、活動力與症狀是否持續或加重。

四、居家照護建議
可先記錄症狀發生時間與頻率，並避免自行餵食人用藥物。

五、什麼情況需要就醫
若出現呼吸困難、抽搐、吐血、血便、持續嘔吐、精神明顯變差或完全不吃不喝，請盡快聯絡獸醫。

六、提醒
本建議不能取代獸醫診斷。

錯誤訊息：{str(e)}
"""

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

    if not is_premium_user():
        current_user.ai_usage_count = (current_user.ai_usage_count or 0) + 1

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
        ai_usage_count=current_user.ai_usage_count or 0,
        ai_limit=FREE_AI_LIMIT,
        is_premium=is_premium_user(),
    )


# =========================
# 健康報告
# =========================

@app.route("/report")
@login_required
def report():
    if not is_premium_user():
        flash("健康報告匯出為 Premium 付費版功能，請先升級後再使用。")
        return redirect(url_for("pricing"))

    pets = Pet.query.filter_by(user_id=current_user.id).order_by(Pet.created_at.desc()).all()
    ai_records = AIConsultation.query.filter_by(user_id=current_user.id).order_by(AIConsultation.created_at.desc()).all()

    return render_template("report.html", pets=pets, ai_records=ai_records)


with app.app_context():
    db.create_all()
    # 不自動執行 ensure_user_plan_columns()，避免 Render 部署時卡住。
    # 如果舊資料庫缺少 plan / is_premium / ai_usage_count，再另外處理。


if __name__ == "__main__":
    app.run(debug=True)
