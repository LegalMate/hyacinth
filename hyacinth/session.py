import time
from authlib.integrations.requests_client import OAuth2Session

CLIO_API_BASE_URL_US="https://app.clio.com/api/v4"

class Session:
    def __init__(self, token, client_id, client_secret):
        self.session = OAuth2Session(client_id=client_id,
                                     client_secret=client_secret,
                                     token=token)

    @staticmethod
    def __make_url(path):
        return f"{CLIO_API_BASE_URL_US}/{path}.json"

    def __get_resource(self, url, **kwargs):
        resp = self.session.get(url, params=kwargs)
        return resp.json()

    def __get_paginated_resource(self, url, **kwargs):
        next_url = url
        while next_url:
            resource = self.get_resource(next_url, **kwargs)

            # this is a generator fn
            for contact in resource["data"]:
                yield contact

            paging = resource["meta"].get("paging")
            if paging:
                if paging.get("next"):
                    next_url = paging["next"]
                else:
                    # no more next page, break
                    next_url = None
            else:
                # no paging meta, break the loop
                next_url = None

    def __post_resource(self, url, json, **kwargs):
        resp = self.session.post(url, json=json, **kwargs)
        return resp.json()

    def __put_resource(self, url,  **kwargs):
        resp = self.session.put(url, **kwargs)
        return resp

    def __patch_resource(self, url, json, **kwargs):
        resp = self.session.patch(url, json=json, **kwargs)
        return resp.json()

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

        print(clio_document)

        put_url = clio_document["data"]["latest_document_version"]["put_url"]
        put_headers = clio_document["data"]["latest_document_version"]["put_headers"]

        headers_map = {}
        for header in put_headers:
            headers_map[header['name']] = header['value']

        print(put_url, headers_map)

        put_resp = self.__put_resource(put_url, headers=headers_map, data=document)

        print(put_resp)

        # PURE JANK
        # time.sleep(1)
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

        print(patch_resp)

        return patch_resp
