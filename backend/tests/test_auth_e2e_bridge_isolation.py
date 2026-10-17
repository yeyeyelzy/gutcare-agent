"""Negative probe: the test-only bridge must ignore any cwd .env file."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from pytest import MonkeyPatch


def test_bridge_app_ignores_sentinel_dotenv_in_temporary_cwd(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    sentinel = "auth-e2e-dotenv-must-not-load"
    (tmp_path / ".env").write_text(f"APP_SERVICE_NAME={sentinel}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GUTCARE_AUTH_E2E_BRIDGE", "1")
    for name in (
        "APP_SERVICE_NAME",
        "APP__SERVICE_NAME",
        "APP_ENV",
        "APP__ENV",
        "DATABASE_URL",
        "MIGRATOR_DATABASE_URL",
        "REDIS_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    bridge_path = Path(__file__).with_name("auth_e2e_http_bridge.py")
    spec = importlib.util.spec_from_file_location("auth_e2e_bridge_isolation_probe", bridge_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.app.state.settings.service_name == "gutcare-business-api"
    assert module.app.state.settings.database_url is None
