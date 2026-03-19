import unittest

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, call

import hyacinth

test_token = {
    "access_token": "not-a-real-access-token",
    "refresh_token": "not-a-real-refresh-token",
    "token_type": "bearer",
    "expires_in": int((timedelta(days=2)).total_seconds()),
    "expires_at": int((datetime.now() + timedelta(days=2)).timestamp()),
}
test_client_id = "test_client_id"
test_client_secret = "test_client_secret"


class TestSession(unittest.TestCase):
    def setUp(self):
        self.session = hyacinth.Session(
            token=test_token,
            client_id=test_client_id,
            client_secret=test_client_secret,
        )
        self.test_url = "https://test-url.com"
        self.test_params = {}

    def test_invalid_region_session(self):
        session = hyacinth.Session(
            token=test_token,
            client_id=test_client_id,
            client_secret=test_client_secret,
            region="JP",
        )
        # defaults to 'US' region
        self.assertEqual(
            session.make_url("who_am_i"), "https://app.clio.com/api/v4/who_am_i.json"
        )

    def test_us_region_session(self):
        session = hyacinth.Session(
            token=test_token,
            client_id=test_client_id,
            client_secret=test_client_secret,
            region="US",
        )
        self.assertEqual(
            session.make_url("who_am_i"), "https://app.clio.com/api/v4/who_am_i.json"
        )

    def test_ca_region_session(self):
        session = hyacinth.Session(
            token=test_token,
            client_id=test_client_id,
            client_secret=test_client_secret,
            region="CA",
        )
        self.assertEqual(
            session.make_url("who_am_i"), "https://ca.app.clio.com/api/v4/who_am_i.json"
        )

    def test_eu_region_session(self):
        session = hyacinth.Session(
            token=test_token,
            client_id=test_client_id,
            client_secret=test_client_secret,
            region="EU",
        )
        self.assertEqual(
            session.make_url("who_am_i"), "https://eu.app.clio.com/api/v4/who_am_i.json"
        )

    def test_au_region_session(self):
        session = hyacinth.Session(
            token=test_token,
            client_id=test_client_id,
            client_secret=test_client_secret,
            region="AU",
        )
        self.assertEqual(
            session.make_url("who_am_i"), "https://au.app.clio.com/api/v4/who_am_i.json"
        )

    def test_get_resource_requests_correct_url(self):
        m = MagicMock()
        self.session.session.get = m
        self.session.get_resource(self.test_url)
        m.assert_called_once_with(self.test_url, params={})

    def test_get_paginated_resource_requests_correct_url(self):
        test_data = [
            {"id": "1", "name": "Anson MacKeracher"},
            {"id": "2", "name": "Nick Francis"},
        ]
        self.session.get_resource = MagicMock(
            return_value={"data": test_data, "meta": {}}
        )
        res = self.session.get_paginated_resource(self.test_url)
        self.assertEqual(tuple(test_data), tuple(res))

    def test_get_contact_url(self):
        self.session.get_resource = MagicMock()
        c = self.session.get_contact(1)
        self.session.get_resource.assert_called_with(
            "https://app.clio.com/api/v4/contacts/1.json"
        )

    def test_get_contact_fields(self):
        self.session.get_resource = MagicMock()
        test_fields = "id,name,email"
        u = self.session.get_contact(1, fields=test_fields)
        self.session.get_resource.assert_called_with(
            "https://app.clio.com/api/v4/contacts/1.json", fields=test_fields
        )

    def test_get_contacts_url(self):
        self.session.get_paginated_resource = MagicMock()
        c = self.session.get_contacts()
        self.session.get_paginated_resource.assert_called_with(
            "https://app.clio.com/api/v4/contacts.json"
        )

    def test_get_contacts_fields(self):
        self.session.get_paginated_resource = MagicMock()
        test_fields = "id,name,email"
        u = self.session.get_contacts(fields=test_fields)
        self.session.get_paginated_resource.assert_called_with(
            "https://app.clio.com/api/v4/contacts.json", fields=test_fields
        )

    def test_get_who_am_i_url(self):
        self.session.get_resource = MagicMock()
        u = self.session.get_who_am_i()
        self.session.get_resource.assert_called_with(
            "https://app.clio.com/api/v4/users/who_am_i.json"
        )

    def test_get_who_am_i_fields(self):
        self.session.get_resource = MagicMock()
        test_fields = "id,name,email,subscription_type,enabled"
        u = self.session.get_who_am_i(fields=test_fields)
        self.session.get_resource.assert_called_with(
            "https://app.clio.com/api/v4/users/who_am_i.json", fields=test_fields
        )

    def test_get_user_url(self):
        self.session.get_resource = MagicMock()
        u = self.session.get_user(1)
        self.session.get_resource.assert_called_with(
            "https://app.clio.com/api/v4/users/1.json"
        )

    def test_get_user_fields(self):
        self.session.get_resource = MagicMock()
        test_fields = "id,name,email,subscription_type,enabled"
        u = self.session.get_user(1, fields=test_fields)
        self.session.get_resource.assert_called_with(
            "https://app.clio.com/api/v4/users/1.json", fields=test_fields
        )

    def test_get_users_url(self):
        self.session.get_paginated_resource = MagicMock()
        c = self.session.get_users()
        self.session.get_paginated_resource.assert_called_with(
            "https://app.clio.com/api/v4/users.json"
        )

    def test_get_users_fields(self):
        self.session.get_paginated_resource = MagicMock()
        test_fields = "id,name,email,subscription_type,enabled"
        u = self.session.get_users(fields=test_fields)
        self.session.get_paginated_resource.assert_called_with(
            "https://app.clio.com/api/v4/users.json", fields=test_fields
        )

    def test_document_url(self):
        self.session.get_resource = MagicMock()
        u = self.session.get_document(1)
        self.session.get_resource.assert_called_with(
            "https://app.clio.com/api/v4/documents/1.json"
        )

    def test_document_fields(self):
        self.session.get_resource = MagicMock()
        test_fields = "id,name,content_type"
        u = self.session.get_document(1, fields=test_fields)
        self.session.get_resource.assert_called_with(
            "https://app.clio.com/api/v4/documents/1.json", fields=test_fields
        )

    def test_get_documents_url(self):
        self.session.get_paginated_resource = MagicMock()
        c = self.session.get_documents()
        self.session.get_paginated_resource.assert_called_with(
            "https://app.clio.com/api/v4/documents.json"
        )

    def test_get_documents_fields(self):
        self.session.get_paginated_resource = MagicMock()
        test_fields = "id,name,content_type"
        u = self.session.get_documents(fields=test_fields)
        self.session.get_paginated_resource.assert_called_with(
            "https://app.clio.com/api/v4/documents.json", fields=test_fields
        )

    def test_matter_url(self):
        self.session.get_resource = MagicMock()
        u = self.session.get_matter(1)
        self.session.get_resource.assert_called_with(
            "https://app.clio.com/api/v4/matters/1.json"
        )

    def test_matter_fields(self):
        self.session.get_resource = MagicMock()
        test_fields = "id,client{id,first_name,last_name}"
        u = self.session.get_matter(1, fields=test_fields)
        self.session.get_resource.assert_called_with(
            "https://app.clio.com/api/v4/matters/1.json", fields=test_fields
        )

    def test_get_matters_url(self):
        self.session.get_paginated_resource = MagicMock()
        c = self.session.get_matters()
        self.session.get_paginated_resource.assert_called_with(
            "https://app.clio.com/api/v4/matters.json"
        )

    def test_get_matters_fields(self):
        self.session.get_paginated_resource = MagicMock()
        test_fields = "id,client{id,first_name,last_name},"
        u = self.session.get_matters(fields=test_fields)
        self.session.get_paginated_resource.assert_called_with(
            "https://app.clio.com/api/v4/matters.json", fields=test_fields
        )

    def test_download_document(self):
        self.session.get_resource = MagicMock()
        u = self.session.download_document(1)
        self.session.get_resource.assert_called_with(
            "https://app.clio.com/api/v4/documents/1/download.json"
        )

    def test_delete_webhook(self):
        self.session.delete_resource = MagicMock()
        _ = self.session.delete_webhook(1)
        self.session.delete_resource.assert_called_with(
            "https://app.clio.com/api/v4/webhooks/1.json"
        )

    def test_update_webhook(self):
        self.session.patch_resource = MagicMock()
        json = {
            "data": {
                "fields": "id,client{id,first_name,last_name},",
            }
        }
        _ = self.session.update_webhook(1, json=json)
        self.session.patch_resource.assert_called_with(
            "https://app.clio.com/api/v4/webhooks/1.json", json=json
        )


class TestOnTokenInvalid(unittest.TestCase):
    def _make_response(self, status_code, content=b'{"data": {}}', content_type="application/json"):
        resp = MagicMock()
        resp.status_code = status_code
        resp.headers = {"Content-Type": content_type}
        resp.content = content
        resp.json.return_value = {"data": {}}
        return resp

    def _make_session(self, on_token_invalid=None, raise_for_status=False):
        return hyacinth.Session(
            token=test_token,
            client_id=test_client_id,
            client_secret=test_client_secret,
            on_token_invalid=on_token_invalid,
            raise_for_status=raise_for_status,
        )

    def test_401_triggers_refresh_and_retries(self):
        """401 with on_token_invalid triggers callback and retries with new token."""
        new_token = {"access_token": "refreshed-token", "token_type": "bearer"}
        refresh_cb = MagicMock(return_value=new_token)
        session = self._make_session(on_token_invalid=refresh_cb)

        resp_401 = self._make_response(401)
        resp_200 = self._make_response(200)
        session.session.get = MagicMock(side_effect=[resp_401, resp_200])

        result = session.get_resource("https://example.com/api/test.json")

        refresh_cb.assert_called_once()
        self.assertEqual(session.session.token, new_token)
        self.assertEqual(result, {"data": {}})

    def test_401_retry_also_401_falls_through(self):
        """If retry after refresh also returns 401, no infinite loop — falls through."""
        new_token = {"access_token": "refreshed-token", "token_type": "bearer"}
        refresh_cb = MagicMock(return_value=new_token)
        session = self._make_session(on_token_invalid=refresh_cb)

        resp_401_first = self._make_response(401)
        resp_401_second = self._make_response(401)
        session.session.get = MagicMock(side_effect=[resp_401_first, resp_401_second])

        result = session.get_resource("https://example.com/api/test.json")

        refresh_cb.assert_called_once()
        # Second 401 falls through to normal return
        self.assertEqual(result, {"data": {}})

    def test_401_without_on_token_invalid_falls_through(self):
        """401 without on_token_invalid set falls through normally."""
        session = self._make_session(on_token_invalid=None)

        resp_401 = self._make_response(401)
        session.session.get = MagicMock(return_value=resp_401)

        result = session.get_resource("https://example.com/api/test.json")

        # Should return without attempting refresh
        session.session.get.assert_called_once()
        self.assertEqual(result, {"data": {}})

    def test_on_token_invalid_returning_none_skips_retry(self):
        """on_token_invalid returning None skips retry."""
        refresh_cb = MagicMock(return_value=None)
        session = self._make_session(on_token_invalid=refresh_cb)

        resp_401 = self._make_response(401)
        session.session.get = MagicMock(return_value=resp_401)

        result = session.get_resource("https://example.com/api/test.json")

        refresh_cb.assert_called_once()
        # No retry — only one call to session.get
        session.session.get.assert_called_once()
        self.assertEqual(result, {"data": {}})
