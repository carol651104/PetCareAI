from flask import Flask, render_template, request
from groq import Groq
import os

app = Flask(__name__)

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/ai", methods=["POST"])
def ai():

    symptom = request.form["symptom"]

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": """
你是一位寵物健康助理。

請使用繁體中文回答。

只能提供一般照護建議。

不可取代獸醫診斷。
"""
            },
            {
                "role": "user",
                "content": symptom
            }
        ]
    )

    answer = response.choices[0].message.content

    return render_template(
        "home.html",
        answer=answer
    )

if __name__ == "__main__":
    app.run(debug=True)