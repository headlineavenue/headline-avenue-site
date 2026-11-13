from __future__ import annotations

from sqlalchemy import select

from .crypto import PREFIX, encrypt_secret
from .database import SessionLocal
from .models import PlatformConnection


def main() -> None:
    db = SessionLocal()
    try:
        rows = list(db.scalars(select(PlatformConnection)))
        changed = 0

        for connection in rows:
            access = connection.access_token
            refresh = connection.refresh_token

            if access and not access.startswith(PREFIX):
                connection.access_token = encrypt_secret(access)
                changed += 1

            if refresh and not refresh.startswith(PREFIX):
                connection.refresh_token = encrypt_secret(refresh)
                changed += 1

        if changed:
            db.commit()
        print(f"Provider token encryption check complete; encrypted {changed} legacy value(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
