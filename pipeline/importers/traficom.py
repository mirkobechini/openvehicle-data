import csv
import io
import zipfile

import httpx

from pipeline import http

URL = "https://opendata.traficom.fi/Content/Ajoneuvorekisteri.zip"
PAGE = "https://www.avoindata.fi/data/en/dataset/ajoneuvojen-avoin-data"
UA = "openvehicle-data/0.0 (+https://github.com/mirkobechini/openvehicle-data)"
ENCODING = "cp1252"
CAT = "M1"


def fetch(client=None):
    c = client or httpx.Client(timeout=300)
    try:
        r = http.get(c, URL, headers={"Accept": "application/zip", "User-Agent": UA})
        r.raise_for_status()
        return r.content
    finally:
        if client is None:
            c.close()


def rows(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    f = io.TextIOWrapper(z.open(z.namelist()[0]), encoding=ENCODING, newline="")
    for r in csv.DictReader(f, delimiter=";"):
        if r.get("ajoneuvoluokka") == CAT:
            yield r
