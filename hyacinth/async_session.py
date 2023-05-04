"""async_session.py -- Async Session for Clio API."""
import logging
import functools
import asyncio
import aiohttp

from authlib.integrations.httpx_client import AsyncOAuth2Client


CLIO_API_BASE_URL_US = "https://app.clio.com/api/v4"
CLIO_API_TOKEN_ENDPOINT = "https://app.clio.com/oauth/token"  # nosec
CLIO_API_RATELIMIT_LIMIT_HEADER = "X-RateLimit-Limit"
CLIO_API_RATELIMIT_REMAINING_HEADER = "X-RateLimit-Remaining"


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


def ratelimit(f):
    """Rate limit a function with Clio rate limites.

    See: https://docs.developers.clio.com/api-docs/rate-limits/
    """
    @functools.wraps(f)
    async def wrapper(self, *args, **kwargs):
        resp = await f(self, *args, **kwargs)

        if resp.status_code == 429 and self.ratelimit:
            retry_after = resp.headers.get("Retry-After")
            log.info(f"Clio Rate Limit hit, Retry-After: {retry_after}s")

            # Retry the request after sleeping for the required time
            await asyncio.sleep(int(retry_after))
            resp = await f(self, *args, **kwargs)

        elif self.raise_for_status:
            resp.raise_for_status()

        if resp.status_code == 204:
            return None

        return resp.json()

    return wrapper


class AsyncSession:
    """Class for interacting with Clio Manage API using async/await."""

    def __init__(
        self,
        token: dict,
        client_id: str,
        client_secret: str,
        ratelimit=False,
        raise_for_status=False,
        update_token=lambda *args: None,
    ):
        """Initialize our Session with an AsyncOAuth2Client."""
        self.session = AsyncOAuth2Client(
            client_id=client_id,
            client_secret=client_secret,
            token=token,
            token_endpoint=CLIO_API_TOKEN_ENDPOINT,
            update_token=update_token,
        )
        self.ratelimit = ratelimit
        self.raise_for_status = raise_for_status

    @ratelimit
    async def __get(self, url: str, **kwargs):
        return await self.session.get(url, **kwargs)

    @ratelimit
    async def __post(self, url: str, json: dict, **kwargs):
        return await self.session.post(url, json=json, **kwargs)

    @ratelimit
    async def __patch(self, url: str, json: dict, **kwargs):
        return await self.session.patch(url, json=json, **kwargs)

    @ratelimit
    async def __delete(self, url: str, **kwargs):
        return await self.session.delete(url, **kwargs)

    async def get_who_am_i(self):
        """Get Clio User associated with current session token."""
        url = f"{CLIO_API_BASE_URL_US}/users/who_am_i"
        return await self.__get(url)

    async def upload_document(self, name, parent_id, parent_type, document, params=None, **kwargs):
        """Upload a new Document to Clio.

        Operations:
        1. POST a new Document to Clio
        2. PUT the Document content to S3
        3. PATCH the Document on Clio as `fully_uploaded`

        """
        post_url = f"{CLIO_API_BASE_URL_US}/documents"
        clio_document = await self.__post(
            post_url,
            params={"fields": "id,latest_document_version{uuid,put_url,put_headers}"},
            json={
                "data": {"name": name, "parent": {"id": parent_id, "type": parent_type}}
            },
        )

        put_url = clio_document["data"]["latest_document_version"]["put_url"]
        put_headers = clio_document["data"]["latest_document_version"]["put_headers"]

        headers_map = {}
        for header in put_headers:
            headers_map[header["name"]] = header["value"]

        with open(document, "rb") as f:
            # We don't want the authenticated session here, authn is
            # handled by the put_headers from Clio.
            async with aiohttp.ClientSession() as session:
                await session.put(put_url, headers=headers_map, data=f, timeout=300)

        patch_url = f"{CLIO_API_BASE_URL_US}/documents/{clio_document['data']['id']}"
        doc_params = {"fields": "id,name,latest_document_version{fully_uploaded}"}
        if params.get("fields"):
            doc_params["fields"] = doc_params["fields"] + "," + params.get("fields")
            del params["fields"]
        if params:
            doc_params = doc_params | params  # this merges the dicts

        patch_resp = await self.__patch(
            patch_url,
            params=doc_params,
            json={
                "data": {
                    "uuid": clio_document["data"]["latest_document_version"]["uuid"],
                    "fully_uploaded": True,
                }
            },
        )

        return patch_resp
