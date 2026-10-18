"""Deterministic checks for the durable recognition dispatch adapter."""

from contextlib import contextmanager
from uuid import UUID

from gutcare.records.image_dispatcher import (
    dispatch_batch,
    request_id_from_payload,
    retry_delay_seconds,
)

REQUEST_ID = UUID("019a0000-0000-7000-8000-000000000021")
PAYLOAD = {
    "request_id": str(REQUEST_ID),
    "recognition_type": "diet_image_recognition",
    "attempt": 1,
    "schema_version": "1.0",
}


class _Result:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _Session:
    def __init__(self, fail=False):
        self.fail = fail
        self.updates = []

    def execute(self, statement, params=None):
        sql = str(statement)
        if "WITH candidate AS" in sql:
            return _Result(
                {
                    "id": UUID("019a0000-0000-7000-8000-000000000022"),
                    "request_id": REQUEST_ID,
                    "patient_id": UUID("019a0000-0000-7000-8000-000000000023"),
                    "payload": PAYLOAD,
                    "attempts": 1,
                }
            )
        if "SET status='pending'" in sql:
            self.updates.append(("pending", params))
        elif "SET status='dead_letter'" in sql:
            self.updates.append(("dead_letter", params))
        elif "SET status='dispatched'" in sql:
            self.updates.append(("dispatched", params))
        return _Result()


class _Sessions:
    def __init__(self, session):
        self.session = session

    @contextmanager
    def begin(self):
        yield self.session


def test_dispatch_sends_minimal_envelope_with_stable_idempotency_key():
    db = _Session()
    sent = []
    count = dispatch_batch(
        _Sessions(db), lambda payload, key: sent.append((payload, key)), batch_size=1
    )
    assert count == 1
    assert sent == [(PAYLOAD, f"record-image:{REQUEST_ID}:1")]
    assert [state for state, _ in db.updates] == ["dispatched"]


def test_dispatch_failure_is_retryable_and_persists_only_fixed_code():
    db = _Session()

    def fail(_payload, _key):
        raise RuntimeError("remote error must not be persisted")

    assert dispatch_batch(_Sessions(db), fail, batch_size=1) == 0
    state, params = db.updates[0]
    assert state == "pending"
    assert params["delay"] == 5
    assert "remote error" not in repr(params)


def test_dispatch_retry_policy_and_request_scope_are_bounded():
    assert [retry_delay_seconds(n) for n in (1, 2, 3, 8, 20)] == [5, 10, 20, 640, 3600]
    assert request_id_from_payload(PAYLOAD) == REQUEST_ID
