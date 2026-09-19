import pytest
from pydantic import ValidationError

from core.enums import Category, Fuel
from core.models import Brand, CarModel, Engine, Family, Generation, Variant


def gen(**k):
    return Generation(id="gen_fiat-500-2007", model_id="model_fiat-500", name="312", year_from=2007, **k)


def test_brand():
    b = Brand(id="brand_fiat", name=" Fiat ", aliases=[" FIAT ", "", "FIAT", "Fiat Auto"])
    assert b.name == "Fiat"
    assert b.aliases == ["FIAT", "Fiat Auto"]


def test_model_default_category():
    m = CarModel(id="model_fiat-500", brand_id="brand_fiat", name="500")
    assert m.category is Category.M1


def test_model_bad_category():
    with pytest.raises(ValidationError):
        CarModel(id="model_fiat-500", brand_id="brand_fiat", name="500", category="N1")


@pytest.mark.parametrize("i", ["fiat", "brand_", "Brand_fiat", "brand_fi at", "model_fiat", "brand_-fiat"])
def test_bad_id(i):
    with pytest.raises(ValidationError):
        Brand(id=i, name="Fiat")


def test_empty_name():
    with pytest.raises(ValidationError):
        Brand(id="brand_fiat", name="   ")


def test_extra_forbidden():
    with pytest.raises(ValidationError):
        Brand(id="brand_fiat", name="Fiat", x=1)


def test_generation_open_ended():
    assert gen().year_to is None


def test_generation_years():
    assert gen(year_to=2015).year_to == 2015
    assert gen(year_to=2007).year_to == 2007
    with pytest.raises(ValidationError):
        gen(year_to=2006)


@pytest.mark.parametrize("y", [1800, 2200])
def test_year_range(y):
    with pytest.raises(ValidationError):
        gen(year_to=y)


def test_engine():
    e = Engine(id="eng_petrol-1242-51", fuel="petrol", displacement_cc=1242, power_kw=51)
    assert e.fuel is Fuel.PETROL
    assert Engine(id="eng_electric-0-80", fuel=Fuel.ELECTRIC).displacement_cc is None


@pytest.mark.parametrize("k", [{"displacement_cc": -1}, {"displacement_cc": 20000}, {"power_kw": 0}, {"power_kw": 5000}])
def test_engine_range(k):
    with pytest.raises(ValidationError):
        Engine(id="eng_petrol-1242-51", fuel="petrol", **k)


def var(**k):
    return Variant(id="var_fiat-500-1-2", generation_id="gen_fiat-500-2007", engine_id="eng_petrol-1242-51", name="1.2 69", year_from=2008, **k)


def test_variant():
    v = var(mass_kg=865, wheelbase_mm=2300, track_width_mm=1408, co2_wltp_g_km=120.5)
    assert v.mass_kg == 865
    assert var().co2_wltp_g_km is None


@pytest.mark.parametrize("k", [{"mass_kg": 0}, {"mass_kg": 20000}, {"wheelbase_mm": 100}, {"track_width_mm": 9000}, {"co2_wltp_g_km": -1}])
def test_variant_range(k):
    with pytest.raises(ValidationError):
        var(**k)


def test_registrations_default_and_values():
    assert CarModel(id="model_a", brand_id="brand_a", name="A").registrations is None
    assert CarModel(id="model_a", brand_id="brand_a", name="A", registrations=0).registrations == 0
    assert var(registrations=12).registrations == 12
    assert var().registrations is None


@pytest.mark.parametrize("v", [-1, 1.5, "many"])
def test_registrations_invalid(v):
    with pytest.raises(ValidationError):
        var(registrations=v)
    with pytest.raises(ValidationError):
        CarModel(id="model_a", brand_id="brand_a", name="A", registrations=v)


def fam(**k):
    return Family(**{"id": "family_mercedes-benz-glc", "brand_id": "brand_mercedes-benz", "name": "GLC", "model_count": 11, "registrations": 13713, **k})


def test_family():
    f = fam(aliases=[" glc ", "", "GLC"])
    assert (f.id, f.brand_id, f.name, f.model_count, f.registrations) == ("family_mercedes-benz-glc", "brand_mercedes-benz", "GLC", 11, 13713)
    assert f.aliases == ["glc", "GLC"]
    assert fam(registrations=None).registrations is None and fam(registrations=0).registrations == 0


@pytest.mark.parametrize("k", [
    {"id": "model_mercedes-benz-glc"}, {"id": "family_"}, {"id": "Family_glc"}, {"brand_id": "brand_"},
    {"model_count": 0}, {"model_count": -1}, {"model_count": 1.5}, {"registrations": -1}, {"name": "  "}, {"extra": 1},
])
def test_family_invalid(k):
    with pytest.raises(ValidationError):
        fam(**k)


def test_model_family_id_is_optional_and_checked():
    assert CarModel(id="model_a", brand_id="brand_a", name="A").family_id is None
    assert CarModel(id="model_a", brand_id="brand_a", name="A", family_id="family_a-a").family_id == "family_a-a"
    for bad in ("model_a", "family_", "FAMILY_a", 5):
        with pytest.raises(ValidationError):
            CarModel(id="model_a", brand_id="brand_a", name="A", family_id=bad)
