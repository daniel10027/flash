"""Métriques Prometheus (BE-T4).

Un ``CollectorRegistry`` **dédié par application** (``create_app`` peut être appelé
plusieurs fois dans les tests) : compteur de requêtes, histogramme de latence, jauge de
requêtes en cours. Exposé en texte Prometheus sur ``GET /metrics`` (hors OpenAPI, comme
``/health``).

Le libellé ``endpoint`` est le **gabarit** de route (``/v1/merchant/charges/<id>``) et
non le chemin concret, pour borner la cardinalité.
"""

from __future__ import annotations

import time

from flask import Flask, Response, g, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

_LATENCY_BUCKETS = (
    0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0,
)


class _AppMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests_total = Counter(
            "flash_http_requests_total",
            "Nombre de requêtes HTTP traitées.",
            ("method", "endpoint", "status"),
            registry=self.registry,
        )
        self.request_duration = Histogram(
            "flash_http_request_duration_seconds",
            "Latence des requêtes HTTP (secondes).",
            ("method", "endpoint"),
            buckets=_LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.in_progress = Gauge(
            "flash_http_requests_in_progress",
            "Requêtes HTTP en cours de traitement.",
            ("method", "endpoint"),
            registry=self.registry,
        )


def _endpoint() -> str:
    rule = request.url_rule
    return rule.rule if rule is not None else "<unmatched>"


def register_metrics(app: Flask) -> None:
    metrics = _AppMetrics()
    app.extensions["flash_metrics"] = metrics

    @app.before_request
    def _metrics_start() -> None:
        if request.path == "/metrics":
            return
        g._metrics_start = time.perf_counter()
        g._metrics_endpoint = _endpoint()
        metrics.in_progress.labels(request.method, g._metrics_endpoint).inc()

    @app.after_request
    def _metrics_stop(response: Response) -> Response:
        start = g.pop("_metrics_start", None)
        if start is None:
            return response
        endpoint = g.pop("_metrics_endpoint", _endpoint())
        elapsed = time.perf_counter() - start
        metrics.in_progress.labels(request.method, endpoint).dec()
        metrics.request_duration.labels(request.method, endpoint).observe(elapsed)
        metrics.requests_total.labels(
            request.method, endpoint, str(response.status_code)
        ).inc()
        return response

    @app.get("/metrics")
    def _metrics_endpoint_view() -> Response:
        return Response(generate_latest(metrics.registry), mimetype=CONTENT_TYPE_LATEST)


__all__ = ["register_metrics"]
