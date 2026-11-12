"""Unit tests for Phoenix deterministic state and argument fingerprinting."""

from __future__ import annotations

from pathlib import Path

from phoenix.fingerprint import args_hash, canonical_json, state_fingerprint


def test_canonical_json_determinism():
    obj1 = {"b": 2, "a": 1, "nested": {"y": [3, 2, 1], "x": 10}}
    obj2 = {"nested": {"x": 10, "y": [3, 2, 1]}, "a": 1, "b": 2}
    assert canonical_json(obj1) == canonical_json(obj2)
    assert canonical_json(obj1) == '{"a":1,"b":2,"nested":{"x":10,"y":[3,2,1]}}'


def test_args_hash_stable():
    h1 = args_hash("write_file", {"path": "a.txt", "content": "alpha"})
    h2 = args_hash("write_file", {"content": "alpha", "path": "a.txt"})
    assert h1 == h2
    assert len(h1) == 64  # SHA-256


def test_state_fingerprint_file(tmp_path: Path):
    f1 = tmp_path / "data.txt"
    f1.write_text("initial content", encoding="utf-8")

    fp_initial = state_fingerprint([{"kind": "file", "path": str(f1)}])
    assert len(fp_initial) == 64

    # Fingerprint changes when content changes
    f1.write_text("updated content", encoding="utf-8")
    fp_updated = state_fingerprint([{"kind": "file", "path": str(f1)}])
    assert fp_updated != fp_initial

    # Fingerprint changes when missing
    f1.unlink()
    fp_missing = state_fingerprint([{"kind": "file", "path": str(f1)}])
    assert fp_missing != fp_updated


def test_state_fingerprint_db_and_http():
    fp_db = state_fingerprint([{"kind": "db_row", "table": "users", "key": "42", "data": {"name": "Alice"}}])
    fp_http = state_fingerprint([{"kind": "http", "url": "https://api.stripe.com/v1/charges", "etag": "W/123"}])
    assert len(fp_db) == 64
    assert len(fp_http) == 64
    assert fp_db != fp_http
