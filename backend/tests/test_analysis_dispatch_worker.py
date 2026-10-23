from gutcare.analysis.worker import DispatchWorker


def test_dispatch_claim_sends_minimal_envelope_with_split_tokens() -> None:
    worker = DispatchWorker("http://business", "http://agent", "business-token", "agent-token")
    calls: list[tuple[str, str, dict | None, str | None]] = []
    responses = iter(
        [
            (
                200,
                {
                    "task": {
                        "task_id": "019a0000-0000-7000-8000-000000000801",
                        "analysis_type": "comprehensive_health_analysis",
                        "attempt": 2,
                    }
                },
            ),
            (202, {"accepted": True}),
        ]
    )

    def fake_request(
        url: str, token: str, payload: dict | None = None, idempotency_key: str | None = None
    ) -> tuple[int, dict]:
        calls.append((url, token, payload, idempotency_key))
        return next(responses)

    worker._request = fake_request  # type: ignore[method-assign]
    assert worker.dispatch_one()
    assert calls == [
        ("http://business/internal/v1/agent/analysis-tasks/claim", "business-token", {}, None),
        (
            "http://agent/internal/v1/tasks",
            "agent-token",
            {
                "task_id": "019a0000-0000-7000-8000-000000000801",
                "analysis_type": "comprehensive_health_analysis",
                "schema_version": "1.0",
                "deadline_at": None,
            },
            "f08:019a0000-0000-7000-8000-000000000801:2",
        ),
    ]


def test_dispatch_empty_claim_does_not_contact_agent() -> None:
    worker = DispatchWorker("http://business", "http://agent", "business-token", "agent-token")
    urls: list[str] = []

    def fake_request(
        url: str, token: str, payload: dict | None = None, idempotency_key: str | None = None
    ) -> tuple[int, dict]:
        urls.append(url)
        return 200, {"task": None}

    worker._request = fake_request  # type: ignore[method-assign]
    assert not worker.dispatch_one()
    assert urls == ["http://business/internal/v1/agent/analysis-tasks/claim"]
