from enum import StrEnum


class Category(StrEnum):
    M1 = "M1"


class Fuel(StrEnum):
    PETROL = "petrol"
    DIESEL = "diesel"
    LPG = "lpg"
    CNG = "cng"
    ELECTRIC = "electric"
    HYBRID = "hybrid"
    PHEV = "phev"
    HYDROGEN = "hydrogen"
    OTHER = "other"
