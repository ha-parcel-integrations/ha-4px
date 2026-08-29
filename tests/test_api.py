"""Tests for the real 4PX POST client."""
import json
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.fourpx.api import FPXApiClient, FPXApiError
from custom_components.fourpx.const import TRACKING_API_URL
from tests.payloads import active_sample, envelope, pending_sample


def _session(status: int, body: object, *, retry_after: str | None = None) -> MagicMock:
    response = AsyncMock(status=status)
    response.headers = {"Retry-After": retry_after} if retry_after is not None else {}
    response.json = AsyncMock(side_effect=json.JSONDecodeError("x", "x", 0) if isinstance(body, str) else None, return_value=None if isinstance(body, str) else body)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.post.return_value = context
    return session


async def test_posts_exactly_one_code_with_confirmed_language_fields():
    session = _session(200, envelope(active_sample()))
    parcel = await FPXApiClient(session).async_get_parcel("SYNTHETICACTIVE01")
    assert parcel["serverCode"] == "SYNTHETICACTIVE01"
    assert session.post.call_args.args[0] == TRACKING_API_URL
    assert session.post.call_args.kwargs["json"] == {"queryCodes": ["SYNTHETICACTIVE01"], "language": "en-us", "translateLanguage": ""}
    assert session.post.call_args.kwargs["headers"] == {"Accept": "application/json", "Content-Type": "application/json"}


async def test_pending_skeleton_returns_none():
    assert await FPXApiClient(_session(200, envelope(pending_sample()))).async_get_parcel("SYNTHETICPENDING") is None


@pytest.mark.parametrize("body", [{"result": 0, "data": None}, {"result": 1, "data": []}, {"result": 1, "data": [{"serverCode": "X", "tracks": None}]}])
async def test_unexpected_envelopes_fail_safely(body):
    with pytest.raises(FPXApiError):
        await FPXApiClient(_session(200, body)).async_get_parcel("SYNTHETIC")


async def test_transport_and_non_json_failures_are_transient():
    with pytest.raises(FPXApiError):
        await FPXApiClient(_session(429, {})).async_get_parcel("SYNTHETIC")
    with pytest.raises(FPXApiError):
        await FPXApiClient(_session(200, "html")).async_get_parcel("SYNTHETIC")
    session = MagicMock()
    session.post.side_effect = aiohttp.ClientError("transport")
    with pytest.raises(aiohttp.ClientError):
        await FPXApiClient(session).async_get_parcel("SYNTHETIC")


async def test_429_carries_status_code_and_numeric_retry_after():
    with pytest.raises(FPXApiError) as excinfo:
        await FPXApiClient(_session(429, {}, retry_after="120")).async_get_parcel("SYNTHETIC")
    assert excinfo.value.status_code == 429
    assert excinfo.value.retry_after == 120.0


async def test_429_without_retry_after_header_leaves_it_none():
    with pytest.raises(FPXApiError) as excinfo:
        await FPXApiClient(_session(429, {})).async_get_parcel("SYNTHETIC")
    assert excinfo.value.status_code == 429
    assert excinfo.value.retry_after is None


async def test_429_with_non_numeric_retry_after_falls_back_to_none():
    with pytest.raises(FPXApiError) as excinfo:
        await FPXApiClient(_session(429, {}, retry_after="Wed, 21 Oct 2026 07:28:00 GMT")).async_get_parcel("SYNTHETIC")
    assert excinfo.value.retry_after is None


async def test_non_429_error_carries_status_code():
    with pytest.raises(FPXApiError) as excinfo:
        await FPXApiClient(_session(500, {})).async_get_parcel("SYNTHETIC")
    assert excinfo.value.status_code == 500
