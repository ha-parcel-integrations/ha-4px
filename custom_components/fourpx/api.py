"""4PX public tracking API client."""
from __future__ import annotations

from typing import Any

import aiohttp

from .const import TRACKING_API_URL


class FPXApiError(Exception):
    """Raised when 4PX returns an unusable response."""

    def __init__(
        self,
        detail: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Store the safe failure classification, status code and Retry-After."""
        super().__init__(f"4PX API request failed: {detail}")
        self.detail = detail
        self.status_code = status_code
        self.retry_after = retry_after


class FPXApiClient:
    """Client for 4PX's anonymous, one-code-per-request tracking endpoint."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialise the client with Home Assistant's HTTP session."""
        self._session = session

    async def async_get_parcel(self, tracking_code: str) -> dict[str, Any] | None:
        """Return a resolved raw parcel, or ``None`` for the pending skeleton.

        The confirmed pending/not-recognised branch is ``result == 1`` with one
        item whose ``serverCode`` and ``tracks`` are both null. All other
        malformed envelopes fail transiently instead of guessing.
        """
        request_body = {
            "queryCodes": [tracking_code],
            "language": "en-us",
            "translateLanguage": "",
        }
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        async with self._session.post(
            TRACKING_API_URL, json=request_body, headers=headers
        ) as response:
            if response.status == 429:
                retry_after_header = response.headers.get("Retry-After")
                try:
                    retry_after = float(retry_after_header) if retry_after_header else None
                except ValueError:
                    retry_after = None  # an HTTP-date, not seconds; let the caller's own backoff handle it
                raise FPXApiError(
                    "HTTP 429", status_code=429, retry_after=retry_after
                )
            if response.status != 200:
                raise FPXApiError(f"HTTP {response.status}", status_code=response.status)
            try:
                payload = await response.json(content_type=None)
            except (ValueError, aiohttp.ContentTypeError) as err:
                raise FPXApiError("unparseable body") from err

        if not isinstance(payload, dict):
            raise FPXApiError("unexpected body (not a JSON object)")
        if payload.get("result") != 1:
            raise FPXApiError("unexpected result envelope")
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise FPXApiError("unexpected parcel count or shape")
        parcel = data[0]
        if parcel.get("serverCode") is None and parcel.get("tracks") is None:
            return None
        if not parcel.get("serverCode") or not isinstance(parcel.get("tracks"), list) or not parcel["tracks"]:
            raise FPXApiError("resolved parcel missing barcode or tracks")
        return parcel
