"""Deterministic checks for the durable recognition dispatch adapter."""

from contextlib import contextmanager
from uuid import UUID

from gutcare.records.image_dispatcher import (
    PermanentDispatchError,
    dispatch_batch,
    make_agent_sender,
    make_business_claimer,
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


def test_permanent_agent_rejection_moves_outbox_to_dead_letter():
    db = _Session()

    def reject(_payload, _key):
        raise PermanentDispatchError("request schema rejected")

    assert dispatch_batch(_Sessions(db), reject, batch_size=1) == 0
    state, params = db.updates[0]
    assert state == "dead_letter"
    assert "remote error" not in repr(params)


def test_agent_sender_posts_only_dispatch_envelope_and_separate_token(monkeypatch):
    from gutcare.records import image_dispatcher

    seen = {}

    class _Response:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.data)
        seen["timeout"] = timeout
        return _Response()

    import json

    monkeypatch.setattr(image_dispatcher, "urlopen", fake_urlopen)
    sender = make_agent_sender("http://agent:8100/", "opaque-token", 4)
    sender(PAYLOAD, f"record-image:{REQUEST_ID}:1")
    assert seen["url"] == "http://agent:8100/internal/v1/record-image-recognition/requests"
    assert seen["body"] == PAYLOAD
    assert seen["headers"]["Authorization"] == "Bearer opaque-token"
    assert seen["headers"]["Idempotency-key"] == f"record-image:{REQUEST_ID}:1"
    assert seen["timeout"] == 4


def test_business_claimer_uses_frozen_request_claim_api_and_service_token(monkeypatch):
    from gutcare.records import image_dispatcher

    seen = {}

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"request":{"request_id":"synthetic-only"}}'

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["method"] = request.method
        seen["headers"] = request.headers
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(image_dispatcher, "urlopen", fake_urlopen)
    claim = make_business_claimer("http://api:8000/", "service-token", 3)
    assert claim() is True
    assert seen["url"] == (
        "http://api:8000/internal/v1/agent/record-image-recognition/claim"
    )
    assert seen["method"] == "POST"
    assert seen["headers"]["Authorization"] == "Bearer service-token"
    assert seen["timeout"] == 3


def test_dispatch_retry_policy_and_request_scope_are_bounded():
    assert [retry_delay_seconds(n) for n in (1, 2, 3, 8, 20)] == [5, 10, 20, 640, 3600]
    assert request_id_from_payload(PAYLOAD) == REQUEST_ID
