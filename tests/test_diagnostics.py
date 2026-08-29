"""Diagnostics redaction tests using synthetic identifiers only."""
from datetime import timedelta
from unittest.mock import MagicMock

from custom_components.fourpx.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_redacts_all_4px_identifier_and_contact_fields(hass):
    entry = MagicMock()
    entry.options = {"parcels": [{"tracking_code": "SYNTHETICCODE"}]}
    entry.runtime_data.coordinator.current_tier_minutes = 15
    entry.runtime_data.coordinator.update_interval = timedelta(minutes=15)
    entry.runtime_data.coordinator.data = [{
        "barcode": "SYNTHETICCODE", "sender": "origin label", "receiver": "destination label",
        "status": "in_transit", "raw": {
            "queryCode": "SYNTHETICCODE", "serverCode": "SYNTHETICCODE",
            "shipperCode": "SYNTHETICSHIPPER", "hawbCodeSet": ["SYNTHETICHANDOFF"],
            "channelContact": {"placeholder": "synthetic"}, "sigPicUrl": "https://invalid.test/synthetic",
            "tkLocation": "synthetic location", "tkDesc": "synthetic prose", "spTkZipCode": "00000",
        },
    }]
    entry.runtime_data.coordinator.delivered = []
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["counts"] == {"incoming_active": 1, "delivered": 0}
    assert result["polling"] == {
        "tier_minutes": 15,
        "update_interval_seconds": 900.0,
        "suspended": False,
    }
    redacted = str(result)
    for value in ("SYNTHETICCODE", "SYNTHETICSHIPPER", "SYNTHETICHANDOFF", "synthetic location", "synthetic prose"):
        assert value not in redacted
    assert result["incoming"][0]["status"] == "in_transit"


async def test_diagnostics_reports_suspended_polling(hass):
    """update_interval None (the full-stop tier) must be visible, not just absent."""
    entry = MagicMock()
    entry.options = {"parcels": []}
    entry.runtime_data.coordinator.current_tier_minutes = None
    entry.runtime_data.coordinator.update_interval = None
    entry.runtime_data.coordinator.data = []
    entry.runtime_data.coordinator.delivered = []

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["polling"] == {
        "tier_minutes": None,
        "update_interval_seconds": None,
        "suspended": True,
    }
