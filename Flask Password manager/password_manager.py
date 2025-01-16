import sqlite3
import os
import smtplib
import random
import string
import csv
import unicodedata
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# pip install python-dotenv
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = os.getenv("EMAIL_PORT")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


# ------------------ DATABASE SETUP ------------------
def create_connection():
    """
    Create a database connection to the SQLite database
    """
    conn = None
    try:
        conn = sqlite3.connect("password_manager.db")
        # Enforce foreign key constraints
        conn.execute("PRAGMA foreign_keys = 1;")
        return conn
    except sqlite3.Error as e:
        print(f"Error creating DB connection: {e}")
    return conn

def create_tables():
    """
    Create the necessary tables in the SQLite database if not present
    """
    conn = create_connection()
    cursor = conn.cursor()

    # Create users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    );
    """)

    # Create suppliers table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS suppliers (
        supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_name TEXT NOT NULL,
        office_id TEXT,
        user_id TEXT,     -- Not to be confused with users.user_id, we'll just store it as text or int
        password TEXT NOT NULL,
        url TEXT,
        date_created TEXT DEFAULT CURRENT_TIMESTAMP,
        last_reset TEXT,
        owner_user_id INTEGER NOT NULL,
        FOREIGN KEY (owner_user_id) REFERENCES users(user_id)
    );
    """)

    conn.commit()
    conn.close()


# ------------------ OTP & EMAIL ------------------
def generate_otp(length=6):
    """Generate a numeric OTP code of given length."""
    digits = string.digits
    return ''.join(random.choice(digits) for _ in range(length))

def send_otp_via_email(to_email, otp_code):
    """
    Sends the OTP code via Email. Uses environment variables for email config.
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = to_email
        msg['Subject'] = "Your OTP Code"

        body = f"Your OTP code is: {otp_code}\nIt will expire soon. Please use it promptly."
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(EMAIL_HOST, int(EMAIL_PORT)) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, to_email, msg.as_string())

        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


# ------------------ USER AUTHENTICATION ------------------
def register():
    """
    Handle user registration.
    - Username must be unique
    - Email must be unique
    - Password stored as plain text here for simplicity (use hashing in production)
    """
    conn = create_connection()
    cursor = conn.cursor()

    print("\n--- Registration ---")
    while True:
        username = input("Enter a unique username: ").strip()
        email = input("Enter your email: ").strip()
        password = input("Enter your password: ").strip()

        # Check uniqueness
        cursor.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username, email))
        row = cursor.fetchone()

        if row:
            print("Error: That username or email is already registered. Please try again.")
        else:
            # Insert new user
            cursor.execute("""
                INSERT INTO users (username, email, password) 
                VALUES (?, ?, ?)
            """, (username, email, password))
            conn.commit()
            print("Registration successful!\n")
            break

    conn.close()


def sign_in():
    """
    Handle user sign in.
    - If the user types the wrong password twice, prompt for reset or try again or exit.
    """
    conn = create_connection()
    cursor = conn.cursor()

    print("\n--- Sign In ---")
    username = input("Username: ").strip()

    # Check if user exists
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user_data = cursor.fetchone()

    if not user_data:
        print("No such user found. Please register first.")
        conn.close()
        return None

    # user_data layout: (user_id, username, email, password)
    user_id, db_username, db_email, db_password = user_data

    attempts = 0
    while True:
        password = input("Password: ").strip()
        if password == db_password:
            print("Sign in successful!")
            conn.close()
            return user_data
        else:
            attempts += 1
            print("Incorrect password.")
            if attempts == 2:
                print("\nYou have entered the wrong password twice.")
                print("Options:")
                print("1. Reset password")
                print("2. Try again")
                print("3. Exit")
                opt = input("Enter choice: ").strip()
                if opt == '1':
                    # Reset password flow
                    # 1) Send OTP to user email
                    print("Sending OTP to your registered email address...")
                    otp_code = generate_otp()
                    if send_otp_via_email(db_email, otp_code):
                        # 2) Ask user to enter OTP
                        user_otp = input("Enter the OTP sent to your email: ").strip()
                        if user_otp == otp_code:
                            new_pass = input("Enter your new password: ").strip()
                            cursor.execute("UPDATE users SET password = ? WHERE user_id = ?", (new_pass, user_id))
                            conn.commit()
                            print("Password has been reset. Please sign in again.")
                        else:
                            print("OTP mismatch. Returning to Welcome Screen.")
                    conn.close()
                    return None
                elif opt == '2':
                    # reset attempts and keep going
                    attempts = 0
                else:
                    # Exit
                    conn.close()
                    return None


# ------------------ SUPPLIER MANAGEMENT ------------------
def parse_datetime(dt_string):
    try:
        return datetime.strptime(dt_string, "%Y-%m-%d %H:%M:%S.%f")  # with microseconds
    except ValueError:
        return datetime.strptime(dt_string, "%Y-%m-%d %H:%M:%S")    # without microseconds
    
def view_supplier_details(current_user):
    """
    1) Show all suppliers for this user.
    2) If none, show message.
    3) If there are suppliers, allow user to type the supplier name or serial no. to view details
    4) Mask password, and at the bottom ask if they want to unmask -> triggers OTP flow
    """
    conn = create_connection()
    cursor = conn.cursor()

    user_id, username, email, _ = current_user

    cursor.execute("""
        SELECT supplier_id, supplier_name, office_id, user_id, password, url, last_reset
        FROM suppliers
        WHERE owner_user_id = ?
    """, (user_id,))
    suppliers = cursor.fetchall()

    if not suppliers:
        print("\nNo suppliers added yet.\n")
        conn.close()
        return

    print("\n--- Your Suppliers ---")
    print("S.No | Supplier Name")
    print("--------------------")
    for i, sup in enumerate(suppliers, start=1):
        sup_id, sup_name, office_id, sup_user_id, pw, url, last_reset = sup
        print(f"{i}. {sup_name}")

    user_input = input("\nEnter S.No or Supplier Name to view details: ").strip()

    # Identify the supplier based on user_input
    selected_supplier = None

    # If user_input is a digit, interpret as index
    if user_input.isdigit():
        index = int(user_input) - 1
        if 0 <= index < len(suppliers):
            selected_supplier = suppliers[index]
    else:
        # match by supplier name
        for sup in suppliers:
            if sup[1].lower() == user_input.lower():
                selected_supplier = sup
                break

    if not selected_supplier:
        print("Supplier not found.")
        conn.close()
        return

    sup_id, sup_name, office_id, sup_user_id, pw, url, last_reset = selected_supplier

    print(f"\nSupplier: {sup_name}")
    if office_id:
        print(f"Office ID: {office_id}")
    else:
        print("Office ID not Required")
    print(f"User ID: {sup_user_id}")
    print(f"Password: {'*' * len(pw)}")
    print(f"Site URL: {url}")
    print(f"Last Reset: {last_reset}")

    # 30 day expiry - record is last_reset. If null, treat as never set
    # For display of next reset reminder
    if last_reset:
        last_reset_dt = parse_datetime(last_reset)
        next_reset_dt = last_reset_dt + timedelta(days=30)
        reminder_dt = next_reset_dt - timedelta(days=7)
        print(f"Password Reset Reminder: {reminder_dt}")
    else:
        print("Password Reset Reminder: Not set")

    print("\n[1] Toggle Password Masking (10 min)")
    print("[2] Return")

    choice = input("Enter your choice: ").strip()
    if choice == "1":
        # OTP flow to unmask password
        print("Sending OTP to your registered email address...")
        otp_code = generate_otp()
        if send_otp_via_email(email, otp_code):
            user_otp = input("Enter the OTP sent to your email: ").strip()
            if user_otp == otp_code:
                print(f"Unmasked Password: {pw}")
            else:
                print("OTP mismatch. Returning to menu.")
        else:
            print("Failed to send OTP. Returning to menu.")

    conn.close()


def modify_supplier_details(current_user):
    """
    2) modify supplier details or delete supplier.
    - Both operations require an OTP for confirmation.
    """
    conn = create_connection()
    cursor = conn.cursor()

    user_id, username, email, _ = current_user

    # Show all suppliers
    cursor.execute("""
        SELECT supplier_id, supplier_name 
        FROM suppliers
        WHERE owner_user_id = ?
    """, (user_id,))
    suppliers = cursor.fetchall()

    if not suppliers:
        print("\nNo suppliers added yet.\n")
        conn.close()
        return

    print("\n--- Your Suppliers ---")
    print("S.No | Supplier Name")
    print("--------------------")
    for i, sup in enumerate(suppliers, start=1):
        sup_id, sup_name = sup
        print(f"{i}. {sup_name}")

    user_input = input("\nEnter S.No or Supplier Name to modify/delete: ").strip()

    selected_supplier = None
    if user_input.isdigit():
        index = int(user_input) - 1
        if 0 <= index < len(suppliers):
            selected_supplier = suppliers[index]
    else:
        for sup in suppliers:
            if sup[1].lower() == user_input.lower():
                selected_supplier = sup
                break

    if not selected_supplier:
        print("Supplier not found.")
        conn.close()
        return

    sup_id, sup_name = selected_supplier
    print(f"\nSelected: {sup_name}")

    print("\nOptions:")
    print("1. Modify Supplier")
    print("2. Delete Supplier")
    choice = input("Enter choice: ").strip()

    if choice == '1':
        # Modify - ask which field to modify
        print("Which field do you want to modify?")
        print("1. Supplier Name")
        print("2. Office ID")
        print("3. User ID")
        print("4. Password")
        print("5. URL")
        field_choice = input("Enter choice: ").strip()

        # OTP required
        print("Sending OTP to your registered email address...")
        otp_code = generate_otp()
        if send_otp_via_email(email, otp_code):
            user_otp = input("Enter the OTP sent to your email: ").strip()
            if user_otp == otp_code:
                new_val = input("Enter new value: ").strip()
                field_map = {
                    '1': 'supplier_name',
                    '2': 'office_id',
                    '3': 'user_id',
                    '4': 'password',
                    '5': 'url'
                }
                if field_choice in field_map:
                    field_name = field_map[field_choice]
                    # If password is changed, also reset the last_reset field
                    if field_choice == '4':
                        # Update password
                        cursor.execute(f"UPDATE suppliers SET {field_name} = ?, last_reset = ? WHERE supplier_id = ?",
                                       (new_val, datetime.now(), sup_id))
                    else:
                        cursor.execute(f"UPDATE suppliers SET {field_name} = ? WHERE supplier_id = ?",
                                       (new_val, sup_id))
                    conn.commit()
                    print(f"{field_map[field_choice]} updated successfully.")
                else:
                    print("Invalid choice.")
            else:
                print("OTP mismatch. No changes made.")
        else:
            print("Failed to send OTP. No changes made.")

    elif choice == '2':
        # Delete
        print("Sending OTP to your registered email address...")
        otp_code = generate_otp()
        if send_otp_via_email(email, otp_code):
            user_otp = input("Enter the OTP sent to your email: ").strip()
            if user_otp == otp_code:
                cursor.execute("DELETE FROM suppliers WHERE supplier_id = ?", (sup_id,))
                conn.commit()
                print("Supplier deleted successfully.")
            else:
                print("OTP mismatch. Supplier not deleted.")
        else:
            print("Failed to send OTP. Supplier not deleted.")

    conn.close()


def remove_invisible_chars(s: str) -> str:
    """
    Remove (or normalize away) invisible Unicode characters such as \u202A
    """
    # Approach 1: Filter out non-printable characters
    filtered = "".join(ch for ch in s if ch.isprintable())
    
    # Approach 2 (optional): Remove any left-to-right override or similar
    # filtered = filtered.replace('\u202A', '').replace('\u202B', '')
    
    # Optionally normalize the path
    filtered = unicodedata.normalize('NFKC', filtered)
    return filtered

def add_new_suppliers(current_user):
    """
    3) Add new suppliers
       user can choose to add via 1) csv/excel or 2) manually
    """
    conn = create_connection()
    cursor = conn.cursor()
    user_id, username, email, _ = current_user

    print("\n--- Add New Suppliers ---")
    print("1. Using CSV file")
    print("2. Manually")
    choice = input("Enter choice: ").strip()

    if choice == '1':
        # CSV import
        csv_path = input("Enter the full path of the CSV file: ").strip()
        
        # Clean path from hidden/unwanted Unicode characters
        csv_path = remove_invisible_chars(csv_path)

        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    supplier_name = row.get("Supplier Name", "").strip()
                    office_id = row.get("Office ID", "").strip()
                    supplier_user_id = row.get("User ID", "").strip()
                    password = row.get("Password", "").strip()
                    url = row.get("URL", "").strip()

                    if not supplier_name or not password:
                        # Minimal check - must have at least name & password
                        continue

                    cursor.execute("""
                        INSERT INTO suppliers
                          (supplier_name, office_id, user_id, password, url, last_reset, owner_user_id) 
                        VALUES (?, ?, ?, ?, ?, DATETIME('now'), ?)
                    """, (supplier_name, office_id, supplier_user_id, password, url, user_id))
                conn.commit()
            print("Suppliers imported successfully from CSV.")
        except Exception as e:
            print(f"Error importing from CSV: {e}")

    elif choice == '2':
        # Manual add
        while True:
            supplier_name = input("Supplier Name: ").strip()
            office_id = input("Office ID (optional): ").strip()
            supplier_user_id = input("User ID: ").strip()
            password = input("Password: ").strip()
            url = input("URL: ").strip()

            if not supplier_name or not password:
                print("Supplier name and password are required. Please try again.")
                continue

            cursor.execute("""
                INSERT INTO suppliers
                  (supplier_name, office_id, user_id, password, url, last_reset, owner_user_id)
                VALUES (?, ?, ?, ?, ?, DATETIME('now'), ?)
            """, (supplier_name, office_id, supplier_user_id, password, url, user_id))
            conn.commit()
            print("Supplier added successfully!")

            add_more = input("Add another supplier? (y/n): ").strip().lower()
            if add_more != 'y':
                break

    conn.close()


def view_password_reset_reminders(current_user):
    """
    4) Display suppliers whose password is due to expire in 7 days or less.
       Every password expires in 30 days.
       The password expiry date = last_reset + 30 days
       We show reminder if current_date >= (expiry_date - 7 days)
    """
    conn = create_connection()
    cursor = conn.cursor()
    user_id, username, email, _ = current_user

    cursor.execute("""
        SELECT supplier_name, last_reset
        FROM suppliers
        WHERE owner_user_id = ?
    """, (user_id,))
    suppliers = cursor.fetchall()

    if not suppliers:
        print("\nNo suppliers found.\n")
        conn.close()
        return

    reminders = []
    for sup in suppliers:
        sup_name, last_reset = sup
        if last_reset:
            try:
                last_reset_dt = parse_datetime(last_reset)
            except ValueError:
                # If there's a parsing error or unexpected format, skip
                continue
            expiry_dt = last_reset_dt + timedelta(days=30)
            reminder_dt = expiry_dt - timedelta(days=7)
            now = datetime.now()
            if now >= reminder_dt and now < expiry_dt:
                # We are within the 7 day window
                reminders.append((sup_name, expiry_dt.strftime("%Y-%m-%d %H:%M:%S")))

    if reminders:
        print("\nSuppliers requiring password reset soon:")
        for item in reminders:
            sup_name, exp_time = item
            print(f"Supplier: {sup_name}, Expiry Date: {exp_time}")
    else:
        print("\nNo supplier passwords are due for reset in the next 7 days.\n")

    conn.close()


def main_menu(current_user):
    """
    After successful login, present the user with the main menu options:
    1) View supplier details
    2) Modify supplier details
    3) Add new suppliers
    4) View supplier password reset reminder alert
    5) Exit (back to welcome screen)
    """
    while True:
        print("\n--- Main Menu ---")
        print("1. View Supplier Details")
        print("2. Modify Supplier Details")
        print("3. Add New Suppliers")
        print("4. View Supplier Password Reset Reminders")
        print("5. Exit")
        choice = input("Enter your choice: ").strip()

        if choice == '1':
            view_supplier_details(current_user)
        elif choice == '2':
            modify_supplier_details(current_user)
        elif choice == '3':
            add_new_suppliers(current_user)
        elif choice == '4':
            view_password_reset_reminders(current_user)
        elif choice == '5':
            print("Returning to Welcome Screen...")
            break
        else:
            print("Invalid choice. Please try again.")


def welcome_screen():
    """
    Display the welcome screen and prompt user to sign in, register or exit.
    """
    while True:
        print("\nWelcome to the Password Manager developed by Usama Thakur")
        print("1. Sign In")
        print("2. Register")
        print("3. Exit")
        choice = input("Enter your choice: ").strip()

        if choice == '1':
            user_data = sign_in()
            if user_data:
                main_menu(user_data)
        elif choice == '2':
            register()
        elif choice == '3':
            print("Exiting the program. Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    create_tables()
    welcome_screen()
