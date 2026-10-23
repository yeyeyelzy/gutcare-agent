import importlib.util
from pathlib import Path
from types import ModuleType


def _migration() -> ModuleType:
    path = Path(__file__).parents[1] / "migrations" / "versions" / "0029_f02_worker_updated_at.py"
    spec = importlib.util.spec_from_file_location("f02_claim_updated_at_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_f02_claim_updated_at_migration_grants_and_revokes_only_timestamp(monkeypatch) -> None:
    migration = _migration()
    statements: list[str] = []
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()
    assert statements == [
        "GRANT UPDATE (updated_at) ON health.medical_document TO gutcare_analysis_worker"
    ]

    statements.clear()
    migration.downgrade()
    assert statements == [
        "REVOKE UPDATE (updated_at) ON health.medical_document FROM gutcare_analysis_worker"
    ]
