import unittest

from datetime import datetime, timedelta
from unittest.mock import MagicMock

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
        self.session = hyacinth.Session(token=test_token,
                                        client_id=test_client_id,
                                        client_secret=test_client_secret)
        self.test_url = "https://test-url.com"
        self.test_params = {}

    def test_get_resource_requests_correct_url(self):
        m = MagicMock()
        self.session.session.get = m
        self.session.get_resource(self.test_url)
        m.assert_called_once_with(self.test_url, params=self.test_params)

    def test_get_paginated_resource_requests_correct_url(self):
        test_data = [{"id": "1",
                      "name": "Anson MacKeracher"},
                     {"id": "2",
                      "name": "Nick Francis"}]
        self.session.get_resource = MagicMock(return_value={"data": test_data,
                                                            "meta": {}})
        res = self.session.get_paginated_resource(self.test_url)
        self.assertEqual(tuple(test_data), tuple(res))

    def test_get_contact_url(self):
        self.session.get_resource = MagicMock()
        c = self.session.get_contact(1)
        self.session.get_resource.assert_called_with("https://app.clio.com/api/v4/contacts/1.json")

    def test_get_contact_fields(self):
        self.session.get_resource = MagicMock()
        test_fields = "id,name,email"
        u = self.session.get_contact(1, fields=test_fields)
        self.session.get_resource.assert_called_with(
            "https://app.clio.com/api/v4/contacts/1.json",
            fields=test_fields)

    def test_get_contacts_url(self):
        self.session.get_paginated_resource = MagicMock()
        c = self.session.get_contacts()
        self.session.get_paginated_resource.assert_called_with("https://app.clio.com/api/v4/contacts.json")

    def test_get_contacts_fields(self):
        self.session.get_paginated_resource = MagicMock()
        test_fields = "id,name,email"
        u = self.session.get_contacts(fields=test_fields)
        self.session.get_paginated_resource.assert_called_with(
            "https://app.clio.com/api/v4/contacts.json",
            fields=test_fields)

    def test_get_who_am_i_url(self):
        self.session.get_resource = MagicMock()
        u = self.session.get_who_am_i()
        self.session.get_resource.assert_called_with("https://app.clio.com/api/v4/users/who_am_i.json")

    def test_get_who_am_i_fields(self):
        self.session.get_resource = MagicMock()
        test_fields = "id,name,email,subscription_type,enabled"
        u = self.session.get_who_am_i(fields=test_fields)
        self.session.get_resource.assert_called_with(
            "https://app.clio.com/api/v4/users/who_am_i.json",
            fields=test_fields)

    def test_get_user_url(self):
        self.session.get_resource = MagicMock()
        u = self.session.get_user(1)
        self.session.get_resource.assert_called_with("https://app.clio.com/api/v4/users/1.json")

    def test_get_user_fields(self):
        self.session.get_resource = MagicMock()
        test_fields = "id,name,email,subscription_type,enabled"
        u = self.session.get_user(1, fields=test_fields)
        self.session.get_resource.assert_called_with(
            "https://app.clio.com/api/v4/users/1.json",
            fields=test_fields)

    def test_get_users_url(self):
        self.session.get_paginated_resource = MagicMock()
        c = self.session.get_users()
        self.session.get_paginated_resource.assert_called_with("https://app.clio.com/api/v4/users.json")

    def test_get_users_fields(self):
        self.session.get_paginated_resource = MagicMock()
        test_fields = "id,name,email,subscription_type,enabled"
        u = self.session.get_users(fields=test_fields)
        self.session.get_paginated_resource.assert_called_with(
            "https://app.clio.com/api/v4/users.json",
            fields=test_fields)

    def test_document_url(self):
        self.session.get_resource = MagicMock()
        u = self.session.get_document(1)
        self.session.get_resource.assert_called_with("https://app.clio.com/api/v4/documents/1.json")

    def test_document_fields(self):
        self.session.get_resource = MagicMock()
        test_fields = "id,name,content_type"
        u = self.session.get_document(1, fields=test_fields)
        self.session.get_resource.assert_called_with(
            "https://app.clio.com/api/v4/documents/1.json",
            fields=test_fields)

    def test_get_documents_url(self):
        self.session.get_paginated_resource = MagicMock()
        c = self.session.get_documents()
        self.session.get_paginated_resource.assert_called_with("https://app.clio.com/api/v4/documents.json")

    def test_get_documents_fields(self):
        self.session.get_paginated_resource = MagicMock()
        test_fields = "id,name,content_type"
        u = self.session.get_documents(fields=test_fields)
        self.session.get_paginated_resource.assert_called_with(
            "https://app.clio.com/api/v4/documents.json",
            fields=test_fields)
