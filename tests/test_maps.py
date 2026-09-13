import numpy as np
import pandas as pd
import pytest

from udg_catalogue.maps import (
    DARK_MATTER_COLOR_COLUMN,
    HOVER_COLUMNS,
    build_3d_figure,
    cluster_label,
    prepare_map_frame,
    write_3d_map,
)


def sample_catalogue():
    return pd.DataFrame(
        {
            "galaxy_name": ["A", "B", "C"],
            "ra": [0.0, 90.0, 10.0],
            "dec": [0.0, 0.0, np.nan],
            "distance_mpc": [4.0, 9.0, 1.0],
            "effective_radius_kpc": [4.0, np.nan, 1.0],
            "stellar_mass_solar": [2.5e8, np.nan, 1.0],
            "dark_matter_fraction": [1.2, np.nan, 0.5],
            "completeness_pct": [100.0, 50.0, 0.0],
            "constellation": ["Pisces", np.nan, "Lyra"],
            "cluster_id": [3, -1, 0],
        }
    )


def test_prepare_map_frame_positions_sizes_and_hover_text():
    frame = prepare_map_frame(sample_catalogue())

    assert frame["galaxy_name"].tolist() == ["A", "B"]
    np.testing.assert_allclose(frame[["x", "y", "z"]].to_numpy(), [[2.0, 0.0, 0.0], [0.0, 3.0, 0.0]], atol=1e-12)
    first, second = frame.iloc[0], frame.iloc[1]
    assert first["size_visual"] == 10.0
    assert second["size_visual"] == 5.0
    assert first["dark_matter_fraction"] == 1.0
    assert first[DARK_MATTER_COLOR_COLUMN] == 1.0
    assert second[DARK_MATTER_COLOR_COLUMN] == 0.0
    assert [first[column] for column in HOVER_COLUMNS] == [
        "Pisces",
        "Cluster #3",
        "100.0%",
        "0.0000°",
        "0.0000°",
        "4.00 Mpc",
        "4.00 kpc",
        "2.50e+08 M☉",
        "100.0%",
    ]
    assert [second[column] for column in HOVER_COLUMNS] == [
        "Unknown",
        "Single / Unclustered",
        "50.0%",
        "90.0000°",
        "0.0000°",
        "9.00 Mpc",
        "N/A",
        "N/A",
        "N/A",
    ]


def test_prepare_map_frame_without_spatial_columns_is_empty():
    assert prepare_map_frame(pd.DataFrame({"galaxy_name": ["A"], "ra": [1.0]})).empty


def test_prepare_map_frame_drops_negative_distances():
    frame = pd.DataFrame({"galaxy_name": ["A"], "ra": [1.0], "dec": [1.0], "distance_mpc": [-3.0]})

    assert prepare_map_frame(frame).empty


def test_build_3d_figure_carries_hover_template_and_point_count():
    figure = build_3d_figure(prepare_map_frame(sample_catalogue()))

    assert figure.layout.title.text == "3D Distribution of Ultra-Diffuse Galaxies (N = 2)"
    assert figure.data[0].hovertemplate.startswith("<b>%{hovertext}</b>")
    assert len(figure.data[0].x) == 2


def test_write_3d_map_writes_html_only_when_galaxies_are_located(tmp_path):
    destination = tmp_path / "map.html"
    skipped = tmp_path / "skipped.html"
    messages = []

    assert write_3d_map(sample_catalogue(), destination, messages.append)
    assert not write_3d_map(pd.DataFrame({"galaxy_name": []}), skipped, messages.append)

    assert "plotly" in destination.read_text(encoding="utf-8").lower()
    assert not skipped.exists()
    assert messages == [
        f"3D map written to {destination}",
        "3D map skipped: no galaxies have RA, Dec and distance",
    ]


@pytest.mark.parametrize(
    ("cluster_id", "expected"),
    [(-1, "Single / Unclustered"), (np.nan, "Single / Unclustered"), (2.0, "Cluster #2")],
)
def test_cluster_label(cluster_id, expected):
    assert cluster_label(cluster_id) == expected
