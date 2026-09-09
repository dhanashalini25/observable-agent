# 11 - Production Agent with Observability

> Traced, measured, canaried and revertible.

**What it demonstrates:** Operating an agent in production rather than running it locally

**Status:** working implementation with passing tests. Built as a learning project to understand the pattern, not as a production service.

---

## Run it right now

No API key needed - every project ships with `MODEL=fake`, a deterministic
offline responder, so you can see the whole flow work before spending anything.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
python -m src.main
pytest -q
```

To use a real model, edit `.env`:

```
MODEL=gpt-4o-mini            # + OPENAI_API_KEY
MODEL=claude-3-5-haiku-latest  # + ANTHROPIC_API_KEY
MODEL=ollama/llama3.1        # free, runs locally
```

Run the service:

```bash
uvicorn src.server:app --reload
# http://127.0.0.1:8000/ask?q=hello
# http://127.0.0.1:8000/metrics
```

## How it works

Every run builds a trace of nested spans with durations, and each span is also emitted as a structured log line carrying the request id - so one request can be followed end to end.

Prometheus metrics cover the four things worth alerting on: latency histogram, request count, error count by exception type, and cumulative cost. `/metrics` exposes them and `/alerts.yml` serves ready-to-use alert rules for error rate, p95 latency regression and cost spike.

Traffic is split between a stable and a canary prompt by hashing the request id, so the same request always lands on the same version - a sticky split, not a coin flip. `ROLLBACK=1` sends everything back to stable without a deploy.

## What "done" means here

- Every run emits spans with per-step durations and a shared request id
- Latency, request count, errors by type and cost are all exported
- Alert rules exist for error rate, p95 latency and cost spike
- Traffic splits between two prompt versions with sticky assignment
- The canary share matches the configured percentage (tested over 2000 ids)
- `ROLLBACK=1` reverts everything to stable with no deploy

Every one of those lines has a test behind it in `tests/` - `pytest -q` is the
proof, not the README.

## Layout

```
src/llm.py             provider-agnostic completion, plus offline fake mode
src/fake.py            the canned responses that make MODEL=fake work
src/logging_setup.py   structured JSON logging
src/agent.py           the pattern itself
src/main.py            CLI entrypoint
src/server.py          FastAPI service, /metrics and /alerts.yml
tests/                 10 tests, all passing
```

## Next steps

- Replace the span context manager with real OpenTelemetry spans
- Point it at LangSmith or Arize and screenshot a real trace here
- Deploy it and record actual p50/p95 under load
- Pull real token counts from the provider response instead of estimating cost

## Reference

https://www.freecodecamp.org/news/how-to-trace-and-monitor-ai-agents-with-langsmith/

---

Part of a 12-project agentic AI series - [github.com/dhanashalini25](https://github.com/dhanashalini25?tab=repositories)
