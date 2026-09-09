"""Production Agent with Observability - traced, measured, canaried, revertible.

Every run emits nested spans with timings, Prometheus counters and histograms
track latency, cost and errors, traffic is split between a stable and a canary
prompt with sticky assignment, and one environment variable reverts everything.
"""
from __future__ import annotations

import hashlib
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from prometheus_client import Counter, Histogram

from .llm import complete
from .logging_setup import log

LATENCY = Histogram("agent_latency_seconds", "end to end latency", ["version"])
REQUESTS = Counter("agent_requests_total", "requests", ["version"])
ERRORS = Counter("agent_errors_total", "errors", ["version", "kind"])
COST = Counter("agent_cost_usd_total", "spend", ["version"])
SPAN_MS = Histogram("agent_span_ms", "per-span duration", ["name"])

PROMPTS = {
    "v1": "You are a helpful assistant. Be concise.",
    "v2": "You are a helpful assistant. Be concise, and state your assumptions explicitly.",
}

STABLE = os.getenv("PROMPT_VERSION_STABLE", "v1")
CANARY = os.getenv("PROMPT_VERSION_CANARY", "v2")
USD_PER_TOKEN = 0.0000006
DEMO = "Summarise what a canary deployment is."


def canary_pct() -> float:
    return float(os.getenv("CANARY_PCT", "10"))


def rolled_back() -> bool:
    return os.getenv("ROLLBACK", "0") == "1"


# ---------------------------------------------------------------- tracing
@dataclass
class Span:
    name: str
    ms: int = 0
    attrs: dict = field(default_factory=dict)


@dataclass
class Trace:
    request_id: str
    spans: list[Span] = field(default_factory=list)

    def render(self) -> str:
        return "\n".join(f"  {s.name:<14} {s.ms:>5}ms  {s.attrs}" for s in self.spans)


@contextmanager
def span(trace: Trace, name: str, **attrs):
    started = time.perf_counter()
    try:
        yield
    finally:
        ms = int((time.perf_counter() - started) * 1000)
        SPAN_MS.labels(name).observe(ms)
        trace.spans.append(Span(name=name, ms=ms, attrs=attrs))
        log.info("span", extra={"request_id": trace.request_id, "span": name, "ms": ms, **attrs})


# --------------------------------------------------------------- routing
def pick_version(request_id: str) -> str:
    """Sticky: the same request id always lands on the same version."""
    if rolled_back():
        return STABLE
    bucket = int(hashlib.sha256(request_id.encode()).hexdigest()[:8], 16) % 100
    return CANARY if bucket < canary_pct() else STABLE


@dataclass
class Response:
    text: str
    version: str
    latency_ms: int
    usd: float
    trace: Trace


def handle(request_id: str, prompt: str) -> Response:
    version = pick_version(request_id)
    trace = Trace(request_id=request_id)
    REQUESTS.labels(version).inc()
    started = time.perf_counter()

    try:
        with span(trace, "llm_call", version=version, prompt_chars=len(prompt)):
            text = complete([
                {"role": "system", "content": PROMPTS[version]},
                {"role": "user", "content": prompt},
            ])
        with span(trace, "post_process", chars=len(text)):
            text = text.strip()
    except Exception as err:  # noqa: BLE001
        ERRORS.labels(version, type(err).__name__).inc()
        log.error("request_failed", extra={"request_id": request_id, "kind": type(err).__name__})
        raise
    finally:
        LATENCY.labels(version).observe(time.perf_counter() - started)

    usd = (len(prompt) + len(text)) / 4 * USD_PER_TOKEN
    COST.labels(version).inc(usd)

    return Response(
        text=text,
        version=version,
        latency_ms=int((time.perf_counter() - started) * 1000),
        usd=usd,
        trace=trace,
    )


def run(prompt: str) -> str:
    r = handle("cli-request", prompt)
    return f"[{r.version} | {r.latency_ms}ms | ${r.usd:.6f}]\n{r.text}\n\ntrace:\n{r.trace.render()}"
