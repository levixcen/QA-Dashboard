import sys
import getpass

from database import get_connection, init_db
from auth import hash_password


def main():
    if len(sys.argv) > 1:
        username = sys.argv[1]
    else:
        username = input("Username: ").strip()

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")

    if not username or not password:
        print("Username and password cannot be empty.")
        return

    if password != confirm:
        print("Passwords do not match.")
        return

    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return

    init_db()
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cur.fetchone():
        print(f"User '{username}' already exists.")
        conn.close()
        return

    cur.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, hash_password(password)),
    )
    conn.commit()
    conn.close()
    print(f"User '{username}' created.")


if __name__ == "__main__":
    main()