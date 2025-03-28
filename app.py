from flask import Flask, make_response, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify, Response, send_file
from datetime import datetime
import sqlite3
import csv
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import json

# Initialize Flask application
app = Flask(__name__)

# ------------------------------- Database Initialization -------------------------------
def init_db():
    """
    Initializes the SQLite database and creates tables if they do not already exist.
    Tables:
    - transactions: Stores income and expenses with details.
    - budgets: Stores budget limits for specific categories.
    - savings_goals: Tracks savings goals with target amounts and progress.
    """
    conn = sqlite3.connect('finances.db')
    c = conn.cursor()

    # Creating Transactions table
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL, -- Income or Expense
            category TEXT NOT NULL, -- Category for transaction
            amount REAL NOT NULL, -- Amount of transaction
            date TEXT NOT NULL, -- Date of transaction
            description TEXT -- Optional description
        )
    ''')

    # Creating Budget table
    c.execute('''
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL, -- Category name
            budget_limit REAL NOT NULL -- Limit set for that category
        )
    ''')

    # Creating Savings Goals table
    c.execute('''
        CREATE TABLE IF NOT EXISTS savings_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_name TEXT NOT NULL, -- Name of the savings goal
            target_amount REAL NOT NULL, -- Goal amount
            current_savings REAL NOT NULL, -- Current saved amount
            due_date TEXT -- Optional due date for goal
        )
    ''')

    conn.commit()
    conn.close()

# ------------------------------- Routes -------------------------------

@app.after_request
def add_cors_headers(response):
    """
    Adds CORS headers to allow cross-origin requests.
    Allows frontend applications to interact with this backend.
    """
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.route('/api/budgets')
def get_budgets():
    """
    API endpoint to fetch budget details.
    Calculates the total spent in each category and returns the remaining budget.
    """
    conn = sqlite3.connect('finances.db')
    c = conn.cursor()

    # Retrieve all budgets
    c.execute("SELECT * FROM budgets")
    budgets_data = c.fetchall()

    budgets = []
    for budget in budgets_data:
        category = budget[1]
        limit = budget[2]

        # Calculate total spent in each category
        c.execute("SELECT SUM(amount) FROM transactions WHERE type='expense' AND category=?", (category,))
        spent = c.fetchone()[0] or 0  # Handle NULL values
        remaining = limit - spent  # Calculate remaining budget

        budgets.append({
            'category': category,
            'limit': limit,
            'spent': spent,
            'remaining': remaining
        })

    conn.close()
    return jsonify(budgets)

@app.route('/')
def index():
    """
    Main dashboard displaying all transactions, total income, expenses, and balance.
    """
    conn = sqlite3.connect('finances.db')
    c = conn.cursor()

    # Fetch all transactions
    c.execute("SELECT * FROM transactions")
    transactions = c.fetchall()

    # Calculate total income
    c.execute("SELECT SUM(amount) FROM transactions WHERE type='income'")
    total_income = c.fetchone()[0] or 0

    # Calculate total expenses
    c.execute("SELECT SUM(amount) FROM transactions WHERE type='expense'")
    total_expense = c.fetchone()[0] or 0

    # Calculate current balance
    current_balance = total_income - total_expense

    conn.close()

    # Sample budget categories for frontend display
    budgets = {
        'food': 500,
        'salary': 0,  # No limit for income
        'gifts': 200,
        'rent': 1000,
    }
    return render_template('index.html', transactions=transactions, balance=current_balance, income=total_income, expense=total_expense, budgets_json=json.dumps(budgets))

@app.route('/add', methods=['GET', 'POST'])
def add_transaction():
    """
    Handles adding a new transaction.
    If the request is AJAX, return JSON response; otherwise, redirect to index.
    """
    if request.method == 'POST':
        # Retrieve form data
        transaction_type = request.form['type']
        category = request.form['category']
        amount = float(request.form['amount'])
        date = request.form['date']
        description = request.form['description']

        # Insert the new transaction into the database
        conn = sqlite3.connect('finances.db')
        c = conn.cursor()
        c.execute('''INSERT INTO transactions (type, category, amount, date, description) 
                     VALUES (?, ?, ?, ?, ?)''', 
                  (transaction_type, category, amount, date, description))
        conn.commit()
        conn.close()

        # Return JSON response if AJAX request, otherwise redirect
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(success=True)
        else:
            return redirect(url_for('index'))

    return render_template('add.html')

@app.route('/delete/<int:transaction_id>', methods=['DELETE'])
def delete_transaction(transaction_id):
    """
    Deletes a transaction by its ID.
    Returns a JSON response indicating success or failure.
    """
    conn = sqlite3.connect('finances.db')
    c = conn.cursor()
    c.execute("DELETE FROM transactions WHERE id=?", (transaction_id,))
    conn.commit()

    if c.rowcount > 0:  # Check if deletion was successful
        conn.close()
        return jsonify({'success': True})
    else:
        conn.close()
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404

@app.route('/export/csv')
def export_csv():
    """
    Exports all transactions as a CSV file.
    Uses a generator to stream the CSV data for efficient handling.
    """
    conn = sqlite3.connect('finances.db')
    c = conn.cursor()
    c.execute("SELECT * FROM transactions")
    transactions = c.fetchall()
    conn.close()

    csv_data = [['ID', 'Type', 'Category', 'Amount', 'Date', 'Description']]  # CSV header
    csv_data += [[t[0], t[1], t[2], t[3], t[4], t[5]] for t in transactions]

    def generate():
        for row in csv_data:
            yield ','.join(map(str, row)) + '\n'

    return Response(generate(), mimetype='text/csv', headers={
        'Content-Disposition': 'attachment;filename=transactions.csv'
    })

# ------------------------------- User Authentication -------------------------------
# Setup secret key and database URI
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database and login manager
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# User model
class User(UserMixin, db.Model):
    """
    User model for authentication.
    Fields:
    - id: Unique user ID.
    - username: Unique username.
    - password: Hashed password.
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

# Create database tables
with app.app_context():
    db.create_all()

# ------------------------------- Run Application -------------------------------
if __name__ == '__main__':
    init_db()  # Ensure database is initialized
    app.run(debug=True)  # Start Flask application
