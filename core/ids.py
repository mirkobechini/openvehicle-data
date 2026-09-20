import re
import unicodedata


def slug(s):
    a = unicodedata.normalize("NFKD", str(s).replace("+", " plus ")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", a.lower()).strip("-")


def make_id(p, *parts):
    s = slug(" ".join(str(x) for x in parts))
    if not s:
        raise ValueError("empty id parts")
    return f"{p}_{s}"
