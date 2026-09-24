import numpy as np
import pandas as pd

from udg_catalogue.postprocess import (
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
            "galaxy_name": ["Alpha", "Beta", "Beta copy", "Gamma"],
            "ra": [83.633, 10.0, 10.0001, 10.1],
            "dec": [-5.361, 20.0, 20.0001, 20.1],
            "distance_mpc": [5.0, 15.0, np.nan, 15.1],
            "effective_radius_kpc": [2.0, np.nan, np.nan, np.nan],
            "stellar_mass_solar": [1e8, np.nan, 3e7, np.nan],
            "dark_matter_fraction": [1.5, 0.5, np.nan, np.nan],
        }
    )

    catalogue = build_catalogue_chain(catalogue_config).process(raw)
    rows = catalogue.set_index("galaxy_name")

    assert "_norm_key" not in catalogue.columns
    assert rows.index.tolist() == ["Alpha", "Beta", "Gamma"]
    assert rows.loc["Alpha", "dark_matter_fraction"] == 1.0
    assert rows.loc["Alpha", "completeness_pct"] == 100.0
    assert rows.loc["Alpha", "quality_flag"] == "Confirmed"
    assert rows.loc["Alpha", "constellation"] == "Orion"
    assert rows.loc["Alpha", "cluster_id"] == -1
    assert rows.loc["Beta", "stellar_mass_solar"] == 3e7
    assert rows.loc["Beta", "completeness_pct"] == 83.3
    assert rows.loc["Beta", "cluster_id"] == rows.loc["Gamma", "cluster_id"] != -1
    assert rows.loc["Gamma", "quality_flag"] == "Needs Review"


def test_build_sorted_catalogue_writes_the_sorted_file(catalogue_config):
    catalogue_config.paths.raw_catalogue.write_text(
        "galaxy_name,ra,dec,distance_mpc\nBeta,10.0,20.0,\nNA,83.633,-5.361,5.0\n",
        encoding="utf-8",
    )
    messages = []

    catalogue = build_sorted_catalogue(catalogue_config, messages.append)

    written = read_catalogue(catalogue_config.paths.sorted_catalogue)
    assert written["galaxy_name"].tolist() == ["NA", "Beta"]
    assert len(catalogue) == 2
    assert messages[-1] == f"Sorted catalogue written to {catalogue_config.paths.sorted_catalogue}"
    assert [path.name for path in catalogue_config.paths.sorted_catalogue.parent.glob("*.tmp")] == []


def test_build_sorted_catalogue_skips_missing_or_empty_sources(catalogue_config):
    messages = []
    raw = catalogue_config.paths.raw_catalogue

    assert build_sorted_catalogue(catalogue_config, messages.append) is None
    raw.write_text("", encoding="utf-8")
    assert build_sorted_catalogue(catalogue_config, messages.append) is None
    raw.write_text("galaxy_name,ra\n", encoding="utf-8")
    assert build_sorted_catalogue(catalogue_config, messages.append) is None

    assert not catalogue_config.paths.sorted_catalogue.exists()
    assert len(messages) == 3


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
