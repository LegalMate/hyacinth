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
        m = MagicMock()
        m.json.return_value = {"data": test_data,
                               "meta": {}}
        self.session.get_resource = MagicMock(return_value=m)
        res = self.session.get_paginated_resource(self.test_url)
        self.assertEqual(tuple(test_data), tuple(res))
        m.json.assert_called()
