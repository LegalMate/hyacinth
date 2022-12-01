from authlib.integrations.requests_client import OAuth2Session

CLIO_API_BASE_URL_US="https://app.clio.com/api/v4"

class Session:
    def __init__(self, token, client_id, client_secret):
        self.session = OAuth2Session(client_id=client_id,
                                     client_secret=client_secret,
                                     token=token)

    def get_resource(self, url, **kwargs):
        return self.session.get(url, params=kwargs)

    def get_paginated_resource(self, url, **kwargs):
        next_url = url
        while next_url:
            res = self.get_resource(next_url, params=kwargs)
            data = res.json()["data"]

            # this is a generator fn
            for contact in data:
                yield contact

            paging = res.json()["meta"].get("paging")
            if paging:
                if paging.get("next"):
                    next_url = paging["next"]
                else:
                    next_url = None
            else:
                # break the loop
                next_url = None

    def get_contact(self, id):
        res = self.get(f"/contacts/{id}.json")
        return res.json()["data"]

    def get_contacts(self, **kwargs):
        url = f"{CLIO_API_BASE_URL_US}/contacts.json"
        return self.get_paginated_resource(url, kwargs)    

    def get_who_am_i(self):
        url = f"{CLIO_API_BASE_URL_US}/users/who_am_i.json"
        res = self.get_resource(url)
        data = res.json()["data"]
        return data

    def get_user(self, id):
        url = f"{CLIO_API_BASE_URL_US}/users/{id}.json"
        res = self.get_resource(url)
        data = res.json()["data"]
        return data

    def get_users(self):
        url = f"{CLIO_API_BASE_URL_US}/users.json"
        return self.get_paginated_resource(url)
