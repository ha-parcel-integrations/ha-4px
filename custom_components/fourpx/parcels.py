"""Pure 4PX parcel mapping helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta, timezone, tzinfo
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
    "FPX_O_IR": ParcelStatus.REGISTERED,
    "FPX_O_IRI": ParcelStatus.REGISTERED,
    "FPX_C_SPLS": ParcelStatus.IN_TRANSIT,
    "FPX_C_AAF": ParcelStatus.IN_TRANSIT,
    "FPX_C_ADFF": ParcelStatus.IN_TRANSIT,
    "FPX_O_RR": ParcelStatus.IN_TRANSIT,
    "FPX_M_HA": ParcelStatus.IN_TRANSIT,
    "FPX_M_DFOA": ParcelStatus.IN_TRANSIT,
    "FPX_M_ATA": ParcelStatus.IN_TRANSIT,
    "FPX_M_CRSD": ParcelStatus.IN_TRANSIT,
    "FPX_M_IT": ParcelStatus.IN_TRANSIT,
    # "Shipment in transit", category "Transit in the country of origin"
    "FPX_F_ST": ParcelStatus.IN_TRANSIT,
    "FPX_I_RCUK": ParcelStatus.IN_TRANSIT,
    "FPX_D_AOPC": ParcelStatus.IN_TRANSIT,
    "FPX_D_APC": ParcelStatus.IN_TRANSIT,
    "FPX_D_AAD": ParcelStatus.IN_TRANSIT,
    "FPX_D_STPP": ParcelStatus.IN_TRANSIT,
    "FPX_D_HQ": ParcelStatus.IN_TRANSIT,
    "FPX_D_SD": ParcelStatus.OUT_FOR_DELIVERY,
    "FPX_D_FD": ParcelStatus.PROBLEM,
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
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def _timestamp(event: dict[str, Any]) -> str | None:
    value = event.get("tkDate")
    parsed = parse_iso(value)
    shape = (
        type(value).__name__,
        type(event.get("tkDateStr")).__name__,
        type(event.get("tkTimezone")).__name__,
    )
    if shape not in _KNOWN_TIMESTAMP_SHAPES and shape not in _timestamp_shapes:
        _timestamp_shapes.add(shape)
        _LOGGER.warning(
            "4PX timestamp field shape needs confirmation; tkDate=%s tkDateStr=%s tkTimezone=%s; %s",
            *shape,
            NEW_ISSUE_URL,
        )
    if parsed is None:
        _warn_once(
            "timestamp:invalid",
            "4PX timestamp is not offset-aware; open an issue: %s",
            NEW_ISSUE_URL,
        )
        return None
    return str(value)


def build_history(
    events: list[Any] | None, *, max_events: int = HISTORY_MAX_EVENTS
) -> list[dict[str, Any]]:
    """Make canonical oldest-to-newest history from 4PX's newest-first list."""
    history: list[tuple[datetime, dict[str, Any]]] = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        timestamp = _timestamp(event)
        if (parsed := parse_iso(timestamp)) is None:
            continue
        code = event.get("tkCode")
        history.append(
            (
                parsed,
                {
                    "timestamp": timestamp,
                    "status": map_event_status(code),
                    "raw_status": code,
                },
            )
        )
    history.sort(key=lambda item: item[0])
    return [entry for _, entry in history][-max_events:]


def tracking_url(code: str | None) -> str | None:
    """Return the consumer tracking page for a resolved barcode."""
    return TRACKING_URL.format(tracking_code=code) if code else None


def _moment(value: Any, zone: tzinfo) -> tuple[datetime, bool, str] | None:
    """Return ``(aware datetime, date_only, text)`` for a carrier time, or ``None``.

    A naive time or a bare date gets ``zone``; an aware time keeps its offset
    and, when it came in as a string, its own spelling.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        moment = datetime.combine(value, time.min, tzinfo=zone)
        return moment, True, moment.isoformat()
    elif isinstance(value, str) and value:
        try:
            if len(value) == 10:
                moment = datetime.combine(
                    date.fromisoformat(value), time.min, tzinfo=zone
                )
                return moment, True, moment.isoformat()
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo:
            return parsed, False, value
    else:
        return None
    moment = parsed if parsed.tzinfo else parsed.replace(tzinfo=zone)
    return moment, False, moment.isoformat()


def _end_of_day(moment: datetime, zone: tzinfo) -> datetime:
    local = moment.astimezone(zone)
    return datetime.combine(local.date(), time(23, 59, 59), tzinfo=zone)


def planned_window(
    start: Any, end: Any, *, zone: tzinfo
) -> tuple[str | None, str | None]:
    """Return ``(planned_from, planned_to)`` in the canonical window shape.

    ``start`` and ``end`` are ISO strings, dates or datetimes, or ``None``; an
    epoch number must be converted first (see ``to_iso_timestamp``). A window
    keeps both ends. One moment with a time ends at ``23:59:59`` the same local
    day; a date covers ``00:00:00`` to ``23:59:59``; two dates run from the
    first day's start to the last day's end. Equal values are one moment,
    reversed values are swapped, and ``planned_to`` is never set without
    ``planned_from``. ``zone`` is the carrier's own zone: it dates naive times
    and bare dates and decides which day a moment ends on, so a ``Z`` moment
    still ends on the carrier's local day. When nothing is left of that day
    after the moment, there is no ``planned_to``.
    """
    first = _moment(start, zone)
    last = _moment(end, zone)
    if first is None:
        first, last = last, None
    if first is None:
        return None, None

    def closing(moment: tuple[datetime, bool, str]) -> datetime:
        return _end_of_day(moment[0], zone) if moment[1] else moment[0]

    if last is not None and closing(last) < first[0]:
        first, last = last, first
    if last is not None and closing(last) == first[0]:
        last = None

    if last is None:
        end_of_day = _end_of_day(first[0], zone)
        return first[2], end_of_day.isoformat() if end_of_day > first[0] else None
    return first[2], closing(last).isoformat() if last[1] else last[2]


_NO_WINDOW_STATUSES = frozenset(
    {ParcelStatus.AT_PICKUP_POINT, ParcelStatus.RETURNING, ParcelStatus.DELIVERED}
)


def planned_for_status(
    status: ParcelStatus, planned_from: str | None, planned_to: str | None
) -> tuple[str | None, str | None]:
    """Empty the delivery window once the parcel is at its destination or done."""
    if status in _NO_WINDOW_STATUSES:
        return None, None
    return planned_from, planned_to


def is_pickup(
    route_flag: bool | None,
    status: ParcelStatus,
    event_statuses: Iterable[ParcelStatus | None] = (),
) -> bool:
    """Whether the delivery route ends at a pickup point.

    The carrier's own route flag wins; otherwise the parcel having reached
    ``AT_PICKUP_POINT`` at any point counts, so the value survives collection.
    """
    if route_flag:
        return True
    return status is ParcelStatus.AT_PICKUP_POINT or any(
        event is ParcelStatus.AT_PICKUP_POINT for event in event_statuses
    )


def normalize_parcel(
    raw: dict[str, Any], *, include_history: bool = False
) -> dict[str, Any]:
    """Normalise a resolved 4PX payload; skeletons are handled by coordinator."""
    events = raw.get("tracks") if isinstance(raw.get("tracks"), list) else []
    newest = events[0] if events and isinstance(events[0], dict) else {}
    if events:
        code = newest.get("tkCode")
        status = map_parcel_status(code)
    else:
        # No track events at all is the confirmed pending/not-yet-scanned
        # shape — api.py's null/null envelope, or the coordinator's synthetic
        # not-found placeholder — not a novel status shape, so it must not
        # trip the unrecognised-shape warning below.
        code = None
        status = ParcelStatus.UNKNOWN
    delivered_at = _timestamp(newest) if status is ParcelStatus.DELIVERED else None
    planned_from, planned_to = planned_for_status(status, None, None)
    pickup = is_pickup(
        None,
        status,
        (
            _STATUS_MAP.get(event.get("tkCode"))
            for event in events
            if isinstance(event, dict)
        ),
    )
    return {
        "carrier": "4PX",
        "barcode": raw.get("serverCode"),
        "sender": raw.get("ctStartName") or None,
        "receiver": raw.get("ctEndName") or None,
        "contents": None,
        "status": status,
        "raw_status": code,
        "delivered": status is ParcelStatus.DELIVERED,
        "delivered_at": delivered_at,
        "planned_from": planned_from,
        "planned_to": planned_to,
        "pickup": pickup,
        "pickup_point": None,
        "url": tracking_url(raw.get("serverCode")),
        "weight": None,
        "dimensions": None,
        "history": build_history(events) if include_history else None,
        "raw": raw,
    }


def sort_parcels_by_ts(
    parcels: list[dict], key_field: str, *, descending: bool = False
) -> list[dict]:
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
    amount = int(
        entry.options.get(CONF_DELIVERED_FILTER_AMOUNT, DEFAULT_DELIVERED_FILTER_AMOUNT)
    )
    if (
        entry.options.get(CONF_DELIVERED_FILTER_TYPE, DEFAULT_DELIVERED_FILTER_TYPE)
        == "days"
    ):
        cutoff = datetime.now(timezone.utc) - timedelta(days=amount)
        return [
            p
            for p in parcels
            if (parsed := parse_iso(p.get("delivered_at"))) is None or parsed >= cutoff
        ]
    return parcels[:amount]
