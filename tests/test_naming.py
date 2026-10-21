import math

import pandas as pd
import pytest

from udg_catalogue.naming import AliasKeyStep, GalaxyNameNormalizer, designations


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
        ("UDG-DF44", "df44"),
        ("UDG R5", "r5"),
        ("UDG 7", "udg7"),
        ("UDG", "udg"),
        ("NGC5846-UDG1", "ngc5846udg1"),
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


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Yagi093 (DF26, GMP 2748)", ["Yagi093", "DF26", "GMP 2748"]),
        ("NGVS1593 (VCC1052)", ["NGVS1593", "VCC1052"]),
        ("DF2 (RCP 29)", ["DF2", "RCP 29"]),
        ("Disco Ball (SMDG0038365-064207)", ["SMDG0038365-064207"]),
        ("KiDS UDG candidate (RA=0.627707, Dec=-30.6654)", []),
        ("Dragonfly 44", []),
        (None, []),
    ],
)
def test_designations(name, expected):
    assert designations(name) == expected


def keyed(names):
    normalizer = GalaxyNameNormalizer()
    return pd.DataFrame({"galaxy_name": names, "_norm_key": [normalizer.normalize(name) for name in names]})


def alias_keys(frame):
    return AliasKeyStep("galaxy_name", "_norm_key", GalaxyNameNormalizer()).process(frame)["_norm_key"].tolist()


def test_a_name_and_its_aliases_share_one_key():
    frame = keyed(["NGVS1593 (VCC1052)", "VCC1052", "Yagi276 (DF28)", "DF28", "Yagi276", "DF 44"])

    assert alias_keys(frame) == ["ngvs1593vcc1052"] * 2 + ["df28"] * 3 + ["df44"]


def test_aliases_join_every_key_of_a_chain_into_one():
    frame = keyed(["Yagi093 (DF26)", "DF26", "Yagi093 (DF26, GMP 2748)", "GMP 2748", "Yagi093"])

    assert set(alias_keys(frame)) == {"df26"}


def test_aliases_join_only_keys_that_rows_have():
    frame = keyed(["DF2 (RCP 29)", "Dragonfly 44", None])

    assert AliasKeyStep("galaxy_name", "_norm_key", GalaxyNameNormalizer()).process(frame) is frame
