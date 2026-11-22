"""Reset the login password without touching any data.

Run from the backend folder:  python -m app.reset_password
"""
from getpass import getpass

from sqlalchemy import delete

from .config import MIN_PASSWORD_LENGTH
from .db import SessionLocal, init_db
from .models import LoginSession
from .security import hash_password, the_user


def main() -> None:
    init_db()
    db = SessionLocal()
    user = the_user(db)
    if user is None:
        print("No account yet. Start the app and create one.")
        return
    print(f"Resetting the password for '{user.username}'.")
    while True:
        pw = getpass("New password: ")
        if len(pw) < MIN_PASSWORD_LENGTH:
            print(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
            continue
        if getpass("Repeat it: ") != pw:
            print("The two entries differ. Try again.")
            continue
        break
    user.password_hash = hash_password(pw)
    db.execute(delete(LoginSession))
    db.commit()
    print("Password changed. Log in with the new password.")


if __name__ == "__main__":
    main()
