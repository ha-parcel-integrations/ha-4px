"""Constants for the 4PX parcel tracker integration."""
from enum import StrEnum

from homeassistant.const import Platform

DOMAIN = "fourpx"


class ParcelStatus(StrEnum):
    """Carrier-agnostic parcel status shared by the suite."""

    REGISTERED = "registered"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    AT_PICKUP_POINT = "at_pickup_point"
    DELIVERED = "delivered"
    RETURNING = "returning"
    PROBLEM = "problem"
    UNKNOWN = "unknown"


PLATFORMS = [Platform.BUTTON, Platform.CALENDAR, Platform.SENSOR]
KNOWN_CAPABILITIES = frozenset({"weight", "dimensions", "delivery_window", "pickup_point", "url", "history"})
# 4PX supplies a timeline and a public consumer page. ETA, collection details,
# weight and dimensions are deliberately not inferred from unconfirmed fields.
CAPABILITIES = frozenset({"url", "history"})

TRACKING_API_URL = "https://track.4px.com/track/v2/front/listTrackV3"
TRACKING_URL = "https://track.4px.com/#/track?trackCode={tracking_code}"

CONF_PARCELS = "parcels"
CONF_TRACKING_CODE = "tracking_code"
CONF_DELIVERED_FILTER_TYPE = "delivered_filter_type"
CONF_DELIVERED_FILTER_AMOUNT = "delivered_filter_amount"
DEFAULT_DELIVERED_FILTER_TYPE = "days"
DEFAULT_DELIVERED_FILTER_AMOUNT = 7
# Dynamic, status-driven polling — unconditional across the suite, no
# user-facing interval option (see CLAUDE.md's "Dynamic polling" section for
# the full algorithm and the reasoning behind it).
#
# Quiet window: no polling between these local hours except the two anchors
# below, for overnight / end-of-day catch-up.
QUIET_WINDOW_START_HOUR = 0
QUIET_WINDOW_END_HOUR = 6

# Cadence while polling is active (minutes). Hot = at least one tracked,
# not-yet-delivered parcel is out_for_delivery within HOT_LOOKAHEAD_HOURS of
# its planned_from (or has no planned_from at all); mid = anything else still
# in flight (registered, in_transit, at_pickup_point, unknown, problem,
# returning).
HOT_INTERVAL_MINUTES = 15
MID_INTERVAL_MINUTES = 45
HOT_LOOKAHEAD_HOURS = 1

# Small, stable per-install offset added to every computed interval so
# different installs don't all hit an anchor or tier boundary at the same
# second. Deterministic (hash of the config entry id), not random.
STAGGER_MINUTES = 7

CONF_INCLUDE_HISTORY = "include_history"
DEFAULT_INCLUDE_HISTORY = False
HISTORY_MAX_EVENTS = 20
