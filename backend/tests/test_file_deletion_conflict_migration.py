import importlib.util
from pathlib import Path
from types import ModuleType


def _migration() -> ModuleType:
    path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "0030_file_deletion_conflict_check.py"
    )
    spec = importlib.util.spec_from_file_location("file_deletion_conflict_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_file_deletion_conflict_migration_grants_only_conflict_key_select(monkeypatch) -> None:
    migration = _migration()
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()
    assert statements == [
        "GRANT SELECT (file_object_id) ON integration.file_deletion_job TO gutcare_app"
    ]

    statements.clear()
    migration.downgrade()
    assert statements == [
        "REVOKE SELECT (file_object_id) ON integration.file_deletion_job FROM gutcare_app"
    ]
