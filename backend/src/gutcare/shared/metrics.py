"""Low-cardinality Prometheus metrics for the business API process."""

import re
from collections.abc import Iterable

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class OperationsMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry(auto_describe=True)
        self._route_templates: frozenset[str] = frozenset()
        self.http_requests = Counter(
            "gutcare_http_requests_total",
            "Completed HTTP requests by route template and status family.",
            ("method", "route", "status_family"),
            registry=self.registry,
        )
        self.http_duration = Histogram(
            "gutcare_http_request_duration_seconds",
            "HTTP request duration by route template.",
            ("method", "route", "status_family"),
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
            registry=self.registry,
        )
        self.readiness = Counter(
            "gutcare_readiness_probes_total",
            "Readiness probe outcomes.",
            ("result",),
            registry=self.registry,
        )
        self.readiness_component = Gauge(
            "gutcare_readiness_component",
            "Readiness component state (1 ready, 0 unavailable).",
            ("component",),
            registry=self.registry,
        )
        self.db_backlog = Gauge(
            "gutcare_worker_backlog",
            "Aggregated durable work by bounded queue and state.",
            ("queue", "state"),
            registry=self.registry,
        )
        self.db_backlog_age = Gauge(
            "gutcare_worker_oldest_backlog_age_seconds",
            "Age of oldest eligible work in bounded durable queues.",
            ("queue",),
            registry=self.registry,
        )
        self.db_snapshot_success = Gauge(
            "gutcare_metrics_db_snapshot_success",
            "Whether the last aggregate database metrics snapshot succeeded.",
            registry=self.registry,
        )
        self.db_snapshot_failures = Counter(
            "gutcare_metrics_db_snapshot_failures_total",
            "Aggregate metrics snapshot database failures.",
            registry=self.registry,
        )

    def set_route_templates(self, routes: Iterable[str]) -> None:
        self._route_templates = frozenset(
            route
            for route in routes
            if isinstance(route, str)
            and len(route) <= 200
            and re.fullmatch(r"/[A-Za-z0-9_./{}-]+", route)
        )

    @staticmethod
    def _label(value: str, allowed: frozenset[str], fallback: str) -> str:
        return value if value in allowed else fallback

    def observe_request(
        self, method: str, route: str, status_code: int, duration_seconds: float
    ) -> None:
        method_label = self._label(
            method.upper(),
            frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}),
            "OTHER",
        )
        route_label = (
            route
            if isinstance(route, str)
            and len(route) <= 200
            and re.fullmatch(r"/[A-Za-z0-9_./{}-]+", route)
            and route in self._route_templates
            else "unmatched"
        )
        status_family = f"{status_code // 100}xx" if 100 <= status_code <= 599 else "other"
        labels = (method_label, route_label, status_family)
        self.http_requests.labels(*labels).inc()
        self.http_duration.labels(*labels).observe(max(0.0, duration_seconds))

    def observe_readiness(
        self, result: str, *, database: bool, schema: bool, privacy_replay: bool
    ) -> None:
        self.readiness.labels(result="ready" if result == "ready" else "not_ready").inc()
        for name, value in (
            ("database", database),
            ("schema", schema),
            ("privacy_replay", privacy_replay),
        ):
            self.readiness_component.labels(component=name).set(1 if value else 0)

    def update_backlog(self, rows: Iterable[tuple[str, str, int, float]]) -> None:
        allowed_queues = frozenset(
            {
                "notification_outbox",
                "file_deletion",
                "file_orphan_cleanup",
                "privacy_deletion",
                "privacy_inventory",
                "export_cleanup",
            }
        )
        allowed_states = frozenset({"backlog", "dead_letter"})
        for queue in allowed_queues:
            for state in allowed_states:
                self.db_backlog.labels(queue=queue, state=state).set(0)
            self.db_backlog_age.labels(queue=queue).set(0)
        for queue, state, count, age_seconds in rows:
            if queue not in allowed_queues or state not in allowed_states:
                continue
            self.db_backlog.labels(queue=queue, state=state).set(max(0, count))
            if state == "backlog":
                self.db_backlog_age.labels(queue=queue).set(max(0.0, age_seconds))
        self.db_snapshot_success.set(1)

    def mark_snapshot_failed(self) -> None:
        for queue in (
            "notification_outbox",
            "file_deletion",
            "file_orphan_cleanup",
            "privacy_deletion",
            "privacy_inventory",
            "export_cleanup",
        ):
            for state in ("backlog", "dead_letter"):
                self.db_backlog.labels(queue=queue, state=state).set(float("nan"))
            self.db_backlog_age.labels(queue=queue).set(float("nan"))
        self.db_snapshot_failures.inc()
        self.db_snapshot_success.set(0)
