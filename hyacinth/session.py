"""hyacinth/session.py -- Sychronous HTTP Session for Clio HTTP API."""
import functools
import logging
import math
import requests
import time
import os
import aiohttp

from authlib.integrations.requests_client import OAuth2Session

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
    """Provide blocking rate limits to wrapped fn."""

    @functools.wraps(f)
    def wrapper(self, *args, **kwargs):
        resp = f(self, *args, **kwargs)

        if resp.status_code == 429 and self.ratelimit:
            retry_after = resp.headers.get(CLIO_API_RETRY_AFTER)
            log.info(f"Clio Rate Limit hit, Retry-After: {retry_after}s")
            time.sleep(int(retry_after))

            # Retry the request
            resp = f(self, *args, **kwargs)

        elif self.raise_for_status:
            resp.raise_for_status()

        self.update_ratelimits(resp)

        # DELETE responses have no content
        if not resp.content:
            return None

        # If the response is not JSON, return the content
        if "application/json" in resp.headers.get("Content-Type"):
            return resp.json()
        else:
            return resp.content

    return wrapper


class Session:
    """
    Session class for interacting with Clio Manage API.

    WARNING: enabling `ratelimit` will block the process
    synchronously when API rate limits are hit. Partial support
    for async hyacinth is provided by hyacinth/async_session.py".
    """

    def __init__(
            self,
            token,
            client_id,
            client_secret,
            region="US",
            ratelimit=False,
            raise_for_status=False,
            update_token=lambda *args: None,  # default update_token does nothing
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

        self.session = OAuth2Session(
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
    def get_resource(self, url, params=None, **kwargs):
        """GET a Resource from Clio API."""
        # use unlimited cursor pagination
        # https://docs.developers.clio.com/api-docs/paging/#unlimited-cursor-pagination
        if not params:
            params = {}
        params["order"] = "id(asc)"
        return self.session.get(url, params=params, **kwargs)

    @ratelimit
    def post_resource(self, url, json, **kwargs):
        """POST a Resource to Clio API."""
        return self.session.post(url, json=json, **kwargs)

    @ratelimit
    def patch_resource(self, url, json, **kwargs):
        """PATCH a Resource on Clio API."""
        return self.session.patch(url, json=json, **kwargs)

    @ratelimit
    def delete_resource(self, url, **kwargs):
        """DELETE a Resource on Clio API."""
        return self.session.delete(url, **kwargs)

    def get_paginated_resource(self, url, **kwargs):
        """Get a paginated Resource from Clio API."""
        if not self.autopaginate:
            return self.get_resource(url, **kwargs)
        else:
            return self.get_autopaginated_resource(url, **kwargs)

    def get_autopaginated_resource(self, url, **kwargs):
        """GET a paginated Resource from Clio API, following page links."""
        resp = self.get_resource(url, **kwargs)

        for d in resp["data"]:
            yield d

        paging = resp["meta"].get("paging")
        if paging:
            if paging.get("next"):
                next_url = paging["next"]
            else:
                # no more next page, break
                next_url = None
        else:
            next_url = None

        while next_url:
            yield from self.get_paginated_resource(next_url, **kwargs)

    def get_calendars(self, **kwargs):
        """GET Calendars."""
        url = self.make_url("calendars")
        return self.get_paginated_resource(url, **kwargs)

    def post_calendar_entry(self, json, **kwargs):
        """POST a Calendar Entry."""
        url = self.make_url("calendar_entries")
        return self.post_resource(url, json, **kwargs)

    def patch_calendar_entry(self, id, json, **kwargs):
        """PATCH a Calendar Entry."""
        url = self.make_url(f"calendar_entries/{id}")
        return self.patch_resource(url, json=json, **kwargs)

    def get_calendar_entries(self, **kwargs):
        """GET a list of Calendar Entries."""
        url = self.make_url("calendar_entries")
        return self.get_paginated_resource(url, **kwargs)

    def get_calendar_entry(self, calendar_entry_id, **kwargs):
        """GET a Calendar Entry with provided ID."""
        url = self.make_url(f"calendar_entries/{calendar_entry_id}")
        return self.get_resource(url, **kwargs)

    def get_contact(self, id, **kwargs):
        """GET a Contact with provided ID."""
        url = self.make_url(f"contacts/{id}")
        return self.get_resource(url, **kwargs)

    def get_contacts(self, **kwargs):
        """GET a list of Contacts."""
        url = self.make_url("contacts")
        return self.get_paginated_resource(url, **kwargs)

    def post_contact(self, json, **kwargs):
        """POST a new Contact."""
        url = Session.make_url("contacts")
        return self.post_resource(url, json=json, **kwargs)

    def patch_contact(self, id, json, **kwargs):
        """PATCH an existing Contact with provided ID."""
        url = Session.make_url(f"contacts/{id}")
        return self.patch_resource(url, json=json, **kwargs)

    def delete_contact(self, id, **kwargs):
        """DELETE an existing Contact with provided ID."""
        url = Session.make_url(f"contacts/{id}")
        return self.delete_resource(url, **kwargs)

    def get_custom_fields(self, **kwargs):
        """GET a list of Cusom Fields."""
        url = self.make_url("custom_fields")
        return self.get_paginated_resource(url, **kwargs)

    def get_who_am_i(self, **kwargs):
        """GET currently authenticated User."""
        url = self.make_url("users/who_am_i")
        return self.get_resource(url, **kwargs)

    def get_user(self, id, **kwargs):
        """GET a single Userwith provided ID."""
        url = self.make_url(f"users/{id}")
        return self.get_resource(url, **kwargs)

    def get_users(self, **kwargs):
        """GET a list of Users."""
        url = self.make_url("users")
        return self.get_paginated_resource(url, **kwargs)

    def get_document(self, id, **kwargs):
        """GET a Document with provided ID."""
        url = self.make_url(f"documents/{id}")
        return self.get_resource(url, **kwargs)

    def get_documents(self, **kwargs):
        """GET a list of Documents."""
        url = self.make_url("documents")
        return self.get_paginated_resource(url, **kwargs)

    def download_document(self, id, **kwargs):
        """Download a Document with provided ID."""
        url = self.make_url(f"documents/{id}/download")
        return self.get_resource(url, **kwargs)

    def delete_document(self, id, **kwargs):
        """DELETE an existing Document with provided ID."""
        url = self.make_url(f"documents/{id}")
        return self.delete_resource(url, **kwargs)

    def patch_documentcategory(self, id, json, **kwargs):
        """PATCH an existing Document Category."""
        url = self.make_url(f"document_categories/{id}")
        return self.patch_resource(url, json=json, **kwargs)

    def patch_document(self, id, json, **kwargs):
        """PATCH an existing document with provided ID."""
        url = self.make_url(f"documents/{id}")
        return self.patch_resource(url, json=json, **kwargs)

    def get_matter(self, id, **kwargs):
        """GET a Matter with provided ID."""
        url = self.make_url(f"matters/{id}")
        return self.get_resource(url, **kwargs)

    def patch_matter(self, id, json, **kwargs):
        """PATCH a Matter with provided ID with provided JSON."""
        url = self.make_url(f"matters/{id}")
        return self.patch_resource(url, json=json, **kwargs)

    def post_note(self, json, **kwargs):
        """POST a new Note."""
        url = self.make_url("notes")
        return self.post_resource(url, json=json, **kwargs)

    def post_task(self, json, **kwargs):
        """POST a new Task."""
        url = self.make_url("tasks")
        return self.post_resource(url, json=json, **kwargs)

    def get_matters(self, **kwargs):
        """GET a list of Matters."""
        url = self.make_url("matters")
        return self.get_paginated_resource(url, **kwargs)

    def get_folder(self, id, **kwargs):
        """GET a Folder with provided ID."""
        url = self.make_url(f"folders/{id}")
        return self.get_resource(url, **kwargs)

    def get_folders(self, **kwargs):
        """GET a list of Folders."""
        url = self.make_url("folders")
        return self.get_paginated_resource(url, **kwargs)

    def get_folders_content(self, **kwargs):
        """GET a list of Folder contents."""
        url = self.make_url("folders/list")
        return self.get_paginated_resource(url, **kwargs)

    def post_folder(self, name, parent_id, parent_type, **kwargs):
        """POST a new Folder."""
        url = self.make_url("folders")
        return self.post_resource(
            url,
            json={
                "data": {"name": name, "parent": {"id": parent_id, "type": parent_type}}
            },
            **kwargs,
        )

    def delete_folder(self, id, **kwargs):
        """DELETE an existing Folder with provided ID."""
        url = self.make_url(f"folders/{id}")
        return self.delete_resource(url, **kwargs)

    def upload_document(
            self, name, parent_id, parent_type, document, document_category_id=None, progress_update=lambda *args: None
    ):
        """POST a new Document, PUT the data, and PATCH Document as fully_uploaded."""
        with open(document, "rb") as f:
            post_url = self.make_url("documents")
            clio_document = self.post_resource(
                post_url,
                params={
                    "fields": "id,latest_document_version{uuid,put_url,put_headers}"
                },
                json={
                    "data": {
                        "name": name,
                        "parent": {"id": parent_id, "type": parent_type},
                        "document_category": {"id": document_category_id},
                    }
                },
            )

            put_url = clio_document["data"]["latest_document_version"]["put_url"]
            put_headers = clio_document["data"]["latest_document_version"][
                "put_headers"
            ]

            headers_map = {}
            for header in put_headers:
                headers_map[header["name"]] = header["value"]

            # We actually DON'T want to use the authenticated client here
            requests.put(put_url, headers=headers_map, data=f, timeout=600)

            patch_url = self.make_url(f"documents/{clio_document['data']['id']}")
            patch_resp = self.patch_resource(
                patch_url,
                params={"fields": "id,name,latest_document_version{fully_uploaded}"},
                json={
                    "data": {
                        "uuid": clio_document["data"]["latest_document_version"][
                            "uuid"
                        ],
                        "fully_uploaded": True,
                    }
                },
            )

            return patch_resp

    async def upload_document_async(
            self, name, parent_id, parent_type, document, document_category_id=None, progress_update=lambda *args: None
    ):
        """POST a new Document, PUT the data, and PATCH Document as fully_uploaded."""
        with open(document, "rb") as f:
            post_url = self.make_url("documents")
            clio_document = self.post_resource(
                post_url,
                params={
                    "fields": "id,latest_document_version{uuid,put_url,put_headers}"
                },
                json={
                    "data": {
                        "name": name,
                        "parent": {"id": parent_id, "type": parent_type},
                        "document_category": {"id": document_category_id},
                    }
                },
            )

            put_url = clio_document["data"]["latest_document_version"]["put_url"]
            put_headers = clio_document["data"]["latest_document_version"][
                "put_headers"
            ]

            headers_map = {}
            for header in put_headers:
                headers_map[header["name"]] = header["value"]

            # We actually DON'T want to use the authenticated client here
            async with aiohttp.ClientSession() as session:
                response = await session.put(
                    put_url, headers=headers_map, data=f, timeout=300
                )
                log.info(response)
                progress_update()

            patch_url = self.make_url(f"documents/{clio_document['data']['id']}")
            patch_resp = self.patch_resource(
                patch_url,
                params={"fields": "id,name,latest_document_version{fully_uploaded}"},
                json={
                    "data": {
                        "uuid": clio_document["data"]["latest_document_version"][
                            "uuid"
                        ],
                        "fully_uploaded": True,
                    }
                },
            )

            return patch_resp

    async def upload_multipart_document(
            self, name, parent_id, parent_type, document, progress_update, document_category_id=None
    ):
        """Async fn to upload a Document to Clio via the multipart upload feature."""
        with open(document, "rb") as f:
            file_size = os.path.getsize(document)
            parts = []
            for i in range(0, file_size, PART_SIZE):
                start_offset = i
                end_offset = min(file_size, i + PART_SIZE)
                part = f.read(end_offset - start_offset)
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

        clio_document = self.post_resource(
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
        patch_resp = self.patch_resource(
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

    def post_webhook(self, url, model, events, fields=None, expires_at=None):
        """Post a Webhook to Clio."""
        post_url = self.make_url("webhooks")
        model_fields = "id"
        if fields:
            model_fields += "," + fields
        return self.post_resource(
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

    def update_webhook(self, id, json, **kwargs):
        """PATCH an existing Webhook with provided ID."""
        url = self.make_url(f"webhooks/{id}")
        return self.patch_resource(url, json=json, **kwargs)

    def delete_webhook(self, id, **kwargs):
        """DELETE an existing Webhook with provided ID."""
        url = self.make_url(f"webhooks/{id}")
        return self.delete_resource(url, **kwargs)

    def get_webhook(self, id, **kwargs):
        """GET a single Webhook with provided ID."""
        url = self.make_url(f"webhooks/{id}")
        return self.get_resource(url, **kwargs)

    def get_webhooks(self, **kwargs):
        """GET a list of all webhooks from Clio."""
        url = self.make_url("webhooks")
        return self.get_paginated_resource(url, **kwargs)

    def get_document_templates(self, **kwargs):
        """GET a list of Document Templates."""
        url = self.make_url("document_templates")
        return self.get_paginated_resource(url, **kwargs)

    def post_document_automation(self, json, **kwargs):
        """POST a new Document Automation."""
        url = self.make_url("document_automations")
        return self.post_resource(url, json=json, **kwargs)

    def post_matter(self, json, **kwargs):
        """POST a new Matter."""
        url = self.make_url("matters")
        return self.post_resource(url, json=json, **kwargs)

    def get_activity(self, id, **kwargs):
        """GET a single Activity with provided ID."""
        url = self.make_url(f"activities/{id}")
        return self.get_resource(url, **kwargs)

    def get_activities(self, **kwargs):
        """GET a list of Activities."""
        url = self.make_url("activities")
        return self.get_paginated_resource(url, **kwargs)

    def post_activity(self, json, **kwargs):
        """POST a new Activity."""
        url = self.make_url("activities")
        return self.post_resource(url, json=json, **kwargs)

    def patch_activity(self, id, json, **kwargs):
        """PATCH an existing Activity with provided ID."""
        url = self.make_url(f"activities/{id}")
        return self.patch_resource(url, json=json, **kwargs)

    def delete_activity(self, id, **kwargs):
        """DELETE an existing Activity with provided ID."""
        url = self.make_url(f"activities/{id}")
        return self.delete_resource(url, **kwargs)

    def get_activity_description(self, id, **kwargs):
        """GET a single Activity Description with provided ID."""
        url = self.make_url(f"activity_descriptions/{id}")
        return self.get_resource(url, **kwargs)

    def get_activity_descriptions(self, **kwargs):
        """GET a list of Activity Descriptions."""
        url = self.make_url("activity_descriptions")
        return self.get_paginated_resource(url, **kwargs)

    def post_activity_description(self, json, **kwargs):
        """POST a new Activity Description."""
        url = self.make_url("activity_descriptions")
        return self.post_resource(url, json=json, **kwargs)

    def get_bills(self, **kwargs):
        """GET a list of Bills."""
        url = self.make_url("bills")
        return self.get_paginated_resource(url, **kwargs)

    def get_bill(self, id, **kwargs):
        """GET a single Bill with provided ID."""
        url = self.make_url(f"bills/{id}")
        return self.get_resource(url, **kwargs)

    def patch_bill(self, id, json, **kwargs):
        """PATCH an existing Bill with provided ID."""
        url = self.make_url(f"bills/{id}")
        return self.patch_resource(url, json=json, **kwargs)

    def delete_bill(self, id, **kwargs):
        """DELETE an existing Bill with provided ID."""
        url = self.make_url(f"bills/{id}")
        return self.delete_resource(url, **kwargs)

    def get_line_items(self, **kwargs):
        """GET a list of Line Items."""
        url = self.make_url("line_items")
        return self.get_paginated_resource(url, **kwargs)

    def patch_line_item(self, id, json, **kwargs):
        """PATCH an existing line item with provided ID of line item."""
        url = self.make_url(f"line_items/{id}")
        return self.patch_resource(url, json=json, **kwargs)

    def get_custom_actions(self, **kwargs):
        """GET a list of Custom Actions."""
        url = self.make_url("custom_actions")
        return self.get_paginated_resource(url, **kwargs)

    def get_custom_action(self, id, **kwargs):
        """GET a single Custom Action with provided ID."""
        url = self.make_url(f"custom_actions/{id}")
        return self.get_resource(url, **kwargs)

    def post_custom_action(self, json, **kwargs):
        """POST a new Custom Action."""
        url = self.make_url("custom_actions")
        return self.post_resource(url, json=json, **kwargs)

    def patch_custom_action(self, id, json, **kwargs):
        """PATCH an existing Custom Action with provided ID."""
        url = self.make_url(f"custom_actions/{id}")
        return self.patch_resource(url, json=json, **kwargs)

    def delete_custom_action(self, id, **kwargs):
        """DELETE an existing Custom Action with provided ID."""
        url = self.make_url(f"custom_actions/{id}")
        return self.delete_resource(url, **kwargs)

    def verify_custom_action(self, subject_url, custom_action_nonce, **kwargs):
        """Verify a Custom Action."""
        url = self.base_url + subject_url
        params = kwargs.get("params", {})
        params.update({"custom_action_nonce": custom_action_nonce})
        kwargs["params"] = params
        return self.get_resource(
            url,
            **kwargs,
        )

    def get_relationships(self, **kwargs):
        """GET a list of Relationships."""
        url = self.make_url("relationships")
        return self.get_paginated_resource(url, **kwargs)

    def get_relationship(self, id, **kwargs):
        """GET a single Relationship with provided ID."""
        url = self.make_url(f"relationships/{id}")
        return self.get_resource(url, **kwargs)

    def post_relationship(self, json, **kwargs):
        """POST a new Relationship."""
        url = self.make_url("relationships")
        return self.post_resource(url, json=json, **kwargs)

    def patch_relationship(self, id, json, **kwargs):
        """PATCH an existing Relationship with provided ID."""
        url = self.make_url(f"relationships/{id}")
        return self.patch_resource(url, json=json, **kwargs)

    def delete_relationship(self, id, **kwargs):
        """DELETE an existing Relationship with provided ID."""
        url = self.make_url(f"relationships/{id}")
        return self.delete_resource(url, **kwargs)

    def post_document_category(self, json, **kwargs):
        """POST a new Document Category."""
        url = self.make_url("document_categories")
        return self.post_resource(url, json=json, **kwargs)
