import os
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.config import get_settings

settings = get_settings()

# In automated test environments (TESTING=1 or py.test in argv), disable limiter unless specifically testing rate limits
is_testing = os.getenv("TESTING", "0") == "1"

limiter = Limiter(
    key_func=get_remote_address,
    enabled=not is_testing,
    default_limits=[settings.RATE_LIMIT_GENERAL],
)
