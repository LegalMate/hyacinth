"""async_session.py -- Async Session for Clio API."""
from authlib.integrations.httpx_client import AsyncOAuth2Client


CLIO_API_BASE_URL_US = "https://app.clio.com/api/v4"
CLIO_API_TOKEN_ENDPOINT = "https://app.clio.com/oauth/token"  # nosec
CLIO_API_RATELIMIT_LIMIT_HEADER = "X-RateLimit-Limit"
CLIO_API_RATELIMIT_REMAINING_HEADER = "X-RateLimit-Remaining"
CLIO_API_RETRY_AFTER = "Retry-After"


class AsyncSession:
    """Class for interacting with Clio Manage API using async/await."""

    def __init__(
        self,
        token,
        client_id,
        client_secret,
        update_token=lambda *args: None,
    ):
        """Initialize our Session with an AsyncOAuth2Client."""
        self.session = AsyncOAuth2Client(
            client_id=client_id,
            client_secret=client_secret,
            token=token,
            token_endpoint=CLIO_API_TOKEN_ENDPOINT,
            update_token=update_token,
        )


    def upload_document(self, name, parent_id, parent_type, document):
        # TODO: this!
        pass
