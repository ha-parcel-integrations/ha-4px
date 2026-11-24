"""The parcel contract's checks, run over every normalised sample."""

from datetime import datetime

import pytest

from custom_components.fourpx import parcels
from custom_components.fourpx.const import ParcelStatus
from custom_components.fourpx.parcels import (
    normalize_parcel,
    parse_iso,
    planned_for_status,
    planned_window,
)
from tests.payloads import active_sample, delivered_sample, event, pending_sample

CANONICAL_KEYS = [
    "carrier",
    "barcode",
    "sender",
    "receiver",
    "contents",
    "status",
    "raw_status",
    "delivered",
    "delivered_at",
    "planned_from",
    "planned_to",
    "pickup",
    "pickup_point",
    "url",
    "weight",
    "dimensions",
    "history",
    "raw",
]

SAMPLES = {
    "delivered": delivered_sample,
    "active": active_sample,
    "pending": pending_sample,
}


@pytest.fixture(params=SAMPLES)
def parcel(request) -> dict:
    return normalize_parcel(SAMPLES[request.param]())


def test_keys_and_order(parcel):
    assert list(parcel) == CANONICAL_KEYS


def test_delivered_follows_status(parcel):
    assert parcel["delivered"] is (parcel["status"] is ParcelStatus.DELIVERED)


def test_delivered_at_only_when_delivered(parcel):
    if not parcel["delivered"]:
        assert parcel["delivered_at"] is None


def test_planned_window_is_ordered_and_anchored(parcel):
    if parcel["planned_to"] is not None:
        assert parcel["planned_from"] is not None
        assert parse_iso(parcel["planned_to"]) > parse_iso(parcel["planned_from"])


def test_pickup_is_a_bool_and_the_point_needs_it(parcel):
    assert isinstance(parcel["pickup"], bool)
    if not parcel["pickup"]:
        assert parcel["pickup_point"] is None


def test_planned_is_emptied_for_a_finished_or_waiting_parcel():
    for status in (
        ParcelStatus.DELIVERED,
        ParcelStatus.AT_PICKUP_POINT,
        ParcelStatus.RETURNING,
    ):
        assert planned_for_status(status, "2099-01-01T10:00:00Z", None) == (None, None)
    assert planned_for_status(ParcelStatus.IN_TRANSIT, "a", "b") == ("a", "b")


def test_a_collected_pickup_parcel_stays_pickup(monkeypatch):
    monkeypatch.setitem(
        parcels._STATUS_MAP, "SYNTHETIC_PICKUP", ParcelStatus.AT_PICKUP_POINT
    )
    sample = delivered_sample()
    sample["tracks"] = [
        event("FPX_S_OK", "2026-04-29T16:00:00+00:00"),
        event("SYNTHETIC_PICKUP", "2026-04-29T09:00:00+00:00"),
    ]
    parcel = normalize_parcel(sample)
    assert parcel["delivered"] is True
    assert parcel["pickup"] is True
    assert parcel["pickup_point"] is None
    assert parcel["planned_from"] is parcel["planned_to"] is None


def test_a_moment_ends_at_the_end_of_that_day():
    start, end = planned_window(
        "2099-04-29T13:00:00+00:00", None, zone=parcels.timezone.utc
    )
    last = datetime.fromisoformat(end)
    assert (last.hour, last.minute, last.second, last.microsecond) == (23, 59, 59, 0)
    assert last.date() == parse_iso(start).date()


def test_a_date_covers_the_whole_day():
    start, end = planned_window("2099-04-29", None, zone=parcels.timezone.utc)
    first = datetime.fromisoformat(start)
    last = datetime.fromisoformat(end)
    assert (first.hour, first.minute, first.second) == (0, 0, 0)
    assert (last.hour, last.minute, last.second, last.microsecond) == (23, 59, 59, 0)
    assert first.date() == last.date()
