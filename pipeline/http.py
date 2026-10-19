import time

import httpx

DELAYS = (5, 20, 60)


def get(c, *a, **k):
    for d in (*DELAYS, None):
        try:
            r = c.get(*a, **k)
            if r.status_code >= 500 or r.status_code == 429:
                r.raise_for_status()
            return r
        except (httpx.TransportError, httpx.HTTPStatusError):
            if d is None:
                raise
            time.sleep(d)
