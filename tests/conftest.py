import os

os.environ["OVD_RATE_LIMIT"] = "0"

from pipeline import http  # noqa: E402

http.DELAYS = (0, 0, 0)
