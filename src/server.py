"""Service with metrics and an alert-rule endpoint.

    uvicorn src.server:app --reload
    # http://127.0.0.1:8000/ask?q=hello
    # http://127.0.0.1:8000/metrics
"""
from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .agent import CANARY, STABLE, canary_pct, handle, rolled_back

app = FastAPI(title="Observable Agent")

ALERTS = """groups:
  - name: agent
    rules:
      - alert: HighErrorRate
        expr: rate(agent_errors_total[5m]) / rate(agent_requests_total[5m]) > 0.05
        for: 5m
      - alert: LatencyP95Regression
        expr: histogram_quantile(0.95, rate(agent_latency_seconds_bucket[10m])) > 5
        for: 10m
      - alert: CostSpike
        expr: increase(agent_cost_usd_total[1h]) > 5
        for: 15m
"""


@app.get("/ask")
def ask(q: str, request_id: str | None = None):
    r = handle(request_id or uuid.uuid4().hex[:12], q)
    return {
        "answer": r.text,
        "version": r.version,
        "latency_ms": r.latency_ms,
        "usd": round(r.usd, 6),
        "spans": [{"name": s.name, "ms": s.ms} for s in r.trace.spans],
    }


@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/alerts.yml", response_class=PlainTextResponse)
def alerts():
    return ALERTS


@app.get("/config")
def config():
    return {
        "stable": STABLE,
        "canary": CANARY,
        "canary_pct": canary_pct(),
        "rolled_back": rolled_back(),
    }
