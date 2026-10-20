"""Provision the isolated demo bucket and its least-privilege API identity."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time


def run_mc(config_path: str, *arguments: str, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["mc", "--config-dir", config_path, *arguments],
        check=False,
        capture_output=True,
        input=input_bytes,
    )
    return result


endpoint = os.environ["MINIO_ENDPOINT"]
root_user = os.environ["MINIO_ROOT_USER"]
root_password = os.environ["MINIO_ROOT_PASSWORD"]
app_access_key = os.environ["MINIO_APP_ACCESS_KEY"]
app_secret_key = os.environ["MINIO_APP_SECRET_KEY"]
bucket = os.environ["MINIO_BUCKET"]
policy_path = os.environ["MINIO_POLICY_PATH"]

def require_success(result: subprocess.CompletedProcess[bytes]) -> None:
    if result.returncode:
        # Never surface subprocess output: it may contain credential material.
        raise RuntimeError("Phone-demo MinIO provisioning failed")


with tempfile.TemporaryDirectory(prefix="gutcare-minio-root-") as root_config, tempfile.TemporaryDirectory(
    prefix="gutcare-minio-app-"
) as app_config:
    for attempt in range(30):
        result = run_mc(root_config, "alias", "set", "local", endpoint, root_user, root_password)
        if result.returncode == 0:
            break
        if attempt == 29:
            require_success(result)
        time.sleep(2)

    require_success(run_mc(root_config, "mb", "--ignore-existing", f"local/{bucket}"))
    require_success(run_mc(root_config, "admin", "policy", "create", "local", "gutcare-phone-demo-app", policy_path))
    # `user add` is also the supported MinIO password rotation operation, so
    # startup remains idempotent for the persistent demo volume.
    require_success(run_mc(root_config, "admin", "user", "add", "local", app_access_key, app_secret_key))
    require_success(
        run_mc(
            root_config,
            "admin",
            "policy",
            "attach",
            "local",
            "gutcare-phone-demo-app",
            "--user",
            app_access_key,
        )
    )
    require_success(run_mc(app_config, "alias", "set", "app", endpoint, app_access_key, app_secret_key))

    probe_key = ".gutcare-phone-demo-permission-check"
    require_success(
        run_mc(app_config, "pipe", f"app/{bucket}/{probe_key}", input_bytes=b"access-check")
    )
    if run_mc(app_config, "cat", f"app/{bucket}/{probe_key}").stdout != b"access-check":
        raise RuntimeError("Phone-demo MinIO application identity cannot read its bucket object")
    require_success(run_mc(app_config, "rm", f"app/{bucket}/{probe_key}"))

    # Verify both bucket scoping and MinIO admin isolation with a disposable
    # sentinel bucket that is created and removed under the root identity.
    denied_bucket = "gutcare-phone-demo-denied-check"
    require_success(run_mc(root_config, "mb", "--ignore-existing", f"local/{denied_bucket}"))
    try:
        visible_buckets = run_mc(app_config, "ls", "app")
        if denied_bucket.encode() in visible_buckets.stdout:
            raise RuntimeError("Phone-demo MinIO application identity can enumerate another bucket")
        if run_mc(app_config, "ls", f"app/{denied_bucket}").returncode == 0:
            raise RuntimeError("Phone-demo MinIO application identity can access another bucket")
        if run_mc(app_config, "admin", "info", "app").returncode == 0:
            raise RuntimeError("Phone-demo MinIO application identity has admin access")
    finally:
        require_success(run_mc(root_config, "rb", f"local/{denied_bucket}"))
