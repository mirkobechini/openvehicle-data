import re


def base(s):
    p = [x.strip() for x in str(s or "").lower().split("*")]
    return "*".join(p[:3]) if len(p) >= 3 and re.fullmatch(r"e\d{1,3}", p[0]) and all(re.fullmatch(r"\S+", x) for x in p[:3]) else None
