from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
import os
import csv
import pandas as pd
from db_utils import create_connection, create_tables
from user_functions import register_user, sign_in_user
from supplier_functions import (
    get_user_suppliers,
    add_supplier,
    allowed_file,
    modify_supplier,
    delete_supplier,
    view_password_reset_reminders,
)
from otp_utils import generate_otp, send_otp_via_email

app = Flask(__name__)

# Configuration for file uploads
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

ALLOWED_EXTENSIONS = {'csv', 'xls', 'xlsx'}
app.secret_key = os.urandom(24)

# Ensure database tables are created
create_tables()

@app.route("/")
def home():
    if "logged_in" in session and session["logged_in"]:
        return redirect(url_for("dashboard"))
    return render_template("home.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        success, msg = register_user(username, email, password)
        flash(msg, "success" if success else "danger")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user_data, error_message = sign_in_user(username, password)
        if user_data:
            session["logged_in"] = True
            session["user"] = {"id": user_data[0], "username": user_data[1], "email": user_data[2]}
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))
        flash(error_message, "danger")
    return render_template("login.html")

@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        email = request.form["email"]
        conn = create_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for("reset_password"))

        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        if user:
            otp = generate_otp()
            if send_otp_via_email(email, otp):
                session["reset_email"] = email
                session["reset_otp"] = otp
                flash("OTP sent. Please verify.", "info")
                return redirect(url_for("verify_otp"))
            flash("Failed to send OTP.", "danger")
        else:
            flash("No user found with this email.", "danger")
    return render_template("reset_password.html")

@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    if request.method == "POST":
        otp = request.form["otp"]
        if otp == session.get("reset_otp"):
            return redirect(url_for("set_new_password"))
        flash("Invalid OTP. Try again.", "danger")
    return render_template("verify_otp.html")

@app.route("/set_new_password", methods=["GET", "POST"])
def set_new_password():
    if request.method == "POST":
        new_password = request.form["new_password"]
        email = session.get("reset_email")
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password = ? WHERE email = ?", (new_password, email))
        conn.commit()
        conn.close()
        session.pop("reset_email", None)
        session.pop("reset_otp", None)
        flash("Password reset successful!", "success")
        return redirect(url_for("login"))
    return render_template("set_new_password.html")

@app.route("/password_reset_reminders", methods=["GET"])
def password_reset_reminders():
    if "logged_in" not in session or not session["logged_in"]:
        return redirect(url_for("login"))

    user_id = session["user"]["id"]
    reminders = view_password_reset_reminders(user_id)

    return render_template("password_reset_reminders.html", reminders=reminders)

@app.route("/dashboard")
def dashboard():
    if "logged_in" not in session or not session["logged_in"]:
        return redirect(url_for("login"))

    user = session["user"]

    # Define menu options dynamically
    menu_options = [
        {"name": "View Suppliers", "url": url_for("view_suppliers")},
        {"name": "Modify Suppliers", "url": url_for("modify_suppliers")},
        {"name": "Add Suppliers", "url": url_for("add_suppliers")},
        {"name": "Password Reset Reminders", "url": url_for("password_reset_reminders")},
    ]

    return render_template("dashboard.html", user=user, menu_options=menu_options)

@app.route("/add_suppliers", methods=["GET", "POST"])
def add_suppliers():
    if "logged_in" not in session or not session["logged_in"]:
        return redirect(url_for("login"))

    user_id = session["user"]["id"]

    if request.method == "POST":
        if 'add_manually' in request.form:
            # Add manually
            supplier_name = request.form.get("supplier_name", "").strip()
            office_id = request.form.get("office_id", "").strip()
            user_id_val = request.form.get("user_id", "").strip()
            password = request.form.get("password", "").strip()
            url = request.form.get("url", "").strip()

            # Check required fields
            if not supplier_name or not password:
                flash("Supplier name and password are required.", "danger")
                return redirect(url_for("add_suppliers"))

            # Call the add_supplier function
            success, msg = add_supplier(user_id, supplier_name, office_id, user_id_val, password, url)
            flash(msg, "success" if success else "danger")

        elif 'file' in request.files:
            # Handle CSV or Excel upload
            file = request.files['file']
            if file.filename == '':
                flash('No selected file.', 'danger')
                return redirect(url_for("add_suppliers"))

            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                # Check file type
                if filename.endswith('.csv'):
                    process_csv(filepath, user_id)
                elif filename.endswith('.xls') or filename.endswith('.xlsx'):
                    process_excel(filepath, user_id)

    return render_template("add_suppliers.html")


@app.route("/view_suppliers")
def view_suppliers():
    if "logged_in" not in session or not session["logged_in"]:
        return redirect(url_for("login"))

    user_id = session["user"]["id"]
    suppliers = get_user_suppliers(user_id)
    return render_template("view_suppliers.html", suppliers=suppliers)

@app.route("/modify_suppliers", methods=["GET", "POST"])
def modify_suppliers():
    if "logged_in" not in session or not session["logged_in"]:
        return redirect(url_for("login"))

    user_id = session["user"]["id"]
    suppliers = get_user_suppliers(user_id)

    if request.method == "POST":
        otp = request.form.get("otp")
        if otp != session.get("otp"):
            flash("Invalid OTP.", "danger")
            return redirect(url_for("modify_suppliers"))

        if "delete_supplier_id" in request.form:
            supplier_id = request.form["delete_supplier_id"]
            success, msg = delete_supplier(user_id, [supplier_id])
            flash(msg, "success" if success else "danger")
        elif "delete_selected" in request.form:
            supplier_ids = request.form.getlist("supplier_ids")
            success, msg = delete_supplier(user_id, supplier_ids)
            flash(msg, "success" if success else "danger")
        elif "supplier_id" in request.form:
            supplier_id = request.form["supplier_id"]
            field = request.form["field"]
            new_value = request.form["new_value"]
            success, msg = modify_supplier(user_id, supplier_id, field, new_value)
            flash(msg, "success" if success else "danger")
    return render_template("modify_suppliers.html", suppliers=suppliers)

@app.route("/fetch_password/<int:supplier_id>", methods=["POST"])
def fetch_password(supplier_id):
    if "logged_in" not in session or not session["logged_in"]:
        return jsonify({"error": "Unauthorized access"}), 403

    user_id = session["user"]["id"]
    otp = request.json.get("otp")

    print(f"Supplier ID: {supplier_id}, User ID: {user_id}, OTP: {otp}")  # Debug print

    # Validate OTP
    if otp != session.get("reset_otp"):  # Ensure OTP matches
        print("Invalid OTP")  # Debug print
        return jsonify({"error": "Invalid OTP"}), 401

    conn = create_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT password FROM suppliers WHERE supplier_id = ? AND owner_user_id = ?",
        (supplier_id, user_id)
    )
    result = cursor.fetchone()
    conn.close()

    if result:
        print(f"Password fetched: {result[0]}")  # Debug print
        return jsonify({"password": result[0]})
    else:
        print("Supplier not found or unauthorized access")  # Debug print
        return jsonify({"error": "Supplier not found or unauthorized access"}), 404

@app.route("/set_debug_otp")
def set_debug_otp():
    session["reset_otp"] = "123456"  # Replace with a test OTP
    return "Debug OTP set to 123456"


@app.route("/logout")
def logout():
    session.clear()  # Clear the session data
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)
