
import os
import re
import math
import sqlite3
import secrets
from datetime import datetime, timedelta

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash
)

app = Flask(__name__)

app.secret_key = os.environ.get(
    "PAYBRIDGE_SECRET_KEY",
    "paybridge-academic-change-this-before-deployment"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "paybridge.db")


# ==================================================
# DATABASE CONNECTION
# ==================================================

def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


# ==================================================
# INITIALIZE DATABASE
# ==================================================

def initialize_database():
    connection = get_db()

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id TEXT UNIQUE NOT NULL,
                amount REAL NOT NULL,
                card_last4 TEXT NOT NULL,
                status TEXT NOT NULL,
                risk_score INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        connection.commit()

    finally:
        connection.close()


# ==================================================
# RISK SCORING
# ==================================================

def calculate_risk(amount, card_number):
    """
    Basic educational risk-scoring logic.
    This is not a production fraud detection system.
    """

    score = 10

    if amount >= 5000:
        score += 20

    if amount >= 20000:
        score += 25

    if amount >= 50000:
        score += 25

    if card_number.endswith("0000"):
        score += 30

    return min(score, 100)


# ==================================================
# PAYMENT PROCESSING
# ==================================================

def process_payment(amount, card_number):
    """
    Records a simulated payment transaction.
    No real payment is processed.
    """

    risk_score = calculate_risk(amount, card_number)

    # Apply the project's transaction decision rules.
    if card_number.endswith("0000") or risk_score >= 80:
        status = "DECLINED"
    else:
        status = "APPROVED"

    transaction_id = "PB-" + secrets.token_hex(5).upper()

    connection = get_db()

    try:
        connection.execute("""
            INSERT INTO transactions (
                transaction_id,
                amount,
                card_last4,
                status,
                risk_score,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            transaction_id,
            amount,
            card_number[-4:],
            status,
            risk_score,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        connection.commit()

    finally:
        connection.close()

    return transaction_id, status, risk_score


# ==================================================
# HOME PAGE
# ==================================================

@app.route("/")
def index():
    return render_template("index.html")


# ==================================================
# PAYMENT PAGE
# ==================================================

@app.route("/payment", methods=["GET", "POST"])
def payment():

    if request.method == "GET":
        return render_template("payment.html")

    # Read submitted values.
    raw_card_number = request.form.get(
        "card_number", ""
    ).strip()

    expiry = request.form.get(
        "expiry", ""
    ).strip()

    cvv = request.form.get(
        "cvv", ""
    ).strip()

    amount_text = request.form.get(
        "amount", ""
    ).strip()

    # 1. Validate card-number characters.
    if not re.fullmatch(r"[0-9 ]+", raw_card_number):
        flash(
            "Enter a card number using digits only.",
            "error"
        )
        return redirect(url_for("payment"))

    card_number = raw_card_number.replace(" ", "")

    # 2. Require exactly 16 digits.
    if not re.fullmatch(r"\d{16}", card_number):
        flash(
            "Please enter a card number containing exactly 16 digits.",
            "error"
        )
        return redirect(url_for("payment"))

    # 3. Validate expiry format.
    if not re.fullmatch(r"(0[1-9]|1[0-2])/\d{2}", expiry):
        flash(
            "Please enter the expiry date in MM/YY format.",
            "error"
        )
        return redirect(url_for("payment"))

    month = int(expiry[:2])
    year = 2000 + int(expiry[3:])

    today = datetime.now()

    if (year, month) < (today.year, today.month):
        flash(
            "The card expiry date has passed.",
            "error"
        )
        return redirect(url_for("payment"))

    # 4. Validate the security-code format.
    if not re.fullmatch(r"\d{3,4}", cvv):
        flash(
            "Please enter a valid 3- or 4-digit security code.",
            "error"
        )
        return redirect(url_for("payment"))

    # 5. Validate the payment amount.
    try:
        amount = float(amount_text)

    except (ValueError, TypeError):
        flash(
            "Please enter a valid payment amount.",
            "error"
        )
        return redirect(url_for("payment"))

    if not math.isfinite(amount) or not 1 <= amount <= 100000:
        flash(
            "The amount must be between ₹1 and ₹100,000.",
            "error"
        )
        return redirect(url_for("payment"))

    amount = round(amount, 2)

    # 6. Process the educational transaction.
    # The full card number, expiry and security code are not stored.
    transaction_id, status, risk_score = process_payment(
        amount,
        card_number
    )

    # 7. Display the transaction result.
    return render_template(
        "payment.html",
        result={
            "transaction_id": transaction_id,
            "status": status,
            "risk_score": risk_score,
            "amount": amount,
            "card_last4": card_number[-4:]
        }
    )


# ==================================================
# TRANSACTION HISTORY
# ==================================================

@app.route("/transactions")
def transactions():

    connection = get_db()

    try:
        rows = connection.execute("""
            SELECT
                transaction_id,
                amount,
                card_last4,
                status,
                risk_score,
                created_at
            FROM transactions
            ORDER BY id DESC
        """).fetchall()

    finally:
        connection.close()

    return render_template(
        "transactions.html",
        transactions=rows
    )


# ==================================================
# ADMIN DASHBOARD
# ==================================================

@app.route("/admin")
def admin():

    connection = get_db()

    try:
        total_transactions = connection.execute(
            "SELECT COUNT(*) FROM transactions"
        ).fetchone()[0]

        approved_transactions = connection.execute("""
            SELECT COUNT(*)
            FROM transactions
            WHERE status = 'APPROVED'
        """).fetchone()[0]

        declined_transactions = connection.execute("""
            SELECT COUNT(*)
            FROM transactions
            WHERE status = 'DECLINED'
        """).fetchone()[0]

        # Total value of approved educational transactions.
        total_volume = connection.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE status = 'APPROVED'
        """).fetchone()[0]

        average_risk = connection.execute("""
            SELECT COALESCE(AVG(risk_score), 0)
            FROM transactions
        """).fetchone()[0]

        recent_transactions = connection.execute("""
            SELECT
                transaction_id,
                amount,
                card_last4,
                status,
                risk_score,
                created_at
            FROM transactions
            ORDER BY id DESC
            LIMIT 10
        """).fetchall()

        start_date = (
            datetime.now().date() - timedelta(days=6)
        ).strftime("%Y-%m-%d")

        daily_rows = connection.execute("""
            SELECT
                substr(created_at, 1, 10) AS day,
                COUNT(*) AS count
            FROM transactions
            WHERE substr(created_at, 1, 10) >= ?
            GROUP BY substr(created_at, 1, 10)
        """, (start_date,)).fetchall()

    finally:
        connection.close()

    # Calculate approval rate.
    approval_rate = (
        round(
            approved_transactions / total_transactions * 100,
            1
        )
        if total_transactions
        else 0
    )

    # Prepare daily transaction activity.
    daily_counts = {
        row["day"]: row["count"]
        for row in daily_rows
    }

    daily_activity = []

    for offset in range(6, -1, -1):
        day = datetime.now().date() - timedelta(days=offset)
        day_key = day.strftime("%Y-%m-%d")

        daily_activity.append({
            "label": day.strftime("%a"),
            "date": day.strftime("%d %b"),
            "count": daily_counts.get(day_key, 0)
        })

    # Calculate chart-bar heights.
    max_count = max(
        (day["count"] for day in daily_activity),
        default=0
    )

    for day in daily_activity:
        day["height"] = (
            max(8, day["count"] / max_count * 100)
            if max_count
            else 8
        )

    return render_template(
        "admin.html",
        total_transactions=total_transactions,
        approved_transactions=approved_transactions,
        declined_transactions=declined_transactions,
        total_volume=total_volume,
        total_amount=total_volume,
        approval_rate=approval_rate,
        average_risk=round(average_risk, 1),
        recent_transactions=recent_transactions,
        daily_activity=daily_activity
    )


# ==================================================
# START APPLICATION
# ==================================================

initialize_database()

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )