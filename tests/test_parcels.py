"""Tests for 4PX's conservative payload mapping."""
from custom_components.fourpx.const import (
    CAPABILITIES,
    KNOWN_CAPABILITIES,
    ParcelStatus,
)
from custom_components.fourpx.parcels import (
    _STATUS_MAP,
    _timestamp_shapes,
    _warned,
    build_history,
    map_parcel_status,
    normalize_parcel,
    parse_iso,
)
from tests.payloads import active_sample, delivered_sample, event


def setup_function() -> None:
    _warned.clear()
    _timestamp_shapes.clear()


def test_all_observed_codes_are_conservatively_mapped():
    assert _STATUS_MAP == {
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


def test_delivery_failed_maps_to_problem():
    assert map_parcel_status("FPX_D_FD") is ParcelStatus.PROBLEM


def test_unknown_or_missing_code_warns_once(caplog):
    assert map_parcel_status("FUTURE_CODE") is ParcelStatus.UNKNOWN
    assert map_parcel_status("FUTURE_CODE") is ParcelStatus.UNKNOWN
    assert map_parcel_status(None) is ParcelStatus.UNKNOWN
    assert caplog.text.count("FUTURE_CODE") == 1
    assert "issues/new?template=unrecognised_status.yml" in caplog.text


def test_timestamp_requires_an_offset():
    assert parse_iso("2026-04-29T13:12:42+00:00") is not None
    assert parse_iso("2026-04-29T13:12:42") is None


def test_live_confirmed_timestamp_shapes_do_not_warn(caplog):
    build_history(
        [
            event("FPX_C_AAF", "2026-04-29T13:12:42+00:00"),
            {
                "tkCode": "FPX_C_AAF",
                "tkDate": "2026-04-29T13:13:42+00:00",
                "tkDateStr": "2026-04-29 13:13:42",
                "tkTimezone": None,
            },
        ]
    )
    assert "timestamp field shape needs confirmation" not in caplog.text


def test_numeric_parcel_status_does_not_warn_without_a_confirmed_mapping(caplog):
    normalize_parcel(active_sample())
    assert "numeric parcel status" not in caplog.text


def test_history_reverses_events_and_uses_offset_bearing_tkdate():
    history = build_history(delivered_sample()["tracks"])
    assert [item["raw_status"] for item in history] == ["FPX_L_RPIF", "FPX_O_RR", "FPX_D_SD", "FPX_S_OK"]
    assert history[-1]["timestamp"] == "2026-04-29T13:12:42+00:00"
    assert history[-1]["status"] is ParcelStatus.DELIVERED


def test_history_caps_and_skips_offsetless_events():
    events = [event("FPX_C_AAF", f"2026-04-{day:02d}T01:00:00+00:00") for day in range(1, 25)]
    events.append(event("FPX_C_AAF", "2026-04-30T01:00:00"))
    assert len(build_history(events)) == 20


def test_normalize_pending_placeholder_does_not_warn(caplog):
    parcel = normalize_parcel({"serverCode": "SYNTHETICPENDING", "tracks": []})
    assert parcel["status"] is ParcelStatus.UNKNOWN
    assert parcel["raw_status"] is None
    assert "Unrecognised 4PX status shape" not in caplog.text


def test_normalize_resolved_parcel_missing_tkcode_still_warns(caplog):
    raw = active_sample()
    del raw["tracks"][0]["tkCode"]
    parcel = normalize_parcel(raw)
    assert parcel["status"] is ParcelStatus.UNKNOWN
    assert "Unrecognised 4PX status shape" in caplog.text
    assert "tkCode=<missing>" in caplog.text


def test_normalize_delivered_and_active_contract():
    delivered = normalize_parcel(delivered_sample(), include_history=True)
    active = normalize_parcel(active_sample())
    assert list(delivered) == ["carrier", "barcode", "sender", "receiver", "status", "raw_status", "delivered", "delivered_at", "planned_from", "planned_to", "pickup", "pickup_point", "url", "weight", "dimensions", "history", "raw"]
    assert delivered["status"] is ParcelStatus.DELIVERED
    assert delivered["delivered_at"] == "2026-04-29T13:12:42+00:00"
    assert delivered["history"][0]["raw_status"] == "FPX_L_RPIF"
    assert active["status"] is ParcelStatus.OUT_FOR_DELIVERY
    assert active["delivered"] is False
    assert active["planned_from"] is active["pickup_point"] is active["weight"] is None


def test_normalize_does_not_leak_event_text_or_location_to_attributes():
    raw = active_sample()
    raw["tracks"][0].update({"tkDesc": "redacted event prose", "tkLocation": "redacted location"})
    parcel = normalize_parcel(raw, include_history=True)
    assert "redacted event prose" not in str({key: value for key, value in parcel.items() if key != "raw"})
    assert "redacted location" not in str({key: value for key, value in parcel.items() if key != "raw"})


def test_capabilities_match_confirmed_fields_only():
    assert CAPABILITIES == frozenset({"url", "history"})
    assert CAPABILITIES <= KNOWN_CAPABILITIES
