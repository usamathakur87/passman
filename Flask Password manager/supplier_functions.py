import sqlite3
from datetime import datetime, timedelta
import csv
import unicodedata

# Database Connection
def create_connection():
    try:
        conn = sqlite3.connect("password_manager.db")
        conn.execute("PRAGMA foreign_keys = 1;")
        return conn
    except sqlite3.Error as e:
        print(f"Error creating DB connection: {e}")
        return None


# Helper Functions
def parse_datetime(dt_string):
    try:
        return datetime.strptime(dt_string, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        return datetime.strptime(dt_string, "%Y-%m-%d %H:%M:%S")


def remove_invisible_chars(s):
    return "".join(ch for ch in s if ch.isprintable())

ALLOWED_EXTENSIONS = {'csv', 'xls', 'xlsx'}

# Supplier Management Functions
def get_user_suppliers(user_id):
    conn = create_connection()
    if not conn:
        return []

    cursor = conn.cursor()
    cursor.execute("""
        SELECT supplier_id, supplier_name, office_id, user_id, password, url, date_created, last_reset
        FROM suppliers
        WHERE owner_user_id = ?
        ORDER BY date_created DESC
    """, (user_id,))
    suppliers = cursor.fetchall()
    conn.close()

    return [{"id": row[0], "supplier_name": row[1], "office_id": row[2], "user_id": row[3], "password": row[4],
             "url": row[5], "date_created": row[6], "last_reset": row[7]} for row in suppliers]

def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def add_supplier(owner_user_id, supplier_name, office_id, user_id, password, url):
    if not supplier_name or not password:
        return False, "Supplier name and password are required."

    try:
        conn = create_connection()
        cursor = conn.cursor()

        # Insert the supplier into the database
        cursor.execute("""
            INSERT INTO suppliers (supplier_name, office_id, user_id, password, url, owner_user_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (supplier_name, office_id, user_id, password, url, owner_user_id))

        conn.commit()
        conn.close()
        return True, "Supplier added successfully."
    except sqlite3.IntegrityError as e:
        return False, f"Database error: {str(e)}"
    except Exception as e:
        return False, f"An unexpected error occurred: {str(e)}"


def modify_supplier(supplier_id, field_name, new_value):
    """
    Modify a specific field of a supplier.
    """
    conn = create_connection()
    try:
        cursor = conn.cursor()
        query = f"UPDATE suppliers SET {field_name} = ? WHERE supplier_id = ?"
        cursor.execute(query, (new_value, supplier_id))
        conn.commit()
        return True, "Supplier updated successfully."
    except Exception as e:
        return False, f"Error updating supplier: {e}"
    finally:
        conn.close()

# In supplier_functions.py
def delete_supplier(user_id, supplier_ids):
    """
    Deletes suppliers for the given user and supplier IDs.

    Args:
        user_id (int): The ID of the user who owns the suppliers.
        supplier_ids (list): List of supplier IDs to delete.

    Returns:
        tuple: (success, message)
    """
    conn = create_connection()
    if not conn:
        return False, "Database connection error."

    try:
        cursor = conn.cursor()
        # Ensure supplier IDs belong to the logged-in user
        cursor.executemany(
            "DELETE FROM suppliers WHERE supplier_id = ? AND owner_user_id = ?",
            [(supplier_id, user_id) for supplier_id in supplier_ids],
        )
        conn.commit()
        return True, f"{len(supplier_ids)} supplier(s) deleted successfully."
    except sqlite3.Error as e:
        return False, f"Error deleting supplier(s): {str(e)}"
    finally:
        conn.close()


def view_password_reset_reminders(user_id):
    """
    Show suppliers with passwords expiring within the next 7 days.
    """
    conn = create_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT supplier_name, last_reset
            FROM suppliers WHERE owner_user_id = ?
            """,
            (user_id,),
        )
        suppliers = cursor.fetchall()

        reminders = []
        now = datetime.now()
        for sup_name, last_reset in suppliers:
            if last_reset:
                try:
                    last_reset_dt = parse_datetime(last_reset)
                    expiry_dt = last_reset_dt + timedelta(days=30)
                    reminder_dt = expiry_dt - timedelta(days=7)
                    if now >= reminder_dt and now < expiry_dt:
                        reminders.append((sup_name, expiry_dt.strftime("%Y-%m-%d %H:%M:%S")))
                except ValueError:
                    continue

        return reminders
    except Exception as e:
        print(f"Error fetching password reset reminders: {e}")
        return []
    finally:
        conn.close()


def import_suppliers_from_csv(user_id, csv_path):
    """
    Import suppliers from a CSV file for the user.
    """
    conn = create_connection()
    try:
        cursor = conn.cursor()
        csv_path = remove_invisible_chars(csv_path)

        with open(csv_path, "r", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                supplier_name = row.get("Supplier Name", "").strip()
                office_id = row.get("Office ID", "").strip()
                user_id_val = row.get("User ID", "").strip()
                password = row.get("Password", "").strip()
                url = row.get("URL", "").strip()

                if not supplier_name or not password:
                    continue

                cursor.execute(
                    """
                    INSERT INTO suppliers
                    (supplier_name, office_id, user_id, password, url, last_reset, owner_user_id)
                    VALUES (?, ?, ?, ?, ?, DATETIME('now'), ?)
                    """,
                    (supplier_name, office_id, user_id_val, password, url, user_id),
                )
        conn.commit()
        return True, "Suppliers imported successfully from CSV."
    except Exception as e:
        return False, f"Error importing suppliers from CSV: {e}"
    finally:
        conn.close()
