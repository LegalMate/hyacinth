"""async_session.py -- Async Session for Clio API."""

import logging
import functools
import asyncio
import aiohttp
import aiofiles
import aiofiles.os
import base64
import math

from authlib.integrations.httpx_client import AsyncOAuth2Client

CLIO_BASE_URL_US = "https://app.clio.com"
CLIO_BASE_URL_AU = "https://au.app.clio.com"
CLIO_BASE_URL_CA = "https://ca.app.clio.com"
CLIO_BASE_URL_EU = "https://eu.app.clio.com"

CLIO_API_BASE_URL_US = f"{CLIO_BASE_URL_US}/api/v4"
CLIO_API_BASE_URL_AU = f"{CLIO_BASE_URL_AU}/api/v4"
CLIO_API_BASE_URL_CA = f"{CLIO_BASE_URL_CA}/api/v4"
CLIO_API_BASE_URL_EU = f"{CLIO_BASE_URL_EU}/api/v4"

CLIO_API_TOKEN_ENDPOINT = "/oauth/token"  # nosec
CLIO_API_RATELIMIT_LIMIT_HEADER = "X-RateLimit-Limit"
CLIO_API_RATELIMIT_REMAINING_HEADER = "X-RateLimit-Remaining"
CLIO_API_RETRY_AFTER = "Retry-After"

PART_SIZE = 104857600  # 100 megabytes in bytes

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


def ratelimit(f):
    """Rate limit a function with Clio rate limits.
    See: https://docs.developers.clio.com/api-docs/rate-limits/
    """

    @functools.wraps(f)
    async def wrapper(self, *args, **kwargs):
        resp = await f(self, *args, **kwargs)

        if resp.status_code == 429 and self.ratelimit:
            retry_after = resp.headers.get(CLIO_API_RETRY_AFTER)
            log.info(f"Clio Rate Limit hit, Retry-After: {retry_after}s")
            await asyncio.sleep(int(retry_after))

            # Retry the request
            resp = await f(self, *args, **kwargs)

        # Sometimes we get a crazy json encoded rate limit error instead of the normal one
        if "application/json" in resp.headers.get("Content-Type", []):
            json = resp.json()

            if json.get("metadata"):
                if json.get("metadata").get("encodingDecoded") == "text/plain":
                    try:
                        data = base64.b64decode(json.get("data"))
                        data_string = data.decode("utf-8")

                        if "RateLimited" in data_string:
                            await asyncio.sleep(60)  # default to 60s
                            resp = await f(self, *args, **kwargs)
                    except Exception as e:
                        log.exception(e)
                        log.error(
                            f"Unable to decode b64 encoded string with response content {resp}"
                        )

        if self.raise_for_status:
            if resp.status_code > 299:
                content = await resp.text()
                log.warning(f"Non-200 status code: {content}")
            resp.raise_for_status()

        self.update_ratelimits(resp)

        # DELETE responses have no content
        if resp.status_code == 204:
            return None

        # If the response is JSON, return the parsed content
        if "application/json" in resp.headers.get("Content-Type"):
            return resp.json()
        else:
            return resp.text()

    return wrapper


class AsyncSession:
    """
    Session class for interacting with Clio Manage API.

    WARNING: enabling `ratelimit` will block the process
    asynchronously when API rate limits are hit.
    """

    def __init__(
        self,
        token,
        client_id,
        client_secret,
        region="US",
        ratelimit=False,
        raise_for_status=False,
        update_token=lambda *args, **kwargs: None,  # default update_token does nothing
        autopaginate=True,
    ):
        """Initialize Clio API HTTP Session."""
        # lowercase this region amirite
        region = region.lower()

        if region == "us":
            self.base_url = CLIO_BASE_URL_US
            self.api_base_url = CLIO_API_BASE_URL_US
        elif region == "ca":
            self.base_url = CLIO_BASE_URL_CA
            self.api_base_url = CLIO_API_BASE_URL_CA
        elif region == "au":
            self.base_url = CLIO_BASE_URL_AU
            self.api_base_url = CLIO_API_BASE_URL_AU
        elif region == "eu":
            self.base_url = CLIO_BASE_URL_EU
            self.api_base_url = CLIO_API_BASE_URL_EU
        else:
            log.warning(f"Invalid region supplied: {region}, defaulting to 'US'")
            log.info("Region must be one of ['US', 'CA', 'EU', 'AU']")
            self.base_url = CLIO_BASE_URL_US
            self.api_base_url = CLIO_API_BASE_URL_US

        self.token_endpoint = self.base_url + CLIO_API_TOKEN_ENDPOINT

        self.session = AsyncOAuth2Client(
            client_id=client_id,
            client_secret=client_secret,
            token=token,
            token_endpoint=self.token_endpoint,
            update_token=update_token,
        )

        self.ratelimit = ratelimit
        self.ratelimit_limit = math.inf
        self.ratelimit_remaining = math.inf
        self.raise_for_status = raise_for_status
        self.autopaginate = autopaginate

    def make_url(self, path):
        """Make a new URL for Clio API."""
        return f"{self.api_base_url}/{path}.json"

    def update_ratelimits(self, response):
        """Update rate limits values from response headers."""
        if self.ratelimit:
            self.ratelimit_limit = response.headers.get(CLIO_API_RATELIMIT_LIMIT_HEADER)
            self.ratelimit_remaining = response.headers.get(
                CLIO_API_RATELIMIT_REMAINING_HEADER
            )

    @ratelimit
    async def get_resource(self, url, params=None, **kwargs):
        """GET a Resource from Clio API."""
        # use unlimited cursor pagination
        # https://docs.developers.clio.com/api-docs/paging/#unlimited-cursor-pagination
        if not params:
            params = {}
        params["order"] = "id(asc)"
        return await self.session.get(url, params=params, **kwargs)

    @ratelimit
    async def post_resource(self, url, json, **kwargs):
        """POST a Resource to Clio API."""
        return await self.session.post(url, json=json, **kwargs)

    @ratelimit
    async def patch_resource(self, url, json, **kwargs):
        """PATCH a Resource on Clio API."""
        return await self.session.patch(url, json=json, **kwargs)

    @ratelimit
    async def delete_resource(self, url, **kwargs):
        """DELETE a Resource on Clio API."""
        return await self.session.delete(url, **kwargs)

    async def get_paginated_resource(self, url, **kwargs):
        """Get a paginated Resource from Clio API."""
        if not self.autopaginate:
            return await self.get_resource(url, **kwargs)
        else:
            return self.get_autopaginated_resource(url, **kwargs)

    async def get_autopaginated_resource(self, url, **kwargs):
        """GET a paginated Resource from Clio, following page links."""
        while url:
            resp = await self.get_resource(url, **kwargs)

            for d in resp["data"]:
                yield d

            paging = resp["meta"].get("paging")
            url = paging.get("next") if paging else None

    async def get_who_am_i(self, **kwargs):
        """GET currently authenticated User."""
        url = self.make_url("users/who_am_i")
        return await self.get_resource(url, **kwargs)

    async def upload_document(
        self,
        name,
        parent_id,
        parent_type,
        document,
        document_category_id=None,
        params=None,
        **kwargs,
    ):
        """Upload a new Document to Clio.

        Operations:
        1. POST a new Document to Clio
        2. PUT the Document content to S3
        3. PATCH the Document on Clio as `fully_uploaded`

        """
        post_url = self.make_url("documents")
        clio_document = await self.post_resource(
            post_url,
            params={"fields": "id,latest_document_version{uuid,put_url,put_headers}"},
            json={
                "data": {
                    "name": name,
                    "parent": {"id": parent_id, "type": parent_type},
                    "document_category": {"id": document_category_id},
                }
            },
        )

        put_url = clio_document["data"]["latest_document_version"]["put_url"]
        put_headers = clio_document["data"]["latest_document_version"]["put_headers"]

        headers_map = {"Content-Length": str(await aiofiles.os.path.getsize(document))}
        for header in put_headers:
            headers_map[header["name"]] = header["value"]

        async with aiofiles.open(document, "rb") as f:
            # We don't want the authenticated session here, authn is
            # handled by the put_headers from Clio.
            async with aiohttp.ClientSession() as session:
                await session.put(put_url, headers=headers_map, data=f, timeout=3600)

        patch_url = self.make_url(f"documents/{clio_document['data']['id']}")
        doc_params = {"fields": "id,name,latest_document_version{fully_uploaded}"}
        if params and params.get("fields"):
            doc_params["fields"] = doc_params["fields"] + "," + params.get("fields")
            del params["fields"]
        if params:
            doc_params = doc_params | params  # this merges the dicts

        patch_resp = await self.patch_resource(
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

    async def get_contact(self, id, **kwargs):
        """GET a Contact with provided ID."""
        url = self.make_url(f"contacts/{id}")
        return await self.get_resource(url, **kwargs)

    async def get_contacts(self, **kwargs):
        """GET a list of Contacts."""
        url = self.make_url("contacts")
        return await self.get_paginated_resource(url, **kwargs)

    async def post_contact(self, json, **kwargs):
        """POST a new Contact."""
        url = self.make_url("contacts")
        return await self.post_resource(url, json=json, **kwargs)

    async def patch_contact(self, id, json, **kwargs):
        """PATCH an existing Contact with provided ID."""
        url = self.make_url(f"contacts/{id}")
        return await self.patch_resource(url, json=json, **kwargs)

    async def delete_contact(self, id, **kwargs):
        """DELETE an existing Contact with provided ID."""
        url = self.make_url(f"contacts/{id}")
        return await self.delete_resource(url, **kwargs)

    async def post_trust_request(self, json, **kwargs):
        """POST a new Trust Request."""
        url = self.make_url("trust_requests")
        return await self.post_resource(url, json=json, **kwargs)

    async def get_reminders(self, **kwargs):
        """GET a list of Reminders."""
        url = self.make_url("reminders")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_reminder(self, id, **kwargs):
        """GET a Reminder with provided ID."""
        url = self.make_url(f"reminders/{id}")
        return await self.get_resource(url, **kwargs)

    async def post_reminder(self, json, **kwargs):
        """POST a new Reminder."""
        url = self.make_url("reminders")
        return await self.post_resource(url, json=json, **kwargs)

    async def patch_reminder(self, id, json, **kwargs):
        """PATCH an existing Reminder with provided ID."""
        url = self.make_url(f"reminders/{id}")
        return await self.patch_resource(url, json=json, **kwargs)

    async def delete_reminder(self, id, **kwargs):
        """DELETE an existing Reminder with provided ID."""
        url = self.make_url(f"reminders/{id}")
        return await self.delete_resource(url, **kwargs)

    async def get_tasks(self, **kwargs):
        """GET a list of Tasks."""
        url = self.make_url("tasks")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_task(self, id, **kwargs):
        """GET a Task with provided ID."""
        url = self.make_url(f"tasks/{id}")
        return await self.get_resource(url, **kwargs)

    async def post_task(self, json, **kwargs):
        """POST a new Task."""
        url = self.make_url("tasks")
        return await self.post_resource(url, json=json, **kwargs)

    async def patch_task(self, id, json, **kwargs):
        """PATCH an existing Task with provided ID."""
        url = self.make_url(f"tasks/{id}")
        return await self.patch_resource(url, json=json, **kwargs)

    async def delete_task(self, id, **kwargs):
        """DELETE an existing Task with provided ID."""
        url = self.make_url(f"tasks/{id}")
        return await self.delete_resource(url, **kwargs)

    async def post_task_list(self, json, **kwargs):
        """POST a new Task List."""
        url = self.make_url("task_lists")
        return await self.post_resource(url, json=json, **kwargs)

    async def get_task_template_lists(self, **kwargs):
        """GET a list of Task Template Lists."""
        url = self.make_url("task_template_lists")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_task_template_list(self, id, **kwargs):
        """GET a Task Template List with provided ID."""
        url = self.make_url(f"task_template_lists/{id}")
        return await self.get_resource(url, **kwargs)

    async def post_task_template_list(self, json, **kwargs):
        """POST a new Task Template List."""
        url = self.make_url("task_template_lists")
        return await self.post_resource(url, json=json, **kwargs)

    async def patch_task_template_list(self, id, json, **kwargs):
        """PATCH an existing Task Template List with provided ID."""
        url = self.make_url(f"task_template_lists/{id}")
        return await self.patch_resource(url, json=json, **kwargs)

    async def delete_task_template_list(self, id, **kwargs):
        """DELETE an existing Task Template List with provided ID."""
        url = self.make_url(f"task_template_lists/{id}")
        return await self.delete_resource(url, **kwargs)

    async def get_activity(self, id, **kwargs):
        """GET a single Activity with provided ID."""
        url = self.make_url(f"activities/{id}")
        return await self.get_resource(url, **kwargs)

    async def get_activities(self, **kwargs):
        """GET a list of Activities."""
        url = self.make_url("activities")
        return await self.get_paginated_resource(url, **kwargs)

    async def post_activity(self, json, **kwargs):
        """POST a new Activity."""
        url = self.make_url("activities")
        return await self.post_resource(url, json=json, **kwargs)

    async def patch_activity(self, id, json, **kwargs):
        """PATCH an existing Activity with provided ID."""
        url = self.make_url(f"activities/{id}")
        return await self.patch_resource(url, json=json, **kwargs)

    async def delete_activity(self, id, **kwargs):
        """DELETE an existing Activity with provided ID."""
        url = self.make_url(f"activities/{id}")
        return await self.delete_resource(url, **kwargs)
