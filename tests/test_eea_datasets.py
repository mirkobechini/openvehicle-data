import pytest
from pydantic import ValidationError

from pipeline.importers.eea_datasets import COMBINED, DATASETS, RECORDS, Dataset, parse_years

U = "a0da862c-0bed-460f-808a-0bae489b12b9"


def test_the_registry_covers_2019_to_2025():
    assert sorted(DATASETS) == list(range(2019, 2026))
    assert all(d.year == y for y, d in DATASETS.items())


def test_only_the_latest_year_is_provisional_and_only_2019_uses_the_combined_table():
    assert [y for y, d in DATASETS.items() if d.status == "P"] == [2025]
    assert [y for y, d in DATASETS.items() if d.table == COMBINED] == [2019]
    assert DATASETS[2024].table == "co2cars_2024Fv30" and DATASETS[2025].table == "co2cars_2025Pv31"


def test_every_year_has_its_own_metadata_record():
    recs = [d.record for d in DATASETS.values()]
    assert len(set(recs)) == 7
    assert DATASETS[2022].url == RECORDS + "992616f8-158f-4ecc-b978-814b81629db6"
    assert all(d.url.startswith("https://sdi.eea.europa.eu/catalogue/") for d in DATASETS.values())


@pytest.mark.parametrize("k", [
    {"year": 2009}, {"year": 2101}, {"table": "co2cars_2019; DROP"}, {"table": ""}, {"status": "X"},
    {"record": "not-a-uuid"}, {"record": U.upper()}, {"table": "co2cars_2020Fv22"}, {"extra": 1},
])
def test_invalid_dataset(k):
    with pytest.raises(ValidationError):
        Dataset(**{"year": 2019, "table": COMBINED, "status": "F", "record": U, **k})


def test_a_year_table_must_match_its_year():
    assert Dataset(year=2020, table="co2cars_2020Fv22", status="F", record=U).year == 2020
    with pytest.raises(ValidationError):
        Dataset(year=2021, table="co2cars_2020Fv22", status="F", record=U)


@pytest.mark.parametrize("s,ys", [
    ("2025", [2025]), ("2019-2025", list(range(2019, 2026))), ("2021,2023", [2021, 2023]),
    (" 2020 - 2022 , 2025 ", [2020, 2021, 2022, 2025]), ("2023,2019-2020,2023", [2019, 2020, 2023]), (2025, [2025]),
])
def test_parse_years(s, ys):
    assert parse_years(s) == ys


@pytest.mark.parametrize("s", ["", "abc", "2025-2019", "20", "2019-", "2018", "2026", "2019-2026", "2019;2020", "-2020"])
def test_parse_years_rejects_bad_input(s):
    with pytest.raises(ValueError):
        parse_years(s)


def test_the_error_lists_what_is_available():
    with pytest.raises(ValueError, match="2019-2025"):
        parse_years("2018")
