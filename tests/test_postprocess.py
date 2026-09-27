import asyncio

import astropy.units as u
import numpy as np
import pandas as pd
from sci_etl_core import RawRecord

from udg_catalogue.astrometry import sky_coordinates
from udg_catalogue.pipeline import build_catalogue_exporter
from udg_catalogue.postprocess import (
    RawRowsStep,
    build_catalogue_chain,
    build_catalogue_layout,
    build_sorted_catalogue,
    describe_catalogue,
    read_catalogue,
)


def test_layout_sorts_rows_orders_columns_and_hides_internal_columns():
    frame = pd.DataFrame(
        {
            "_norm_key": ["b", "a", "c"],
            "ra": [1.0, 2.0, 3.0],
            "galaxy_name": ["B", "A", "C"],
            "completeness_pct": [50.0, 100.0, 50.0],
            "constellation": ["Orion", "Lyra", "Lyra"],
            "cluster_id": [0, -1, 1],
            "quality_flag": ["Needs Review", "Confirmed", "Needs Review"],
        }
    )

    laid_out = build_catalogue_layout().process(frame)

    assert laid_out["galaxy_name"].tolist() == ["A", "C", "B"]
    assert laid_out.columns.tolist() == [
        "galaxy_name",
        "completeness_pct",
        "quality_flag",
        "constellation",
        "cluster_id",
        "ra",
    ]


def test_layout_without_sort_columns_keeps_row_order():
    assert build_catalogue_layout().process(pd.DataFrame({"other": [2, 1]}))["other"].tolist() == [2, 1]


def test_catalogue_chain_derives_the_scientific_columns(catalogue_config):
    raw = pd.DataFrame(
        {
            "record_id": ["2401.00001", "2401.00001", "2402.00002", "2402.00002"],
            "galaxy_name": ["Alpha", "Beta", "Beta copy", "Gamma"],
            "ra": [83.633, 10.0, 10.0001, 10.1],
            "dec": [-5.361, 20.0, 20.0001, 20.1],
            "distance_mpc": [5.0, 15.0, np.nan, 15.1],
            "effective_radius_kpc": [2.0, np.nan, np.nan, np.nan],
            "stellar_mass_solar": [1e8, np.nan, 3e7, np.nan],
            "dark_matter_fraction": [0.95, 0.5, np.nan, np.nan],
        }
    )

    catalogue = build_catalogue_chain(catalogue_config).process(raw)
    rows = catalogue.set_index("galaxy_name")

    assert "_norm_key" not in catalogue.columns
    assert rows.index.tolist() == ["Alpha", "Beta", "Gamma"]
    assert rows.loc["Alpha", "dark_matter_fraction"] == 0.95
    assert rows.loc["Alpha", "completeness_pct"] == 100.0
    assert rows.loc["Alpha", "quality_flag"] == "Confirmed"
    assert rows.loc["Alpha", "constellation"] == "Orion"
    assert rows.loc["Alpha", "cluster_id"] == -1
    assert rows.loc["Beta", "stellar_mass_solar"] == 3e7
    assert rows.loc["Beta", "completeness_pct"] == 83.3
    assert rows.loc["Beta", "cluster_id"] == rows.loc["Gamma", "cluster_id"] != -1
    assert rows.loc["Gamma", "quality_flag"] == "Needs Review"
    assert rows.loc["Beta", "source_papers"] == "2401.00001; 2402.00002"
    assert rows.loc["Alpha", "source_papers"] == "2401.00001"
    assert catalogue.columns.tolist()[:6] == [
        "galaxy_name",
        "completeness_pct",
        "quality_flag",
        "constellation",
        "cluster_id",
        "source_papers",
    ]
    assert not any(column.startswith("_") or column == "record_id" for column in catalogue.columns)


def test_raw_rows_hide_the_paper_columns_and_read_measurements_as_numbers():
    raw = pd.DataFrame(
        {
            "record_id": ["2401.00001"],
            "extra": ['{"notes": "x"}'],
            "galaxy_name": ["DF 44"],
            "stellar_mass_solar": ["3.2 +/- 0.4"],
            "distance_mpc": ["100"],
        }
    )

    prepared = RawRowsStep().process(raw)

    assert prepared.columns.tolist() == ["_record_id", "_extra", "galaxy_name", "stellar_mass_solar", "distance_mpc"]
    assert pd.isna(prepared.loc[0, "stellar_mass_solar"])
    assert prepared.loc[0, "distance_mpc"] == 100.0
    assert raw.loc[0, "stellar_mass_solar"] == "3.2 +/- 0.4"


def test_no_two_catalogue_rows_lie_within_the_matching_radius(catalogue_config):
    raw = pd.DataFrame(
        {
            "record_id": ["p1", "p1", "p2", "p2", "p3", "p3", "p3"],
            "galaxy_name": ["4692", "ID 4692", "KiDS_UDG_5", "UDG_2.162882_-33.8838", "DF 2", "DF-2 twin", "DF 4"],
            "ra": [150.1, 150.1, 2.162882, 2.162882, 40.44, 40.4403, 40.3],
            "dec": [2.2, 2.2, -33.8838, -33.8838, -8.40, -8.4001, -8.1],
            "distance_mpc": [20.0, None, 30.0, None, 20.0, None, 20.0],
            "effective_radius_kpc": [2.0, None, 3.0, None, 2.2, 2.1, 1.9],
            "stellar_mass_solar": [1e8, 1e8, None, 2e8, 2e8, None, 1.5e8],
            "dark_matter_fraction": [None, 0.5, None, None, None, None, None],
        }
    )
    raw.loc[len(raw)] = ["p4", "DF-2 third", 40.4401, -8.4003, None, None, None, None]

    catalogue = build_catalogue_chain(catalogue_config).process(raw)

    coordinates = sky_coordinates(catalogue)
    first, second, _, _ = coordinates.search_around_sky(
        coordinates, catalogue_config.deduplication.max_separation_arcsec * u.arcsec
    )
    assert [(int(a), int(b)) for a, b in zip(first, second, strict=True) if a != b] == []
    assert len(catalogue) == 4


def test_build_sorted_catalogue_writes_the_sorted_file(catalogue_config):
    catalogue_config.paths.raw_catalogue.write_text(
        "record_id,galaxy_name,ra,dec,distance_mpc,extra\np1,Beta,10.0,20.0,,\np2,NA,83.633,-5.361,5.0,\n",
        encoding="utf-8",
    )
    messages = []

    catalogue = build_sorted_catalogue(catalogue_config, messages.append)

    written = read_catalogue(catalogue_config.paths.sorted_catalogue)
    assert written["galaxy_name"].tolist() == ["NA", "Beta"]
    assert len(catalogue) == 2
    assert messages[-1] == f"Sorted catalogue written to {catalogue_config.paths.sorted_catalogue}"
    assert [path.name for path in catalogue_config.paths.sorted_catalogue.parent.glob("*.tmp")] == []


PUBLISHED = (
    "galaxy_name,completeness_pct,quality_flag,constellation,cluster_id,ra,dec,distance_mpc\n"
    "Kept,33.3,Low Confidence,Orion,-1,83.633,-5.361,\n"
    "Beta,33.3,Low Confidence,Taurus,-1,10.0,20.0,\n"
    "Beta copy,33.3,Low Confidence,Taurus,-1,10.0001,20.0001,7.0\n"
)


def test_the_sorted_catalogue_is_built_from_the_raw_catalogue_alone(catalogue_config):
    catalogue_config.paths.sorted_catalogue.write_text(PUBLISHED, encoding="utf-8")
    catalogue_config.paths.raw_catalogue.write_text(
        "record_id,galaxy_name,ra,dec,distance_mpc\np1,Beta,10.0,20.0,\np1,Gamma,30.0,5.0,12.0\np2,Delta,31.0,6.0,\n",
        encoding="utf-8",
    )
    messages = []

    catalogue = build_sorted_catalogue(catalogue_config, messages.append)

    rows = read_catalogue(catalogue_config.paths.sorted_catalogue).set_index("galaxy_name")
    assert sorted(rows.index) == ["Beta", "Delta", "Gamma"]
    assert pd.isna(rows.loc["Beta", "distance_mpc"])
    assert len(catalogue) == 3
    assert messages[-1] == f"Sorted catalogue written to {catalogue_config.paths.sorted_catalogue}"


def test_a_corrected_deduplication_may_shrink_the_published_catalogue(catalogue_config):
    catalogue_config.paths.sorted_catalogue.write_text(PUBLISHED, encoding="utf-8")
    catalogue_config.paths.raw_catalogue.write_text(
        "record_id,galaxy_name,ra,dec,distance_mpc\n"
        "p1,Kept,83.633,-5.361,\np1,Beta,10.0,20.0,\np2,Beta copy,10.0,20.0,7.0\n",
        encoding="utf-8",
    )

    catalogue = build_sorted_catalogue(catalogue_config, lambda _message: None)

    assert sorted(catalogue["galaxy_name"]) == ["Beta", "Kept"]
    assert len(read_catalogue(catalogue_config.paths.sorted_catalogue)) == 2


def test_a_raw_catalogue_smaller_than_the_published_one_is_refused_unless_replacing(catalogue_config):
    catalogue_config.paths.sorted_catalogue.write_text(PUBLISHED, encoding="utf-8")
    raw = "record_id,galaxy_name,ra,dec\np1,Beta,10.0,20.0\n"
    catalogue_config.paths.raw_catalogue.write_text(raw, encoding="utf-8")
    messages = []

    catalogue =build_sorted_catalogue(catalogue_config, messages.append)

    assert catalogue["galaxy_name"].tolist() == ["Kept", "Beta", "Beta copy"]
    assert catalogue_config.paths.sorted_catalogue.read_text(encoding="utf-8") == PUBLISHED
    assert messages == [
        f"Refusing to overwrite {catalogue_config.paths.sorted_catalogue}: the raw catalogue has 1 rows but the "
        "published one has 3 galaxies, so the raw data looks incomplete. "
        "Pass --replace-catalogue to build the catalogue from the raw rows alone."
    ]

    replaced = build_sorted_catalogue(catalogue_config, messages.append, replace=True)

    assert replaced["galaxy_name"].tolist() == ["Beta"]
    assert read_catalogue(catalogue_config.paths.sorted_catalogue)["galaxy_name"].tolist() == ["Beta"]


def test_build_sorted_catalogue_skips_missing_or_empty_sources(catalogue_config):
    messages = []
    raw = catalogue_config.paths.raw_catalogue

    assert build_sorted_catalogue(catalogue_config, messages.append) is None
    raw.write_text("", encoding="utf-8")
    assert build_sorted_catalogue(catalogue_config, messages.append) is None
    raw.write_text("record_id,galaxy_name,ra\n", encoding="utf-8")
    assert build_sorted_catalogue(catalogue_config, messages.append) is None

    assert not catalogue_config.paths.sorted_catalogue.exists()
    assert len(messages) == 3


def test_a_raw_catalogue_without_paper_ids_is_not_merged(catalogue_config):
    catalogue_config.paths.raw_catalogue.write_text("galaxy_name,ra,dec\nBeta,10.0,20.0\n", encoding="utf-8")
    messages = []

    assert build_sorted_catalogue(catalogue_config, messages.append) is None
    assert not catalogue_config.paths.sorted_catalogue.exists()
    assert messages == [
        f"Raw catalogue has no record_id column: {catalogue_config.paths.raw_catalogue} was written before rows "
        "named their paper; rebuild it with --rescan"
    ]


def test_describe_catalogue_counts():
    catalogue = pd.DataFrame(
        {
            "completeness_pct": [100.0, 50.0, 100.0],
            "constellation": ["Orion", "Unknown", "Lyra"],
            "cluster_id": [0, -1, 0],
        }
    )

    assert describe_catalogue(catalogue) == [
        "Galaxies in sorted catalogue: 3",
        "Galaxies with 100% completeness: 2",
        "Constellations represented: 2",
        "3D clusters: 1",
    ]


def test_exported_negative_coordinates_are_read_back_as_numbers(catalogue_config):
    exporter = build_catalogue_exporter(catalogue_config)
    paper = RawRecord(record_id="2401.00001", title="NGC 1052-DF2", abstract="A galaxy lacking dark matter.")

    async def export():
        await exporter.open()
        await exporter.write(paper, [{"galaxy_name": "NGC 1052-DF2", "ra": 40.445, "dec": -8.403}])
        await exporter.flush()
        await exporter.aclose()

    asyncio.run(export())
    catalogue = build_sorted_catalogue(catalogue_config, lambda _message: None)

    assert catalogue.loc[0, "dec"] == -8.403
    assert catalogue.loc[0, "constellation"] == "Cetus"
    assert catalogue.loc[0, "source_papers"] == "2401.00001"
