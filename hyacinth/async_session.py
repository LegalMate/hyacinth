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

        # Handle S3 redirects before processing content
        if resp.is_redirect and "location" in resp.headers:
            s3_url = resp.headers["location"]
            if "s3." in s3_url:
                # Create a new client without auth headers for S3
                timeout = aiohttp.ClientTimeout(connect=10, total=self.download_timeout)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(s3_url) as resp:
                        return await resp.read()
            else:
                resp = await self.get_resource(s3_url)

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
                content = resp.content
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
            return resp.content

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
        download_timeout=600,
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
        self.download_timeout = download_timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.aclose()

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

    async def get_matter(self, id, **kwargs):
        """GET a Matter with provided ID."""
        url = self.make_url(f"matters/{id}")
        return await self.get_resource(url, **kwargs)

    async def get_matters(self, **kwargs):
        """GET a list of Matters."""
        url = self.make_url("matters")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_folder(self, id, **kwargs):
        """GET a Folder with provided ID."""
        url = self.make_url(f"folders/{id}")
        return await self.get_resource(url, **kwargs)

    async def get_folders(self, **kwargs):
        """GET a list of Folders."""
        url = self.make_url("folders")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_folders_content(self, **kwargs):
        """GET a list of Folder contents."""
        url = self.make_url("folders/list")
        return await self.get_paginated_resource(url, **kwargs)

    async def post_folder(
        self, name, parent_id, parent_type, document_category_id=None, **kwargs
    ):
        """POST a new Folder."""
        url = self.make_url("folders")
        return await self.post_resource(
            url,
            json={
                "data": {
                    "name": name,
                    "parent": {"id": parent_id, "type": parent_type},
                    "document_category": {"id": document_category_id},
                }
            },
            **kwargs,
        )

    async def delete_folder(self, id, **kwargs):
        """DELETE an existing Folder with provided ID."""
        url = self.make_url(f"folders/{id}")
        return await self.delete_resource(url, **kwargs)

    async def upload_multipart_document(
        self,
        name,
        parent_id,
        parent_type,
        document,
        progress_update,
        document_category_id=None,
    ):
        """Async fn to upload a Document to Clio via the multipart upload feature."""
        async with aiofiles.open(document, "rb") as f:
            file_size = await aiofiles.os.path.getsize(document)
            parts = []
            for i in range(0, file_size, PART_SIZE):
                start_offset = i
                end_offset = min(file_size, i + PART_SIZE)
                part = await f.read(end_offset - start_offset)
                parts.append((start_offset, end_offset, part))
                progress_update()
            # content_md5 = hashlib.md5(part).digest()  # nosec
            # content_md5_str = base64.b64encode(content_md5).decode('utf-8')

        multiparts = []
        for idx, part in enumerate(parts, start=1):
            multiparts.append(
                {
                    "part_number": idx,
                    "content_length": len(part[2]),
                    # "content_md5": content_md5_str,
                }
            )

        post_url = self.make_url("documents")

        clio_document = await self.post_resource(
            post_url,
            params={
                "fields": "id,latest_document_version{uuid,put_headers,multiparts}"
            },
            json={
                "data": {
                    "name": name,
                    "parent": {"id": parent_id, "type": parent_type},
                    "document_category": {"id": document_category_id},
                    "multiparts": multiparts,
                }
            },
        )

        for part in clio_document["data"]["latest_document_version"]["multiparts"]:
            put_url = part["put_url"]
            put_headers = part["put_headers"]
            headers_map = {}
            for header in put_headers:
                headers_map[header["name"]] = header["value"]

            part_number = part["part_number"]
            data_part = parts[part_number - 1][2]  # 'parts' is a list of tuples
            async with aiohttp.ClientSession() as session:
                response = await session.put(
                    put_url, headers=headers_map, data=data_part, timeout=300
                )
                log.info(response)
                progress_update()

        patch_url = self.make_url(f"documents/{clio_document['data']['id']}")
        patch_resp = await self.patch_resource(
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

    async def post_webhook(self, url, model, events, fields=None, expires_at=None):
        """Post a Webhook to Clio."""
        post_url = self.make_url("webhooks")
        model_fields = "id"
        if fields:
            model_fields += "," + fields
        return await self.post_resource(
            post_url,
            json={
                "data": {
                    "fields": model_fields,
                    "events": events,
                    "model": model,
                    "url": url,
                    "expires_at": expires_at,
                },
            },
            params={"fields": "id,shared_secret,status,expires_at"},
        )

    async def update_webhook(self, id, json, **kwargs):
        """PATCH an existing Webhook with provided ID."""
        url = self.make_url(f"webhooks/{id}")
        return await self.patch_resource(url, json=json, **kwargs)

    async def delete_webhook(self, id, **kwargs):
        """DELETE an existing Webhook with provided ID."""
        url = self.make_url(f"webhooks/{id}")
        return await self.delete_resource(url, **kwargs)

    async def get_webhook(self, id, **kwargs):
        """GET a single Webhook with provided ID."""
        url = self.make_url(f"webhooks/{id}")
        return await self.get_resource(url, **kwargs)

    async def get_webhooks(self, **kwargs):
        """GET a list of all webhooks from Clio."""
        url = self.make_url("webhooks")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_document_templates(self, **kwargs):
        """GET a list of Document Templates."""
        url = self.make_url("document_templates")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_document_automation(self, document_automation_id, **kwargs):
        """GET a Document Automation."""
        url = self.make_url(f"document_automations/{document_automation_id}")
        return await self.get_resource(url, **kwargs)

    async def post_document_automation(self, json, **kwargs):
        """POST a new Document Automation."""
        url = self.make_url("document_automations")
        return await self.post_resource(url, json=json, **kwargs)

    async def post_matter(self, json, **kwargs):
        """POST a new Matter."""
        url = self.make_url("matters")
        return await self.post_resource(url, json=json, **kwargs)

    async def patch_matter(self, id, json, **kwargs):
        """PATCH a Matter with provided ID with provided JSON."""
        url = self.make_url(f"matters/{id}")
        return await self.patch_resource(url, json=json, **kwargs)

    async def get_matter_stages(self, **kwargs):
        """GET a list of Matter Stages."""
        url = self.make_url("matter_stages")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_matter_client(self, matter_id, **kwargs):
        """GET a Matter's Client with provided Matter ID."""
        url = self.make_url(f"matters/{matter_id}/client")
        return await self.get_resource(url, **kwargs)

    async def get_calendars(self, **kwargs):
        """GET Calendars."""
        url = self.make_url("calendars")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_user(self, id, **kwargs):
        """GET a single User with provided ID."""
        url = self.make_url(f"users/{id}")
        return await self.get_resource(url, **kwargs)

    async def get_users(self, **kwargs):
        """GET a list of Users."""
        url = self.make_url("users")
        return await self.get_paginated_resource(url, **kwargs)

    async def post_calendar_entry(self, json, **kwargs):
        """POST a Calendar Entry."""
        url = self.make_url("calendar_entries")
        return await self.post_resource(url, json, **kwargs)

    async def patch_calendar_entry(self, id, json, **kwargs):
        """PATCH a Calendar Entry."""
        url = self.make_url(f"calendar_entries/{id}")
        return await self.patch_resource(url, json=json, **kwargs)

    async def get_calendar_entries(self, **kwargs):
        """GET a list of Calendar Entries."""
        url = self.make_url("calendar_entries")
        return await self.get_paginated_resource(url, **kwargs)

    async def post_note(self, json, **kwargs):
        """POST a new Note."""
        url = self.make_url("notes")
        return await self.post_resource(url, json=json, **kwargs)

    async def get_custom_fields(self, **kwargs):
        """GET a list of Cusom Fields."""
        url = self.make_url("custom_fields")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_custom_field_sets(self, **kwargs):
        """GET a list of Cusom Fields Sets."""
        url = self.make_url("custom_field_sets")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_custom_field_set(self, id, **kwargs):
        """GET a Custom Field Set."""
        url = self.make_url(f"custom_field_sets/{id}")
        return await self.get_resource(url, **kwargs)

    async def download_document(self, id, **kwargs):
        """Download a Document with provided ID."""
        url = self.make_url(f"documents/{id}/download")
        return await self.get_resource(url, **kwargs)

    async def get_document(self, id, **kwargs):
        """GET a Document with provided ID."""
        url = self.make_url(f"documents/{id}")
        return await self.get_resource(url, **kwargs)

    async def delete_document(self, id, **kwargs):
        """DELETE an existing Document with provided ID."""
        url = self.make_url(f"documents/{id}")
        return await self.delete_resource(url, **kwargs)

    async def get_documents(self, **kwargs):
        """GET a list of Documents."""
        url = self.make_url("documents")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_matter_finances(self, id, **kwargs):
        """GET a Matter's Finances with provided ID."""
        url = self.make_url(f"matter_finances/{id}")
        return await self.get_resource(url, **kwargs)

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

    async def get_activity_description(self, id, **kwargs):
        """GET a single Activity Description with provided ID."""
        url = self.make_url(f"activity_descriptions/{id}")
        return await self.get_resource(url, **kwargs)

    async def get_activity_descriptions(self, **kwargs):
        """GET a list of Activity Descriptions."""
        url = self.make_url("activity_descriptions")
        return await self.get_paginated_resource(url, **kwargs)

    async def post_activity_description(self, json, **kwargs):
        """POST a new Activity Description."""
        url = self.make_url("activity_descriptions")
        return await self.post_resource(url, json=json, **kwargs)

    async def get_bills(self, **kwargs):
        """GET a list of Bills."""
        url = self.make_url("bills")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_bill(self, id, **kwargs):
        """GET a single Bill with provided ID."""
        url = self.make_url(f"bills/{id}")
        return await self.get_resource(url, **kwargs)

    async def patch_bill(self, id, json, **kwargs):
        """PATCH an existing Bill with provided ID."""
        url = self.make_url(f"bills/{id}")
        return await self.patch_resource(url, json=json, **kwargs)

    async def delete_bill(self, id, **kwargs):
        """DELETE an existing Bill with provided ID."""
        url = self.make_url(f"bills/{id}")
        return await self.delete_resource(url, **kwargs)

    async def get_line_items(self, **kwargs):
        """GET a list of Line Items."""
        url = self.make_url("line_items")
        return await self.get_paginated_resource(url, **kwargs)

    async def patch_line_item(self, id, json, **kwargs):
        """PATCH an existing line item with provided ID of line item."""
        url = self.make_url(f"line_items/{id}")
        return await self.patch_resource(url, json=json, **kwargs)

    async def post_trust_request(self, json, **kwargs):
        """POST a new Trust Request."""
        url = self.make_url("trust_requests")
        return await self.post_resource(url, json=json, **kwargs)

    async def get_custom_actions(self, **kwargs):
        """GET a list of Custom Actions."""
        url = self.make_url("custom_actions")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_custom_action(self, id, **kwargs):
        """GET a single Custom Action with provided ID."""
        url = self.make_url(f"custom_actions/{id}")
        return self.get_resource(url, **kwargs)

    async def post_custom_action(self, json, **kwargs):
        """POST a new Custom Action."""
        url = self.make_url("custom_actions")
        return await self.post_resource(url, json=json, **kwargs)

    async def patch_custom_action(self, id, json, **kwargs):
        """PATCH an existing Custom Action with provided ID."""
        url = self.make_url(f"custom_actions/{id}")
        return await self.patch_resource(url, json=json, **kwargs)

    async def delete_custom_action(self, id, **kwargs):
        """DELETE an existing Custom Action with provided ID."""
        url = self.make_url(f"custom_actions/{id}")
        return await self.delete_resource(url, **kwargs)

    async def verify_custom_action(self, subject_url, custom_action_nonce, **kwargs):
        """Verify a Custom Action."""
        url = self.base_url + subject_url
        params = kwargs.get("params", {})
        params.update({"custom_action_nonce": custom_action_nonce})
        kwargs["params"] = params
        return await self.get_resource(
            url,
            **kwargs,
        )

    async def get_relationships(self, **kwargs):
        """GET a list of Relationships."""
        url = self.make_url("relationships")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_relationship(self, id, **kwargs):
        """GET a single Relationship with provided ID."""
        url = self.make_url(f"relationships/{id}")
        return await self.get_resource(url, **kwargs)

    async def post_relationship(self, json, **kwargs):
        """POST a new Relationship."""
        url = self.make_url("relationships")
        return await self.post_resource(url, json=json, **kwargs)

    async def patch_relationship(self, id, json, **kwargs):
        """PATCH an existing Relationship with provided ID."""
        url = self.make_url(f"relationships/{id}")
        return await self.patch_resource(url, json=json, **kwargs)

    async def delete_relationship(self, id, **kwargs):
        """DELETE an existing Relationship with provided ID."""
        url = self.make_url(f"relationships/{id}")
        return await self.delete_resource(url, **kwargs)

    async def get_document_categories(self, **kwargs):
        """GET a list of Document Categories."""
        url = self.make_url("document_categories")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_document_category(self, id, **kwargs):
        """GET a single Document Category with provided ID."""
        url = self.make_url(f"document_categories/{id}")
        return await self.get_resource(url, **kwargs)

    async def patch_document_category(self, id, json, **kwargs):
        """PATCH an existing Document Category with provided ID."""
        url = self.make_url(f"document_categories/{id}")
        return await self.patch_resource(url, json=json, **kwargs)

    async def post_document_category(self, json, **kwargs):
        """POST a new Document Category."""
        url = self.make_url("document_categories")
        return await self.post_resource(url, json=json, **kwargs)

    async def delete_document_category(self, id, **kwargs):
        """DELETE an existing Document Category with provided ID."""
        url = self.make_url(f"document_categories/{id}")
        return await self.delete_resource(url, **kwargs)

    async def get_practice_areas(self, **kwargs):
        """GET a list of Practice Areas."""
        url = self.make_url("practice_areas")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_practice_area(self, id, **kwargs):
        """GET a single Practice Area with provided ID."""
        url = self.make_url(f"practice_areas/{id}")
        return await self.get_resource(url, **kwargs)

    async def post_practice_area(self, json, **kwargs):
        """POST a new Practice Area."""
        url = self.make_url("practice_areas")
        return await self.post_resource(url, json=json, **kwargs)

    async def patch_practice_area(self, id, json, **kwargs):
        """PATCH an existing Practice Area with provided ID."""
        url = self.make_url(f"practice_areas/{id}")
        return await self.patch_resource(url, json=json, **kwargs)

    async def delete_practice_area(self, id, **kwargs):
        """DELETE an existing Practice Area with provided ID."""
        url = self.make_url(f"practice_areas/{id}")
        return await self.delete_resource(url, **kwargs)

    async def get_communications(self, **kwargs):
        """GET a list of Communications."""
        url = self.make_url("communications")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_communication(self, id, **kwargs):
        """GET a single Communication with provided ID."""
        url = self.make_url(f"communications/{id}")
        return await self.get_resource(url, **kwargs)

    async def post_communication(self, json, **kwargs):
        """POST a new Communication."""
        url = self.make_url("communications")
        return await self.post_resource(url, json=json, **kwargs)

    async def patch_communication(self, id, json, **kwargs):
        """PATCH an existing Communication with provided ID."""
        url = self.make_url(f"communications/{id}")
        return await self.patch_resource(url, json=json, **kwargs)

    async def delete_communication(self, id, **kwargs):
        """DELETE an existing Communication with provided ID."""
        url = self.make_url(f"communications/{id}")
        return await self.delete_resource(url, **kwargs)

    async def get_reminders(self, **kwargs):
        """GET a list of Reminders."""
        url = self.make_url("reminders")
        return await self.get_paginated_resource(url, **kwargs)

    async def get_reminder(self, id, **kwargs):
        """GET a single Reminder with provided ID."""
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
