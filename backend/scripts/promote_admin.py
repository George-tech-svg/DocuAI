"""Promote an existing account to platform administrator once, by email."""
import argparse
import sys
from pathlib import Path
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.session import get_engine
from app.models.user import User

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("email", help="Email address of the existing account to promote")
args = parser.parse_args()

with sessionmaker(bind=get_engine())() as db:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('documind_one_time_admin_bootstrap'))"))
    user = db.scalar(select(User).where(User.email == args.email.strip().lower()))
    if user is None:
        raise SystemExit("No account exists with that email. Create the account first, then run this command again.")
    existing_admin = db.scalar(select(User).where(User.is_superuser.is_(True)).limit(1))
    if existing_admin is not None:
        if existing_admin.id == user.id:
            raise SystemExit(f"{user.email} is already the registered super administrator.")
        raise SystemExit(f"A super administrator is already registered ({existing_admin.email}); promotion is disabled.")
    user.is_superuser = True
    db.commit()
    print(f"Administrator access enabled for {user.email}.")
