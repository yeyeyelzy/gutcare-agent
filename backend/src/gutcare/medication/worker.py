"""Recoverable finite-window F06 checkin materializer CLI."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gutcare.medication.service import materialize


def main() -> None:
    url = os.environ.get("MEDICATION_WORKER_DATABASE_URL")
    if not url:
        raise SystemExit("MEDICATION_WORKER_DATABASE_URL is required")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url, pool_pre_ping=True)
    try:
        materialize(sessionmaker(engine, expire_on_commit=False))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
