import functools
import logging
import math
import requests
import time
from authlib.integrations.requests_client import OAuth2Session

CLIO_API_BASE_URL_US = "https://app.clio.com/api/v4"
CLIO_API_RATELIMIT_LIMIT_HEADER = "X-RateLimit-Limit"
CLIO_API_RATELIMIT_REMAINING_HEADER = "X-RateLimit-Remaining"
CLIO_API_RETRY_AFTER = "Retry-After"


def ratelimit(f):
    def wrapper(self, *args):
        resp = f(self, *args)

        if resp.status_code == 429 and self.ratelimit:
            retry_after = resp.headers.get(CLIO_API_RETRY_AFTER)
            logging.info(f"Clio Rate Limit hit, Retry-After: {retry_after}s")
            time.sleep(int(retry_after))

            # Retry the request
            resp = f(self, *args)

        self.update_ratelimits(resp)
        return resp.json()
    return wrapper


class Session:
    """Session class for interacting with Clio Manage API.

    WARNING: enabling `ratelimit` will block the process synchronously
    when API rate limits are hit. Support for async hyacinth is coming
    soon.

    """

    def __init__(self, token, client_id, client_secret, ratelimit=False):
        """Initialize Session with optional ratelimits."""
        self.session = OAuth2Session(client_id=client_id,
                                     client_secret=client_secret,
                                     token=token)

        self.ratelimit = ratelimit
        self.ratelimit_limit = math.inf
        self.ratelimit_remaining = math.inf

    @staticmethod
    def __make_url(path):
        return f"{CLIO_API_BASE_URL_US}/{path}.json"

    def update_ratelimits(self, response):
        if self.ratelimit:
            self.ratelimit_limit = response.headers.get(
                CLIO_API_RATELIMIT_LIMIT_HEADER
            )
            self.ratelimit_remaining = response.headers.get(
                CLIO_API_RATELIMIT_REMAINING_HEADER
            )

    @ratelimit
    def __get_resource(self, url, **kwargs):
        return self.session.get(url, params=kwargs)

    @ratelimit
    def __post_resource(self, url, json, **kwargs):
        return self.session.post(url, json=json, params=kwargs)

    @ratelimit
    def __patch_resource(self, url, json, **kwargs):
        return self.session.patch(url, json=json, params=kwargs)

    def __get_paginated_resource(self, url, **kwargs):
        next_url = url
        while next_url:
            resp = self.get_resource(next_url, **kwargs)

            for datum in resp["data"]:
                yield datum

            paging = resp["meta"].get("paging")
            if paging:
                if paging.get("next"):
                    next_url = paging["next"]
                else:
                    # no more next page, break
                    next_url = None
            else:
                # no paging meta, break the loop
                next_url = None

    def get_contact(self, id, **kwargs):
        """GET a Contact."""
        url = Session.__make_url(f"contacts/{id}")
        return self.__get_resource(url, **kwargs)

    def get_contacts(self, **kwargs):
        """GET a list of Contacts."""
        url = Session.__make_url("contacts")
        return self.__get_paginated_resource(url, **kwargs)

    def get_who_am_i(self, **kwargs):
        """GET currently authenticated User."""
        url = Session.__make_url("users/who_am_i")
        return self.__get_resource(url, **kwargs)

    def get_user(self, id, **kwargs):
        """GET a single User."""
        url = Session.__make_url(f"users/{id}")
        return self.__get_resource(url, **kwargs)

    def get_users(self, **kwargs):
        """GET a list of Users."""
        url = Session.__make_url("users")
        return self.__get_paginated_resource(url, **kwargs)

    def get_document(self, id, **kwargs):
        """GET a Document."""
        url = Session.__make_url(f"documents/{id}")
        return self.__get_resource(url, **kwargs)

    def get_documents(self, **kwargs):
        """GET a list of Documents."""
        url = Session.__make_url("documents")
        return self.__get_paginated_resource(url, **kwargs)

    def get_matter(self, id, **kwargs):
        """GET a Matter."""
        url = Session.__make_url(f"matters/{id}")
        return self.__get_resource(url, **kwargs)

    def get_matters(self, **kwargs):
        """GET a list of Matters."""
        url = Session.__make_url("matters")
        return self.__get_paginated_resource(url, **kwargs)

    def post_folder(self, name, parent_id, parent_type, **kwargs):
        """POST a new Folder."""
        url = Session.__make_url("folders")
        return self.__post_resource(
            url,
            json={
                "name": name,
                "parent": {
                    "id": parent_id,
                    "type": parent_type
                }
            }
        )

    def upload_document(self, name, parent_id, parent_type, document):
        """POST a new Document, PUT the data, and PATCH Document as fully_uploaded."""
        post_url = Session.__make_url("documents")
        clio_document = self.__post_resource(
            post_url,
            params={"fields": "id,latest_document_version{uuid,put_url,put_headers}"},
            json={
                "data": {
                    "name": name,
                    "parent": {
                        "id": parent_id,
                        "type": parent_type
                    }
                }
            }
        )

        put_url = clio_document["data"]["latest_document_version"]["put_url"]
        put_headers = clio_document["data"]["latest_document_version"]["put_headers"]

        headers_map = {}
        for header in put_headers:
            headers_map[header['name']] = header['value']

        # We actually DON'T want to use the authenticated client here
        requests.put(
            put_url,
            headers=headers_map,
            data=document
        )

        patch_url = self.__make_url(f"documents/{clio_document['data']['id']}")
        patch_resp = self.__patch_resource(
            patch_url,
            params={"fields": "id,name,latest_document_version{fully_uploaded}"},
            json={
                "data": {
                    "uuid": clio_document["data"]["latest_document_version"]["uuid"],
                    "fully_uploaded": True
                }
            }
        )

        return patch_resp
