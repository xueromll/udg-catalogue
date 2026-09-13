import math

import pytest

from udg_catalogue.naming import GalaxyNameNormalizer


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("DF 44", "df44"),
        ("Dragonfly 44", "df44"),
        ("df-44", "df44"),
        ("DF044", "df44"),
        ("ＤＦ４４", "df44"),
        ("VCC 1234", "vcc1234"),
        ("Coma UDG", "comaudg"),
        ("KDG 44", "kdg44"),
        ("UGC 2162", "ugc2162"),
        ("NGC 1052-DF2", "ngc1052df2"),
        ("NGC 1052-DF4", "ngc1052df4"),
        ("Dw0010-0112", "dw10.112"),
        ("dw 10-112", "dw10.112"),
        ("dw 101-12", "dw101.12"),
        ("+", ""),
        (None, ""),
        (math.nan, ""),
        ("", ""),
        (["DF 44"], ""),
    ],
)
def test_normalize(name, expected):
    assert GalaxyNameNormalizer().normalize(name) == expected


def test_distinct_catalogue_numbers_never_share_a_key():
    normalizer = GalaxyNameNormalizer()
    names = ["DF 44", "KDG 44", "UGC 44", "NGC 1052-DF2", "NGC 1052-DF4", "dw 1-12", "dw 11-2"]

    assert len({normalizer.normalize(name) for name in names}) == len(names)


def test_prefix_aliases_are_configurable():
    assert GalaxyNameNormalizer(prefix_aliases={}).normalize("Dragonfly 44") == "dragonfly44"
    assert GalaxyNameNormalizer(prefix_aliases={"virgocc": "vcc"}).normalize("VirgoCC 1287") == "vcc1287"
