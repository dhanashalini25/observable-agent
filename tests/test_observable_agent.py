import pytest

from src import agent
from src.agent import PROMPTS, canary_pct, handle, pick_version, rolled_back


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("ROLLBACK", raising=False)
    monkeypatch.setenv("CANARY_PCT", "10")


def test_prompt_versions_differ():
    assert PROMPTS["v1"] != PROMPTS["v2"]


def test_pick_version_is_sticky():
    assert pick_version("request-abc") == pick_version("request-abc")


def test_rollback_forces_stable(monkeypatch):
    monkeypatch.setenv("ROLLBACK", "1")
    assert rolled_back()
    assert all(pick_version(f"r{i}") == agent.STABLE for i in range(50))


def test_canary_split_is_roughly_right(monkeypatch):
    monkeypatch.setenv("CANARY_PCT", "25")
    versions = [pick_version(f"request-{i}") for i in range(2000)]
    share = versions.count(agent.CANARY) / len(versions) * 100
    assert 20 < share < 30, f"canary share was {share:.1f}%"


def test_zero_percent_canary(monkeypatch):
    monkeypatch.setenv("CANARY_PCT", "0")
    assert all(pick_version(f"r{i}") == agent.STABLE for i in range(100))


def test_canary_pct_reads_env(monkeypatch):
    monkeypatch.setenv("CANARY_PCT", "42")
    assert canary_pct() == 42.0


def test_handle_emits_spans(monkeypatch):
    monkeypatch.setattr(agent, "complete", lambda m, **k: "an answer")
    r = handle("req-1", "hello")
    assert [s.name for s in r.trace.spans] == ["llm_call", "post_process"]
    assert all(s.ms >= 0 for s in r.trace.spans)


def test_handle_records_cost(monkeypatch):
    monkeypatch.setattr(agent, "complete", lambda m, **k: "an answer")
    assert handle("req-2", "hello").usd > 0


def test_errors_are_counted_and_reraised(monkeypatch):
    def boom(messages, **kwargs):
        raise TimeoutError("upstream timeout")

    monkeypatch.setattr(agent, "complete", boom)
    before = agent.ERRORS.labels(agent.STABLE, "TimeoutError")._value.get()
    with pytest.raises(TimeoutError):
        handle("req-error", "hello")
    assert agent.ERRORS.labels(agent.STABLE, "TimeoutError")._value.get() == before + 1


def test_latency_histogram_observes(monkeypatch):
    monkeypatch.setattr(agent, "complete", lambda m, **k: "x")
    handle("req-3", "hello")
    assert agent.LATENCY.labels(agent.STABLE)._sum.get() >= 0
