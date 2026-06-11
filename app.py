from flask import Flask, render_template, request
from groq import Groq
import os

app = Flask(__name__)

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


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


# =========================
# 首頁：AI 初步健康建議
# =========================
@app.route("/")
def home():
    return render_template("home.html")


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
# 8 大功能總覽頁
# =========================
@app.route("/features")
def features():
    return render_template("features.html")


# =========================
# 功能 1：會員登入與帳號管理
# =========================
@app.route("/login")
def login():
    return render_template("login.html")


# =========================
# 功能 2：寵物資料管理
# =========================
@app.route("/pets")
def pets():
    return render_template("pets.html")


# =========================
# 功能 3：健康紀錄管理
# =========================
@app.route("/health-records")
def health_records():
    return render_template("health_records.html")


# =========================
# 功能 4：疫苗與驅蟲提醒
# =========================
@app.route("/reminders")
def reminders():
    return render_template("reminders.html")


# =========================
# 功能 5：就醫紀錄管理
# =========================
@app.route("/medical-records")
def medical_records():
    return render_template("medical_records.html")


# =========================
# 功能 6：AI 初步健康建議
# 目前功能已放在首頁 /
# =========================
@app.route("/ai-advice")
def ai_advice():
    return render_template("home.html")


# =========================
# 功能 7：健康趨勢儀表板
# =========================
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


# =========================
# 功能 8：健康報告匯出
# =========================
@app.route("/report")
def report():
    return render_template("report.html")


if __name__ == "__main__":
    app.run(debug=True)
