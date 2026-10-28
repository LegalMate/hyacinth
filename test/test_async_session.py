import inspect
import os
import subprocess
import sys
import unittest

import httpx
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from hyacinth.async_session import AsyncSession
from hyacinth.errors import (
    HTTPX_ERRORS,
    HTTPX_STATUS_ERRORS,
    HTTPX_TRANSPORT_ERRORS,
)

try:  # httpx2 is not a hard dependency of hyacinth
    import httpx2
except ImportError:
    httpx2 = None

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

    async def test_httpx_branch_is_unchanged(self):
        """The httpx path keeps its class, message, request, response, cause."""
        session = AsyncSession(
            token=test_token,
            client_id=test_client_id,
            client_secret=test_client_secret,
            raise_for_status=True,
        )

        error_body = b'{"error": {"message": "Matter not found"}}'
        request = httpx.Request("GET", "https://example.com/api/test.json")
        resp = MagicMock()
        resp.status_code = 404
        resp.headers = {"Content-Type": "application/json"}
        resp.content = error_body
        original = httpx.HTTPStatusError("404 error", request=request, response=resp)
        resp.raise_for_status.side_effect = original
        session.session.get = AsyncMock(return_value=resp)

        with self.assertRaises(httpx.HTTPStatusError) as ctx:
            await session.get_resource("https://example.com/api/test.json")

        err = ctx.exception
        self.assertIs(type(err), httpx.HTTPStatusError)
        self.assertEqual(
            str(err),
            "404 error - " + error_body.decode("utf-8", errors="replace"),
        )
        self.assertIs(err.request, request)
        self.assertIs(err.response, resp)
        self.assertIs(err.__cause__, original)


class TestAsyncDefaultUpdateToken(unittest.IsolatedAsyncioTestCase):
    """AsyncOAuth2Client awaits update_token on every refresh, so the default
    has to be a coroutine function or omitting it raises TypeError."""

    async def test_default_update_token_is_awaitable(self):
        session = AsyncSession(
            token=test_token,
            client_id=test_client_id,
            client_secret=test_client_secret,
        )
        update_token = session.session.update_token
        self.assertTrue(inspect.iscoroutinefunction(update_token))
        # Awaiting it is what authlib does; a plain function returning None
        # would raise TypeError here.
        self.assertIsNone(await update_token(test_token, refresh_token="r"))

    async def test_supplied_update_token_is_used(self):
        supplied = AsyncMock()
        session = AsyncSession(
            token=test_token,
            client_id=test_client_id,
            client_secret=test_client_secret,
            update_token=supplied,
        )
        self.assertIs(session.session.update_token, supplied)


@unittest.skipIf(httpx2 is None, "httpx2 not installed")
class TestAsyncRaiseForStatusHttpx2(unittest.IsolatedAsyncioTestCase):
    """Authlib 1.8+ runs the client on httpx2, and httpx2 errors are not httpx
    subclasses, so they used to escape the raise_for_status handler."""

    error_body = b'{"error": {"type": "invalid", "message": "Matter not found"}}'

    def _make_session(self):
        return AsyncSession(
            token=test_token,
            client_id=test_client_id,
            client_secret=test_client_secret,
            raise_for_status=True,
        )

    def _make_response(self, status_code, error_cls, request_cls):
        request = request_cls("GET", "https://example.com/api/test.json")
        resp = MagicMock()
        resp.status_code = status_code
        resp.headers = {"Content-Type": "application/json"}
        resp.content = self.error_body
        resp.raise_for_status.side_effect = error_cls(
            f"{status_code} error", request=request, response=resp
        )
        return resp, request

    async def _raised(self, status_code, error_cls, request_cls):
        session = self._make_session()
        resp, request = self._make_response(status_code, error_cls, request_cls)
        session.session.get = AsyncMock(return_value=resp)

        with self.assertRaises(error_cls) as ctx:
            await session.get_resource("https://example.com/api/test.json")

        return ctx.exception, resp, request

    async def test_404_takes_the_httpx_path(self):
        err, resp, request = await self._raised(
            404, httpx2.HTTPStatusError, httpx2.Request
        )

        self.assertIs(type(err), httpx2.HTTPStatusError)
        self.assertNotIsInstance(err, httpx.HTTPError)
        self.assertEqual(
            str(err),
            "404 error - " + self.error_body.decode("utf-8", errors="replace"),
        )
        self.assertIs(err.request, request)
        self.assertIs(err.response, resp)
        self.assertIsInstance(err.__cause__, httpx2.HTTPStatusError)

    async def test_429_takes_the_httpx_path(self):
        err, resp, request = await self._raised(
            429, httpx2.HTTPStatusError, httpx2.Request
        )

        self.assertIs(type(err), httpx2.HTTPStatusError)
        self.assertEqual(
            str(err),
            "429 error - " + self.error_body.decode("utf-8", errors="replace"),
        )
        self.assertIs(err.request, request)
        self.assertIs(err.response, resp)

    async def test_message_matches_the_httpx_message(self):
        """Same status and body, so the same message on both families."""
        from_httpx, _, _ = await self._raised(404, httpx.HTTPStatusError, httpx.Request)
        from_httpx2, _, _ = await self._raised(
            404, httpx2.HTTPStatusError, httpx2.Request
        )

        self.assertEqual(str(from_httpx), str(from_httpx2))

    async def test_read_timeout_is_not_wrapped(self):
        """A transport error is not a status error: it passes through as is."""
        session = self._make_session()
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {"Content-Type": "application/json"}
        resp.content = self.error_body
        resp.raise_for_status.side_effect = httpx2.ReadTimeout("read timed out")
        session.session.get = AsyncMock(return_value=resp)

        with self.assertRaises(httpx2.ReadTimeout) as ctx:
            await session.get_resource("https://example.com/api/test.json")

        self.assertEqual(str(ctx.exception), "read timed out")
        self.assertIsInstance(ctx.exception, HTTPX_ERRORS)
        self.assertIsInstance(ctx.exception, HTTPX_TRANSPORT_ERRORS)

    async def test_connect_error_during_request_is_caught_by_the_tuple(self):
        """Transport errors raised by the request itself reach the caller."""
        session = self._make_session()
        session.session.get = AsyncMock(side_effect=httpx2.ConnectError("no route"))

        with self.assertRaises(httpx2.ConnectError) as ctx:
            await session.get_resource("https://example.com/api/test.json")

        self.assertIsInstance(ctx.exception, HTTPX_ERRORS)
        self.assertIsInstance(ctx.exception, HTTPX_TRANSPORT_ERRORS)


class TestErrorTuples(unittest.TestCase):
    def test_tuple_covers_status_transport_timeout_and_base(self):
        for exc in (
            httpx.HTTPError,
            httpx.HTTPStatusError,
            httpx.TransportError,
            httpx.TimeoutException,
        ):
            self.assertIn(exc, HTTPX_ERRORS)

        if httpx2 is None:
            return

        for exc in (
            httpx2.HTTPError,
            httpx2.HTTPStatusError,
            httpx2.TransportError,
            httpx2.TimeoutException,
        ):
            self.assertIn(exc, HTTPX_ERRORS)

    def test_httpx2_is_not_an_httpx_subclass(self):
        if httpx2 is None:
            self.skipTest("httpx2 not installed")

        for exc in (
            httpx2.HTTPError,
            httpx2.HTTPStatusError,
            httpx2.TransportError,
            httpx2.TimeoutException,
        ):
            self.assertFalse(issubclass(exc, httpx.HTTPError))

    def test_status_tuple_holds_both_families(self):
        self.assertIn(httpx.HTTPStatusError, HTTPX_STATUS_ERRORS)
        if httpx2 is not None:
            self.assertIn(httpx2.HTTPStatusError, HTTPX_STATUS_ERRORS)

    def test_imports_and_catches_without_httpx2(self):
        """hyacinth has to install and import where httpx2 is absent."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        code = (
            "import sys\n"
            "sys.modules['httpx2'] = None\n"
            "import httpx, hyacinth\n"
            "from hyacinth.errors import HTTPX2_STATUS_ERRORS, HTTPX_ERRORS\n"
            "assert HTTPX2_STATUS_ERRORS == (), HTTPX2_STATUS_ERRORS\n"
            "assert HTTPX_ERRORS == (\n"
            "    httpx.HTTPError,\n"
            "    httpx.HTTPStatusError,\n"
            "    httpx.TransportError,\n"
            "    httpx.TimeoutException,\n"
            "), HTTPX_ERRORS\n"
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=root,
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
