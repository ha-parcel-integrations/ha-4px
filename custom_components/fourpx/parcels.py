"""Pure 4PX parcel mapping helpers."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_DELIVERED_FILTER_AMOUNT,
    CONF_DELIVERED_FILTER_TYPE,
    DEFAULT_DELIVERED_FILTER_AMOUNT,
    DEFAULT_DELIVERED_FILTER_TYPE,
    HISTORY_MAX_EVENTS,
    TRACKING_URL,
    ParcelStatus,
)

_LOGGER = logging.getLogger(__name__)
NEW_ISSUE_URL = "https://github.com/ha-parcel-integrations/ha-4px/issues/new?template=unrecognised_status.yml"
_STATUS_MAP: dict[str, ParcelStatus] = {
    "FPX_L_RPIF": ParcelStatus.REGISTERED,
    "FPX_C_SPLS": ParcelStatus.IN_TRANSIT,
    "FPX_C_AAF": ParcelStatus.IN_TRANSIT,
    "FPX_C_ADFF": ParcelStatus.IN_TRANSIT,
    "FPX_O_RR": ParcelStatus.IN_TRANSIT,
    "FPX_D_SD": ParcelStatus.OUT_FOR_DELIVERY,
    "FPX_S_OK": ParcelStatus.DELIVERED,
}
_warned: set[str] = set()
_timestamp_shapes: set[tuple[str, str, str]] = set()
_KNOWN_TIMESTAMP_SHAPES = {
    ("str", "str", "str"),
    ("str", "str", "NoneType"),
}


def _warn_once(key: str, message: str, *args: Any) -> None:
    if key not in _warned:
        _warned.add(key)
        _LOGGER.warning(message, *args)


def _warn_unmapped(code: str | None) -> None:
    label = code or "<missing>"
    _warn_once(
        f"status:{label}",
        "Unrecognised 4PX status shape — open an issue and paste this line: %s; tkCode=%s",
        NEW_ISSUE_URL,
        label,
    )


def map_parcel_status(code: str | None) -> ParcelStatus:
    """Map a 4PX event code, warning once for unknown or absent codes."""
    if not code:
        _warn_unmapped(code)
        return ParcelStatus.UNKNOWN
    mapped = _STATUS_MAP.get(code)
    if mapped is None:
        _warn_unmapped(code)
        return ParcelStatus.UNKNOWN
    return mapped


def map_event_status(code: str | None) -> ParcelStatus | None:
    """Map an event code for history, retaining unknown status as null."""
    if not code or code not in _STATUS_MAP:
        _warn_unmapped(code)
        return None
    return _STATUS_MAP[code]


def parse_iso(value: str | None) -> datetime | None:
    """Parse only an offset-aware ISO timestamp."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def _timestamp(event: dict[str, Any]) -> str | None:
    value = event.get("tkDate")
    parsed = parse_iso(value)
    shape = (type(value).__name__, type(event.get("tkDateStr")).__name__, type(event.get("tkTimezone")).__name__)
    if shape not in _KNOWN_TIMESTAMP_SHAPES and shape not in _timestamp_shapes:
        _timestamp_shapes.add(shape)
        _LOGGER.warning("4PX timestamp field shape needs confirmation; tkDate=%s tkDateStr=%s tkTimezone=%s; %s", *shape, NEW_ISSUE_URL)
    if parsed is None:
        _warn_once("timestamp:invalid", "4PX timestamp is not offset-aware; open an issue: %s", NEW_ISSUE_URL)
        return None
    return str(value)


def build_history(events: list[Any] | None, *, max_events: int = HISTORY_MAX_EVENTS) -> list[dict[str, Any]]:
    """Make canonical oldest-to-newest history from 4PX's newest-first list."""
    history: list[tuple[datetime, dict[str, Any]]] = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        timestamp = _timestamp(event)
        if (parsed := parse_iso(timestamp)) is None:
            continue
        code = event.get("tkCode")
        history.append((parsed, {"timestamp": timestamp, "status": map_event_status(code), "raw_status": code}))
    history.sort(key=lambda item: item[0])
    return [entry for _, entry in history][-max_events:]


def tracking_url(code: str | None) -> str | None:
    """Return the consumer tracking page for a resolved barcode."""
    return TRACKING_URL.format(tracking_code=code) if code else None


def normalize_parcel(raw: dict[str, Any], *, include_history: bool = False) -> dict[str, Any]:
    """Normalise a resolved 4PX payload; skeletons are handled by coordinator."""
    events = raw.get("tracks") if isinstance(raw.get("tracks"), list) else []
    newest = events[0] if events and isinstance(events[0], dict) else {}
    code = newest.get("tkCode")
    status = map_parcel_status(code)
    delivered_at = _timestamp(newest) if status is ParcelStatus.DELIVERED else None
    return {
        "carrier": "4PX",
        "barcode": raw.get("serverCode"),
        "sender": raw.get("ctStartName") or None,
        "receiver": raw.get("ctEndName") or None,
        "status": status,
        "raw_status": code,
        "delivered": status is ParcelStatus.DELIVERED,
        "delivered_at": delivered_at,
        "planned_from": None,
        "planned_to": None,
        "pickup": False,
        "pickup_point": None,
        "url": tracking_url(raw.get("serverCode")),
        "weight": None,
        "dimensions": None,
        "history": build_history(events) if include_history else None,
        "raw": raw,
    }


def sort_parcels_by_ts(parcels: list[dict], key_field: str, *, descending: bool = False) -> list[dict]:
    """Sort parseable timestamp values first, keeping missing values last."""
    with_ts: list[tuple[datetime, dict]] = []
    without_ts: list[dict] = []
    for parcel in parcels:
        if (parsed := parse_iso(parcel.get(key_field))) is None:
            without_ts.append(parcel)
        else:
            with_ts.append((parsed, parcel))
    with_ts.sort(key=lambda item: item[0], reverse=descending)
    return [parcel for _, parcel in with_ts] + without_ts


def apply_delivered_filter(parcels: list[dict], entry: ConfigEntry) -> list[dict]:
    """Apply configured delivered-package retention to a sorted parcel list."""
    amount = int(entry.options.get(CONF_DELIVERED_FILTER_AMOUNT, DEFAULT_DELIVERED_FILTER_AMOUNT))
    if entry.options.get(CONF_DELIVERED_FILTER_TYPE, DEFAULT_DELIVERED_FILTER_TYPE) == "days":
        cutoff = datetime.now(timezone.utc) - timedelta(days=amount)
        return [p for p in parcels if (parsed := parse_iso(p.get("delivered_at"))) is None or parsed >= cutoff]
    return parcels[:amount]
