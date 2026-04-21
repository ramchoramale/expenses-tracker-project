from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from sklearn.linear_model import LinearRegression
import numpy as np
from twilio.rest import Client
import random
import datetime

app = Flask(__name__)
CORS(app)

app.config["JWT_SECRET_KEY"] = "super-secret-key"
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = datetime.timedelta(days=1)

jwt = JWTManager(app)

# ---------- TWILIO CONFIG ----------
TWILIO_SID = "YOUR_SID"
TWILIO_AUTH = "YOUR_AUTH"
TWILIO_PHONE = "+1234567890"

client = Client(TWILIO_SID, TWILIO_AUTH)

otp_store = {}  # {phone: (otp, expiry)}

# ---------- DATABASE ----------
def get_db():
    return sqlite3.connect("database.db")

def init():
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            email TEXT UNIQUE,
            password TEXT,
            phone TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses(
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            category TEXT,
            date TEXT
        )
        """)

init()

# ---------- REGISTER ----------
@app.route("/register", methods=["POST"])
def register():
    data = request.json

    if not data.get("email") or not data.get("password"):
        return jsonify({"msg": "Missing fields"}), 400

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO users(email,password,phone)
            VALUES(?,?,?)
            """, (
                data["email"],
                generate_password_hash(data["password"]),
                data.get("phone")
            ))
        return jsonify({"msg": "Registered successfully"})
    except:
        return jsonify({"msg": "User already exists"}), 400

# ---------- LOGIN ----------
@app.route("/login", methods=["POST"])
def login():
    data = request.json

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (data["email"],))
        user = cur.fetchone()

    if user and check_password_hash(user[2], data["password"]):
        token = create_access_token(identity=user[0])
        return jsonify({"token": token})

    return jsonify({"msg": "Invalid credentials"}), 401

# ---------- SEND OTP ----------
@app.route("/send-otp", methods=["POST"])
def send_otp():
    phone = request.json.get("phone")

    if not phone:
        return jsonify({"msg": "Phone required"}), 400

    otp = str(random.randint(100000, 999999))
    expiry = datetime.datetime.now() + datetime.timedelta(minutes=5)

    otp_store[phone] = (otp, expiry)

    try:
        client.messages.create(
            body=f"Your OTP is {otp}",
            from_=TWILIO_PHONE,
            to=phone
        )
    except:
        return jsonify({"msg": "OTP send failed"}), 500

    return jsonify({"msg": "OTP sent"})

# ---------- VERIFY OTP ----------
@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    phone = request.json.get("phone")
    otp = request.json.get("otp")

    if phone not in otp_store:
        return jsonify({"msg": "No OTP found"}), 400

    stored_otp, expiry = otp_store[phone]

    if datetime.datetime.now() > expiry:
        return jsonify({"msg": "OTP expired"}), 400

    if stored_otp != otp:
        return jsonify({"msg": "Invalid OTP"}), 400

    # find user by phone
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE phone=?", (phone,))
        user = cur.fetchone()

    if not user:
        return jsonify({"msg": "User not registered"}), 404

    token = create_access_token(identity=user[0])
    return jsonify({"token": token})

# ---------- ADD EXPENSE ----------
@app.route("/add", methods=["POST"])
@jwt_required()
def add():
    uid = get_jwt_identity()
    data = request.json

    if not data.get("amount") or not data.get("category"):
        return jsonify({"msg": "Missing fields"}), 400

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO expenses(user_id,amount,category,date)
        VALUES(?,?,?,?)
        """, (
            uid,
            float(data["amount"]),
            data["category"],
            datetime.datetime.now().isoformat()
        ))

    return jsonify({"msg": "Expense added"})

# ---------- VIEW ----------
@app.route("/view")
@jwt_required()
def view():
    uid = get_jwt_identity()

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT amount,category,date 
        FROM expenses WHERE user_id=?
        """, (uid,))
        data = cur.fetchall()

    return jsonify(data)

# ---------- ANALYTICS ----------
@app.route("/analytics")
@jwt_required()
def analytics():
    uid = get_jwt_identity()

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT amount,category,date 
        FROM expenses WHERE user_id=?
        """, (uid,))
        rows = cur.fetchall()

    by_category = {}
    by_month = {}

    for amt, cat, date in rows:
        by_category[cat] = by_category.get(cat, 0) + amt

        month = date[:7]
        by_month[month] = by_month.get(month, 0) + amt

    return jsonify({
        "category": by_category,
        "monthly": by_month
    })

# ---------- AI PREDICTION ----------
@app.route("/predict")
@jwt_required()
def predict():
    uid = get_jwt_identity()

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT amount FROM expenses WHERE user_id=?", (uid,))
        data = cur.fetchall()

    values = [d[0] for d in data]

    if len(values) < 5:
        return jsonify({"msg": "Not enough data"})

    X = np.array(range(len(values))).reshape(-1, 1)
    y = np.array(values)

    model = LinearRegression()
    model.fit(X, y)

    pred = model.predict([[len(values)]])[0]

    return jsonify({"prediction": float(pred)})

# ---------- RUN ----------
if __name__ == "__main__":
    app.run()