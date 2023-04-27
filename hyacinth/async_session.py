"""async_session.py -- Async Session for Clio API."""
import logging
import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
import aiofiles


CLIO_API_BASE_URL_US = "https://app.clio.com/api/v4"
CLIO_API_TOKEN_ENDPOINT = "https://app.clio.com/oauth/token"  # nosec
CLIO_API_RATELIMIT_LIMIT_HEADER = "X-RateLimit-Limit"
CLIO_API_RATELIMIT_REMAINING_HEADER = "X-RateLimit-Remaining"
CLIO_API_RETRY_AFTER = "Retry-After"


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class AsyncSession:
    """Class for interacting with Clio Manage API using async/await."""

    def __init__(
        self,
        token,
        client_id,
        client_secret,
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

    async def get_who_am_i(self):
        """Get Clio User associated with current session token."""
        url = f"{CLIO_API_BASE_URL_US}/users/who_am_i"
        res = await self.session.get(url)
        return res.json()

    async def upload_document(self, name, parent_id, parent_type, document):
        """Upload a new Document to Clio."""
        post_url = f"{CLIO_API_BASE_URL_US}/documents"
        clio_document_res = await self.session.post(
            post_url,
            params={"fields": "id,latest_document_version{uuid,put_url,put_headers}"},
            json={
                "data": {"name": name, "parent": {"id": parent_id, "type": parent_type}}
            },
        )
        clio_document = clio_document_res.json()

        put_url = clio_document["data"]["latest_document_version"]["put_url"]
        put_headers = clio_document["data"]["latest_document_version"]["put_headers"]

        headers_map = {}
        for header in put_headers:
            headers_map[header["name"]] = header["value"]

        async with (
                # We actually DON'T want to use the authenticated client here
                httpx.AsyncClient() as client,
                # aiofiles is an async interface for file io
                aiofiles.open(document, mode="rb") as f
        ):
            # httpx wants us to provide an asynchronous byte generator as data
            async def data_generator():
                yield await f.read()

            await client.put(put_url, headers=headers_map, data=data_generator())

        patch_url = f"{CLIO_API_BASE_URL_US}/documents/{clio_document['data']['id']}"
        patch_resp = await self.session.patch(
            patch_url,
            params={"fields": "id,name,latest_document_version{fully_uploaded}"},
            json={
                "data": {
                    "uuid": clio_document["data"]["latest_document_version"]["uuid"],
                    "fully_uploaded": True,
                }
            },
        )

        return patch_resp
