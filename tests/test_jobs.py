from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "jobs"))

from common import json_metrics  # noqa: E402
from dispatch_notifications import payload_for  # noqa: E402


def test_notification_payload_carries_idempotency():
    row = {
        "notification_id": 42,
        "idempotency_key": "42:TEAMS",
        "numero_bl": "BL-42",
        "type_notif": "EDI_NOK_OK",
        "message": "Le BL est passé à OK.",
        "cree_le": "2026-07-25T12:00:00Z",
        "cree_par": "admin@example.com",
        "type_canal": "POWER_AUTOMATE",
    }
    payload = payload_for(row)
    assert payload["idempotency_key"] == "42:TEAMS"
    assert payload["numero_bl"] == "BL-42"


def test_metrics_are_valid_json():
    assert json_metrics(sent=2, failed=0) == '{"sent": 2, "failed": 0}'
