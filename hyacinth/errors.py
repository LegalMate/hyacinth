"""hyacinth/errors.py -- error tuples covering the httpx and httpx2 families.

Authlib 1.8+ runs AsyncOAuth2Client on httpx2, and httpx2 exceptions are not
httpx subclasses. These tuples let a caller catch status, transport, timeout
and base HTTPError from either family with one handler.
"""

import httpx

try:  # httpx2 ships with Authlib 1.8+; older installs do not have it
    import httpx2
except ImportError:  # pragma: no cover - only when httpx2 is absent
    httpx2 = None

HAS_HTTPX2 = httpx2 is not None

HTTPX2_STATUS_ERRORS = (httpx2.HTTPStatusError,) if HAS_HTTPX2 else ()
HTTPX2_TRANSPORT_ERRORS = (httpx2.TransportError,) if HAS_HTTPX2 else ()
HTTPX2_TIMEOUT_ERRORS = (httpx2.TimeoutException,) if HAS_HTTPX2 else ()
HTTPX2_BASE_ERRORS = (httpx2.HTTPError,) if HAS_HTTPX2 else ()

HTTPX_STATUS_ERRORS = (httpx.HTTPStatusError,) + HTTPX2_STATUS_ERRORS
HTTPX_TRANSPORT_ERRORS = (httpx.TransportError,) + HTTPX2_TRANSPORT_ERRORS
HTTPX_TIMEOUT_ERRORS = (httpx.TimeoutException,) + HTTPX2_TIMEOUT_ERRORS


def _unique(*groups):
    """Flatten exception tuples, dropping duplicates but keeping order."""
    flat = []
    for group in groups:
        for exc in group:
            if exc not in flat:
                flat.append(exc)
    return tuple(flat)


# Base HTTPError of both families plus every specific error above.
HTTPX_ERRORS = _unique(
    (httpx.HTTPError,),
    HTTPX2_BASE_ERRORS,
    HTTPX_STATUS_ERRORS,
    HTTPX_TRANSPORT_ERRORS,
    HTTPX_TIMEOUT_ERRORS,
)


def status_error_with_body(error, response):
    """Rebuild a status error with Clio's response body appended.

    The class of the originating family is kept, so an httpx2 error stays an
    httpx2 error and an httpx error stays an httpx error.
    """
    message = f"{error} - {response.content.decode('utf-8', errors='replace')}"
    return type(error)(message, request=error.request, response=error.response)
