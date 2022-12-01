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
    def test_get_resource(self):
        test_url = "https://test-url.com"
        test_params = {}
        
        s = hyacinth.Session(token=test_token,
                             client_id=test_client_id,
                             client_secret=test_client_secret)

        m = s.session.get = MagicMock()

        s.get_resource(test_url)

        m.assert_called_once_with(test_url, params=test_params)
        
