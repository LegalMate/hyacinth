from authlib.integrations.requests_client import OAuth2Session

CLIO_API_BASE_URL_US="https://app.clio.com/api/v4"

class Session:
    def __init__(self, token, client_id, client_secret):
        self.session = OAuth2Session(client_id=client_id,
                                     client_secret=client_secret,
                                     token=token)

    @staticmethod
    def make_url(path):
        return f"{CLIO_API_BASE_URL_US}/{path}.json"

    def get_resource(self, url, **kwargs):
        resp = self.session.get(url, params=kwargs)
        return resp.json()

    def get_paginated_resource(self, url, **kwargs):
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

    def get_contact(self, id, **kwargs):
        url = Session.make_url(f"contacts/{id}")
        return self.get_resource(url, **kwargs)

    def get_contacts(self, **kwargs):
        url = Session.make_url("contacts")
        return self.get_paginated_resource(url, **kwargs)

    def get_who_am_i(self, **kwargs):
        url = Session.make_url("users/who_am_i")
        return self.get_resource(url, **kwargs)

    def get_user(self, id, **kwargs):
        url = Session.make_url(f"users/{id}")
        return self.get_resource(url, **kwargs)

    def get_users(self, **kwargs):
        url = Session.make_url("users")
        return self.get_paginated_resource(url, **kwargs)

    def get_document(self, id, **kwargs):
        url = Session.make_url(f"documents/{id}")
        return self.get_resource(url, **kwargs)

    def get_documents(self, **kwargs):
        url = Session.make_url("documents")
        return self.get_paginated_resource(url, **kwargs)
