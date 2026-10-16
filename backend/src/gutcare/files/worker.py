"""Long-running scheduler for F02 retention and orphan cleanup jobs."""

import logging
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gutcare.config import get_settings
from gutcare.files.scanner import ClamAvScanner
from gutcare.files.service import FileService
from gutcare.files.storage import S3ObjectStorage

logger = logging.getLogger("gutcare.files.worker")


def main() -> None:
    settings = get_settings()
    required = (
        settings.worker_database_url,
        settings.object_storage_endpoint,
        settings.object_storage_access_key,
        settings.object_storage_secret_key,
        settings.clamav_host,
        settings.files_capability_secret,
    )
    if any(value is None for value in required):
        raise RuntimeError(
            "Worker database, private object storage and scanner settings are required"
        )
    assert settings.worker_database_url is not None
    assert settings.object_storage_endpoint is not None
    assert settings.object_storage_access_key is not None
    assert settings.object_storage_secret_key is not None
    assert settings.clamav_host is not None
    assert settings.files_capability_secret is not None
    database_url = str(settings.worker_database_url)
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(database_url, pool_pre_ping=True)
    worker_sessions = sessionmaker(engine, expire_on_commit=False)
    service = FileService(
        worker_sessions,
        S3ObjectStorage(
            str(settings.object_storage_endpoint),
            settings.object_storage_access_key,
            settings.object_storage_secret_key,
        ),
        ClamAvScanner(
            settings.clamav_host,
            settings.clamav_port,
            settings.clamav_timeout_seconds,
        ),
        str(settings.public_base_url),
        settings.object_storage_bucket,
        settings.files_capability_secret,
        worker_sessions=worker_sessions,
    )
    try:
        while True:
            try:
                service.reap_expired_upload_sessions()
                service.process_due_deletion_jobs()
            except Exception:
                logger.exception("F02 cleanup cycle failed")
            time.sleep(15)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
