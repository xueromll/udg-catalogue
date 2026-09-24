import numpy as np
import pandas as pd

from udg_catalogue.postprocess import (
    CatalogueLayoutStep,
    ValueClipStep,
    build_catalogue_chain,
    build_sorted_catalogue,
    describe_catalogue,
    read_catalogue,
)


def test_value_clip_step_bounds_present_columns_without_mutating_input():
    frame = pd.DataFrame({"dark_matter_fraction": [1.5, -0.2, 0.4, np.nan]})

    clipped = ValueClipStep({"dark_matter_fraction": (0.0, 1.0), "absent": (0.0, 1.0)}).process(frame)

    assert clipped["dark_matter_fraction"].tolist()[:3] == [1.0, 0.0, 0.4]
    assert np.isnan(clipped["dark_matter_fraction"].iloc[3])
    assert frame["dark_matter_fraction"].iloc[0] == 1.5


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

    laid_out = CatalogueLayoutStep().process(frame)

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
    assert CatalogueLayoutStep().process(pd.DataFrame({"other": [2, 1]}))["other"].tolist() == [2, 1]


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


def test_build_sorted_catalogue_merges_the_existing_catalogue(catalogue_config):
    catalogue_config.paths.sorted_catalogue.write_text(
        "galaxy_name,completeness_pct,quality_flag,constellation,cluster_id,ra,dec,distance_mpc\n"
        "Kept,33.3,Low Confidence,Orion,-1,83.633,-5.361,\n"
        "Beta,16.7,Low Confidence,Unknown,-1,,,7.0\n",
        encoding="utf-8",
    )
    catalogue_config.paths.raw_catalogue.write_text(
        "galaxy_name,ra,dec,distance_mpc\nBeta,10.0,20.0,\n",
        encoding="utf-8",
    )
    messages = []

    catalogue = build_sorted_catalogue(catalogue_config, messages.append)

    rows = read_catalogue(catalogue_config.paths.sorted_catalogue).set_index("galaxy_name")
    assert sorted(rows.index) == ["Beta", "Kept"]
    assert rows.loc["Beta", "ra"] == 10.0
    assert rows.loc["Beta", "distance_mpc"] == 7.0
    assert rows.loc["Beta", "completeness_pct"] == 100.0
    assert len(catalogue) == 2
    assert messages[-1] == f"Sorted catalogue written to {catalogue_config.paths.sorted_catalogue}"


def test_build_sorted_catalogue_refuses_to_shrink_the_existing_catalogue(catalogue_config):
    existing = (
        "galaxy_name,completeness_pct,quality_flag,constellation,cluster_id,ra,dec\n"
        "Beta,33.3,Low Confidence,Taurus,-1,10.0,20.0\n"
        "Beta copy,33.3,Low Confidence,Taurus,-1,10.0001,20.0001\n"
    )
    catalogue_config.paths.sorted_catalogue.write_text(existing, encoding="utf-8")
    catalogue_config.paths.raw_catalogue.write_text("galaxy_name,ra,dec\nBeta,10.0,20.0\n", encoding="utf-8")
    messages = []

    catalogue = build_sorted_catalogue(catalogue_config, messages.append)

    assert catalogue["galaxy_name"].tolist() == ["Beta", "Beta copy"]
    assert catalogue_config.paths.sorted_catalogue.read_text(encoding="utf-8") == existing
    assert messages == [
        f"Refusing to overwrite {catalogue_config.paths.sorted_catalogue}: the rebuilt catalogue has 1 galaxies "
        "but the existing one has 2. Move the existing file aside to rebuild from scratch."
    ]


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
