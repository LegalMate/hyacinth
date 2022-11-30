import os
import json

from authlib.integrations.requests_client import OAuth2Session

CLIO_API_BASE_URL_US="https://app.clio.com/api/v4"

TOKEN=json.loads(os.getenv("TOKEN"))
CLIENT_ID=os.getenv("CLIO_CLIENT_ID")
CLIENT_SECRET=os.getenv("CLIO_CLIENT_SECRET")

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
        return self.get_paginated_resource(url)

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
    

def main():
    sesh = Session(TOKEN, CLIENT_ID, CLIENT_SECRET)
    # contacts = sesh.get_contacts()
    # for c in contacts:
        # print(c["name"])
    me = sesh.get_who_am_i()
    print(me)

    users = sesh.get_users()
    for u in users:
        print(u)

    zelda = sesh.get_user(id="352065601")
    print(zelda)


if __name__ == "__main__":
    main()
