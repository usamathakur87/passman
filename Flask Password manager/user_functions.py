from db_utils import create_connection
from otp_utils import generate_otp, send_otp_via_email

def register_user(username, email, password):
    conn = create_connection()
    if not conn:
        return False, "Database connection error."

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username, email))
    row = cursor.fetchone()
    if row:
        conn.close()
        return False, "Username or email is already registered."

    cursor.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)", (username, email, password))
    conn.commit()
    conn.close()
    return True, "Registration successful!"

def sign_in_user(username, password):
    conn = create_connection()
    if not conn:
        return None, "Database connection error."

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user_data = cursor.fetchone()
    conn.close()

    if not user_data:
        return None, "No such user found. Please register first."

    user_id, db_username, db_email, db_password = user_data
    if password == db_password:
        return user_data, None
    else:
        return None, "Incorrect username or password."
