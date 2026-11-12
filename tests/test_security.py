"""Unit and adversarial security tests for Phoenix."""

from __future__ import annotations

from pathlib import Path

import pytest
from phoenix.idempotency import ExactlyOnce
from phoenix.ledger import Ledger
from phoenix.models import SideEffect
from phoenix.security import SecurityError, confine_storage_path, redact_secrets


def test_model_cannot_choose_ledger_path(tmp_path: Path):
    """Adversarial check: model cannot escape storage via directory traversal."""
    with pytest.raises(SecurityError):
        Ledger(tmp_path / ".." / ".." / "etc" / "phoenix.db", base_dir=tmp_path)

    with pytest.raises(SecurityError):
        confine_storage_path("../../root_secret.txt", tmp_path)


def test_secret_redaction():
    """Verify recursive secret redaction across nested objects and keys."""
    raw_payload = {
        "user": "alice",
        "api_key": "test_mock_api_key_value",
        "auth_token": "bearer xyz1234567890abcdef123456",
        "nested": {
            "password": "super_secret_password",
            "token": "tok_12345",
            "safe_val": 42,
        },
        "list_items": [
            "normal_string",
            {"secret": "hidden_value"},
            "bearer token_string_to_redact_1234567890",
        ],
    }

    sanitized = redact_secrets(raw_payload)
    assert sanitized["user"] == "alice"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["auth_token"] == "[REDACTED]"
    assert sanitized["nested"]["password"] == "[REDACTED]"
    assert sanitized["nested"]["token"] == "[REDACTED]"
    assert sanitized["nested"]["safe_val"] == 42
    assert sanitized["list_items"][1]["secret"] == "[REDACTED]"
    assert "[REDACTED]" in sanitized["list_items"][2]


def test_no_cross_session_read_cache(tmp_path: Path):
    """Verify that read-only tools are NEVER cached or replayed across sessions."""
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        eo = ExactlyOnce(led, enabled=True)

        rec = led.begin(
            session_id="session_A",
            turn_id=None,
            tool_name="read_file",
            args={"path": "confidential.txt"},
            side_effect_class=SideEffect.READ,
            idempotency_key="key_read_1",
            pre_fingerprint=None,
        )
        led.commit(rec.id, post_fingerprint="fp_read", result={"data": "confidential"}, duration_ms=2)

        # Session B attempts to read with same key: MUST EXECUTE, never return stored!
        decision = eo.decide(
            tool_name="read_file",
            args={"path": "confidential.txt"},
            session_id="session_B",
            pre_fp=None,
            opt_in=True,
            side_effect_class=SideEffect.READ,
            idempotency_key="key_read_1",
        )
        assert decision.action == "execute"
        assert decision.stored is None
    finally:
        led.close()


def test_prompt_injection_cannot_replay_foreign_result(tmp_path: Path):
    """Adversarial check: spoofed foreign session key without opt-in is refused."""
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        eo = ExactlyOnce(led, enabled=True)

        # Opt-in is False by default: must execute, never replay
        decision = eo.decide(
            tool_name="charge_card",
            args={"amount": 500},
            session_id="attacker_session",
            pre_fp=None,
            opt_in=False,
            idempotency_key="foreign_key",
        )
        assert decision.action == "execute"
        assert decision.stored is None
    finally:
        led.close()
