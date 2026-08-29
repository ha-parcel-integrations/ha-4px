"""Synthetic, non-identifying 4PX responses shared by tests."""
from __future__ import annotations

ACTIVE_CODE = "SYNTHETICACTIVE01"
DELIVERED_CODE = "SYNTHETICDONE0001"


def event(code: str, timestamp: str) -> dict:
    """Return a synthetic event with no location or user-facing prose."""
    return {"tkCode": code, "tkDate": timestamp, "tkDateStr": "2026-04-29 13:12:42", "tkTimezone": "+0000"}


def delivered_sample(code: str = DELIVERED_CODE) -> dict:
    """Delivered response, deliberately newest first as 4PX supplies it."""
    return {
        "queryCode": code,
        "serverCode": code,
        "ctStartName": "Origin region",
        "ctEndName": "Destination region",
        "status": 2,
        "tracks": [
            event("FPX_S_OK", "2026-04-29T13:12:42+00:00"),
            event("FPX_D_SD", "2026-04-29T08:46:00+00:00"),
            event("FPX_O_RR", "2026-04-28T15:52:17+00:00"),
            event("FPX_L_RPIF", "2026-04-27T23:03:58+00:00"),
        ],
    }


def active_sample(code: str = ACTIVE_CODE) -> dict:
    sample = delivered_sample(code)
    sample["tracks"] = [
        event("FPX_D_SD", "2026-04-29T08:46:00+00:00"),
        event("FPX_C_ADFF", "2026-04-28T15:52:17+00:00"),
        event("FPX_L_RPIF", "2026-04-27T23:03:58+00:00"),
    ]
    return sample


def pending_sample(code: str = "SYNTHETICPENDING") -> dict:
    return {"queryCode": code, "serverCode": None, "status": 0, "tracks": None}


def envelope(parcel: dict | None) -> dict:
    return {"result": 1, "message": "", "data": [parcel] if parcel else None, "tag": "synthetic"}
