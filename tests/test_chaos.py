"""Unit tests for Phoenix deterministic Chaos & Crash Injection Engine."""

from __future__ import annotations

from phoenix.chaos import CrashBoundary, run_chaos_suite, run_single_trial


def test_deterministic_reproducibility():
    """Verify that given the same seed and boundary, the outcome is 100% deterministic."""
    outcome1 = run_single_trial(seed=42, crash_boundary=CrashBoundary.AFTER_EXECUTION_BEFORE_COMMIT)
    outcome2 = run_single_trial(seed=42, crash_boundary=CrashBoundary.AFTER_EXECUTION_BEFORE_COMMIT)

    assert outcome1.passed is True
    assert outcome2.passed is True
    assert outcome1.effect_count == 1
    assert outcome2.effect_count == 1
    assert outcome1.dupes_prevented == outcome2.dupes_prevented


def test_all_crash_boundaries_maintain_exactly_once():
    """Verify all 5 discrete crash injection boundaries result in exactly-once."""
    for boundary in CrashBoundary:
        outcome = run_single_trial(seed=100, crash_boundary=boundary)
        assert outcome.passed is True, f"Boundary {boundary} failed to satisfy exactly-once"
        assert outcome.effect_count == 1
        assert outcome.lost_ops == 0


def test_chaos_micro_batch():
    """Run a micro-batch of 50 seeded trials and verify 0 dupes and 0 lost ops."""
    results = run_chaos_suite(trials=50)
    assert results["trials"] == 50
    assert results["passed"] == 50
    assert results["failed"] == 0
    assert results["duplicate_writes"] == 0
    assert results["lost_operations"] == 0
