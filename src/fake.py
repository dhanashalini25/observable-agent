"""Canned reply for MODEL=fake."""
from __future__ import annotations


def respond(messages: list[dict]) -> str:
    return (
        "A canary deployment sends a small slice of traffic to the new version, "
        "compares its error rate and latency against the old one, and rolls back "
        "if the new version looks worse."
    )
