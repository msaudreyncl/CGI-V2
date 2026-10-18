"""
reset_admin.py — Fix or reset the default admin account password.

Run this from the project root with your venv active:
    python database/reset_admin.py

This script connects directly to MySQL and upserts the admin user
with a freshly generated bcrypt hash — bypassing any seed.sql issues.
"""

import sys
import os

# Add backend to path so we can reuse config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

try:
    import bcrypt
    import pymysql
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run:  pip install bcrypt pymysql python-dotenv")
    sys.exit(1)

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

DB_HOST     = os.getenv('DB_HOST',     'localhost')
DB_PORT     = int(os.getenv('DB_PORT', '3306'))
DB_NAME     = os.getenv('DB_NAME',     'cgi_db')
DB_USER     = os.getenv('DB_USER',     'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')

ADMIN_EMAIL    = 'admin@cgi.local'
ADMIN_NAME     = 'System Admin'
ADMIN_PASSWORD = 'Admin@1234'
ADMIN_ID       = 1

def main():
    print(f"Connecting to MySQL at {DB_HOST}:{DB_PORT}/{DB_NAME}...")
    try:
        conn = pymysql.connect(
            host=DB_HOST, port=DB_PORT, db=DB_NAME,
            user=DB_USER, password=DB_PASSWORD, charset='utf8mb4'
        )
    except pymysql.err.OperationalError as e:
        print(f"\nERROR: Cannot connect to MySQL.\n{e}")
        print("\nCheck that:\n  1. XAMPP MySQL is running\n  2. DB_HOST/DB_PORT/DB_USER/DB_PASSWORD in .env are correct")
        sys.exit(1)

    # Generate fresh hash
    password_hash = bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt(rounds=12)).decode()
    print(f"Generated hash for '{ADMIN_PASSWORD}'")

    with conn.cursor() as cur:
        # The original System Admin is identified only by its immutable primary key.
        cur.execute("SELECT id FROM users WHERE id = %s", (ADMIN_ID,))
        row = cur.fetchone()

        if row:
            cur.execute(
                """UPDATE users
                   SET name = %s, email = %s, password_hash = %s, role = 'admin', is_active = 1
                   WHERE id = %s""",
                (ADMIN_NAME, ADMIN_EMAIL, password_hash, ADMIN_ID)
            )
            print(f"Updated existing admin user (id={row[0]})")
        else:
            cur.execute(
                """INSERT INTO users (id, name, email, password_hash, role, is_active)
                   VALUES (%s, %s, %s, %s, 'admin', 1)""",
                (ADMIN_ID, ADMIN_NAME, ADMIN_EMAIL, password_hash)
            )
            print(f"Created new admin user")

    conn.commit()
    conn.close()

    print(f"\nDone. Login credentials:")
    print(f"  Email   : {ADMIN_EMAIL}")
    print(f"  Password: {ADMIN_PASSWORD}")

if __name__ == '__main__':
    main()
