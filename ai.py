from flask import Flask, jsonify
import sqlite3
import numpy as np
from sklearn.linear_model import LinearRegression

app = Flask(__name__)

@app.route("/predict")
def predict():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("SELECT amount FROM expenses")
    data = cur.fetchall()

    values = [d[0] for d in data]

    if len(values) < 3:
        return {"msg":"Not enough data"}

    X = np.array(range(len(values))).reshape(-1,1)
    y = np.array(values)

    model = LinearRegression()
    model.fit(X,y)

    pred = model.predict([[len(values)]])[0]

    return jsonify({"prediction": float(pred)})

app.run(debug=True)