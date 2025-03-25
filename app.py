from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify, Response, send_file
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
    conn = sqlite3.connect('finances.db')
    c = conn.cursor()

    # Transactions table: Logs income and expenses with details.
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            description TEXT
        )
    ''')

    # Budget table: Stores budget limits for specific categories.
    c.execute('''
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            budget_limit REAL NOT NULL
        )
    ''')

    # Savings Goals table: tracks savings goals with target amounts and progress.
    c.execute('''
        CREATE TABLE IF NOT EXISTS savings_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_name TEXT NOT NULL,
            target_amount REAL NOT NULL,
            current_savings REAL NOT NULL,
            due_date TEXT
        )
    ''')

    conn.commit()
    conn.close()

# ------------------------------- Routes -------------------------------
@app.route('/')
def index():
    conn = sqlite3.connect('finances.db')
    c = conn.cursor()
    # Fetch all transactions
    c.execute("SELECT * FROM transactions")
    transactions = c.fetchall()

    # Calculate total income and expenses
    c.execute("SELECT SUM(amount) FROM transactions WHERE type='income'")
    total_income = c.fetchone()[0] or 0
    c.execute("SELECT SUM(amount) FROM transactions WHERE type='expense'")
    total_expense = c.fetchone()[0] or 0
    current_balance = total_income - total_expense

    conn.close()

    budgets = {
        'food': 500,
        'salary': 0,  # No limit for income
        'gifts': 200,
        'rent': 1000,
    }
    return render_template('index.html', transactions=transactions, balance=current_balance, income=total_income, expense=total_expense, budgets_json=json.dumps(budgets))
    #return render_template('index.html', transactions=transactions, balance=current_balance, income=total_income, expense=total_expense)



@app.route('/add', methods=['GET', 'POST'])
def add_transaction():
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
        return redirect(url_for('index'))

    return render_template('add.html')

@app.route('/edit_transaction', methods=['POST'])
def edit_transaction():
    # Get form data
    """
    Route for editing an existing transaction.
    Accepts updated transaction data via POST request.
    """
    transaction_id = request.form['transaction_id']
    transaction_type = request.form['type']
    category = request.form['category']
    amount = request.form['amount']
    date = request.form['date']
    description = request.form['description']

    # Connect to the database and update the transaction
    conn = sqlite3.connect('finances.db')
    c = conn.cursor()

    # Update the transaction in the database
    c.execute('''UPDATE transactions
                 SET type = ?, category = ?, amount = ?, date = ?, description = ?
                 WHERE id = ?''', 
              (transaction_type, category, amount, date, description, transaction_id))
    
    conn.commit()

    # Check if the update was successful
    if c.rowcount > 0:
        conn.close()
        return jsonify({'success': True})
    else:
        conn.close()
        return jsonify({'success': False, 'message': 'Transaction not found'})

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

    if c.rowcount > 0: # Success check
        conn.close()
        return jsonify({'success': True})
    else:
        conn.close()
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404

@app.route('/transaction/<int:transaction_id>')
def get_transaction_details(transaction_id):
    conn = sqlite3.connect('finances.db')
    c = conn.cursor()
    c.execute("SELECT * FROM transactions WHERE id=?", (transaction_id,))
    transaction = c.fetchone()
    conn.close()

    if transaction:
        return jsonify({
            'id': transaction[0],
            'type': transaction[1],
            'category': transaction[2],
            'amount': transaction[3],
            'date': transaction[4],
            'description': transaction[5]
        })
    else:
        return jsonify({'error': 'Transaction not found'}), 404

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


@app.route('/export/pdf')
def export_pdf():
    conn = sqlite3.connect('finances.db')
    c = conn.cursor()
    c.execute("SELECT * FROM transactions")
    transactions = c.fetchall()
    conn.close()

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(100, 750, "Transactions Report")
    c.drawString(50, 730, "ID    Type    Category    Amount    Date    Description")

    y = 710
    for t in transactions:
        c.drawString(50, y, f"{t[0]}  {t[1]}  {t[2]}  ${t[3]}  {t[4]}  {t[5]}")
        y -= 20
        if y < 50:  # New page if content exceeds
            c.showPage()
            y = 750

    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="transactions.pdf", mimetype='application/pdf')

@app.route('/budgeting', methods=['GET', 'POST'])
def budgeting():
    if request.method == 'POST':
        # Handle adding a new budget category
        if 'category' in request.form and 'budget_limit' in request.form:
            category = request.form['category']
            budget_limit = float(request.form['budget_limit'])

            conn = sqlite3.connect('finances.db')
            c = conn.cursor()
            c.execute('''INSERT INTO budgets (category, budget_limit) VALUES (?, ?)''', 
                      (category, budget_limit))
            conn.commit()
            conn.close()
        
        # Handle adding a new savings goal
        if 'goal_name' in request.form and 'target_amount' in request.form and 'current_savings' in request.form:
            goal_name = request.form['goal_name']
            target_amount = float(request.form['target_amount'])
            current_savings = float(request.form['current_savings'])
            due_date = request.form['due_date']

            conn = sqlite3.connect('finances.db')
            c = conn.cursor()
            c.execute('''INSERT INTO savings_goals (goal_name, target_amount, current_savings, due_date)
                         VALUES (?, ?, ?, ?)''', 
                      (goal_name, target_amount, current_savings, due_date))
            conn.commit()
            conn.close()

        return redirect(url_for('budgeting'))

    # Retrieve current budgets and savings goals
    conn = sqlite3.connect('finances.db')
    c = conn.cursor()

    # Get budgets
    c.execute("SELECT * FROM budgets")
    budgets = c.fetchall()

    # Get savings goals
    c.execute("SELECT * FROM savings_goals")
    goals = c.fetchall()

    conn.close()

    return render_template('budgeting.html', budgets=budgets, goals=goals)



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
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

# Create database tables
with app.app_context():
    db.create_all()

# Route for Home Page (Login Required)
@app.route('/loginLanding')
@login_required
def home():
    # You can add other logic related to budgeting, savings, etc.
    return render_template('loginLanding.html')

# Route for Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Login unsuccessful. Please check your username and password', 'danger')
    return render_template('login.html')

# Route for Signup
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)  # Using the default pbkdf2_sha256

        if User.query.filter_by(username=username).first():
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('signup'))

        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        flash('Signup successful! You can now login.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')


# Route for Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/signupLanding')
def signup_landing():
    return render_template('signupLanding.html')

@app.route('/loginLanding')
def login_landing():
    return render_template('loginLanding.html')


"""@app.route('/login')
def login():
    return render_template('login.html')"""

"""
@app.route('/signup')
def signup():
    return render_template('signup.html')"""

@app.route('/contact')
def contact_page():
    return render_template('contact.html')

@app.route('/home')
def home_page():
    return render_template('home.html')


# Load user function for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))



if __name__ == "__main__":
    init_db()
    app.run(debug=True)
