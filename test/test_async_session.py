import unittest

import httpx
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from hyacinth.async_session import AsyncSession

test_token = {
    "access_token": "not-a-real-access-token",
    "refresh_token": "not-a-real-refresh-token",
    "token_type": "bearer",
    "expires_in": int((timedelta(days=2)).total_seconds()),
    "expires_at": int((datetime.now() + timedelta(days=2)).timestamp()),
}
test_client_id = "test_client_id"
test_client_secret = "test_client_secret"


class TestAsyncRefreshOn401(unittest.IsolatedAsyncioTestCase):
    def _make_response(self, status_code, content=b'{"data": {}}', content_type="application/json"):
        resp = MagicMock()
        resp.status_code = status_code
        resp.headers = {"Content-Type": content_type}
        resp.content = content
        resp.json.return_value = {"data": {}}
        return resp

    def _make_session(self, refresh_on_401=False, raise_for_status=False):
        return AsyncSession(
            token=test_token,
            client_id=test_client_id,
            client_secret=test_client_secret,
            refresh_on_401=refresh_on_401,
            raise_for_status=raise_for_status,
        )

    async def test_401_triggers_refresh_and_retries(self):
        """401 with refresh_on_401=True calls refresh_token and retries."""
        session = self._make_session(refresh_on_401=True)

        resp_401 = self._make_response(401)
        resp_200 = self._make_response(200)
        session.session.get = AsyncMock(side_effect=[resp_401, resp_200])
        session.session.refresh_token = AsyncMock()

        result = await session.get_resource("https://example.com/api/test.json")

        session.session.refresh_token.assert_called_once_with(url=session.token_endpoint)
        self.assertEqual(result, {"data": {}})

    async def test_401_retry_also_401_falls_through(self):
        """If retry after refresh also returns 401, no infinite loop."""
        session = self._make_session(refresh_on_401=True)

        resp_401_first = self._make_response(401)
        resp_401_second = self._make_response(401)
        session.session.get = AsyncMock(side_effect=[resp_401_first, resp_401_second])
        session.session.refresh_token = AsyncMock()

        result = await session.get_resource("https://example.com/api/test.json")

        session.session.refresh_token.assert_called_once()
        self.assertEqual(result, {"data": {}})

    async def test_401_without_refresh_on_401_falls_through(self):
        """401 with refresh_on_401=False (default) falls through unchanged."""
        session = self._make_session(refresh_on_401=False)

        resp_401 = self._make_response(401)
        session.session.get = AsyncMock(return_value=resp_401)

        result = await session.get_resource("https://example.com/api/test.json")

        session.session.get.assert_called_once()
        self.assertEqual(result, {"data": {}})

    async def test_failed_refresh_falls_through_with_original_401(self):
        """If refresh_token raises an exception, falls through with original 401."""
        session = self._make_session(refresh_on_401=True)

        resp_401 = self._make_response(401)
        session.session.get = AsyncMock(return_value=resp_401)
        session.session.refresh_token = AsyncMock(side_effect=Exception("refresh failed"))

        result = await session.get_resource("https://example.com/api/test.json")

        session.session.refresh_token.assert_called_once()
        session.session.get.assert_called_once()
        self.assertEqual(result, {"data": {}})


class TestAsyncRaiseForStatusIncludesBody(unittest.IsolatedAsyncioTestCase):
    async def test_error_response_includes_clio_body(self):
        """raise_for_status includes Clio's response body in the exception."""
        session = AsyncSession(
            token=test_token,
            client_id=test_client_id,
            client_secret=test_client_secret,
            raise_for_status=True,
        )

        error_body = b'{"error": {"type": "invalid", "message": "Matter not found"}}'
        request = httpx.Request("GET", "https://example.com/api/test.json")
        resp = MagicMock()
        resp.status_code = 404
        resp.headers = {"Content-Type": "application/json"}
        resp.content = error_body
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=request, response=resp,
        )
        session.session.get = AsyncMock(return_value=resp)

        with self.assertRaises(httpx.HTTPStatusError) as ctx:
            await session.get_resource("https://example.com/api/test.json")

        self.assertIn("Matter not found", str(ctx.exception))
