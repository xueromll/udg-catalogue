import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from udg_catalogue.maps import build_3d_figure, prepare_map_frame
from udg_catalogue.ui import charts
from udg_catalogue.ui.tokens import ACCENT, CANVAS, CATEGORICAL, INK, MUTED

CATALOGUE = pd.DataFrame(
    {
        "galaxy_name": ["DF2", "DF44", "Bad", "Tiny"],
        "stellar_mass_solar": [2e8, 3e8, "n/a", -1.0],
        "effective_radius_kpc": [2.2, 4.6, 1.0, 0.5],
        "completeness_pct": [100.0, 80.0, 20.0, 10.0],
        "ra": [40.4, 195.2, 1.0, 2.0],
        "dec": [-8.4, 26.9, 0.0, 1.0],
        "distance_mpc": [22.1, 100.0, 5.0, 7.0],
        "cluster_id": [10, -1, 3, 10],
    }
)


def test_slate_sets_the_canvas_layout_mono_ticks_and_an_optional_height():
    figure = charts.slate(go.Figure(go.Scatter(x=[1], y=[1])), height=200)

    assert figure.layout.paper_bgcolor == CANVAS
    assert figure.layout.height == 200
    assert figure.layout.coloraxis.colorscale[0][1] == "#440154"
    assert figure.layout.xaxis.tickfont.family.startswith("JetBrains Mono")
    assert charts.slate(go.Figure()).layout.height is None


def test_restyle_map_uses_one_categorical_hue_per_cluster_and_grey_for_the_unclustered():
    frame = prepare_map_frame(CATALOGUE)
    frame["cluster_label"] = frame["cluster_id"].map(charts.cluster_label)
    figure = charts.restyle_map(build_3d_figure(frame, color_column="cluster_label", color_label="Cluster", color_range=None))

    colours = {trace.name: trace.marker.color for trace in figure.data}
    assert colours[charts.UNCLUSTERED] == MUTED
    assert sorted(colour for name, colour in colours.items() if name != charts.UNCLUSTERED) == sorted(CATEGORICAL[:2])
    assert figure.layout.scene.bgcolor == CANVAS
    assert figure.layout.scene.xaxis.backgroundcolor == charts.WALL
    assert figure.layout.margin.l == 0
    assert figure.layout.title.text is None


def test_restyle_map_leaves_a_continuous_colour_axis_on_the_measure_scale():
    figure = charts.restyle_map(build_3d_figure(prepare_map_frame(CATALOGUE)))

    assert not isinstance(figure.data[0].marker.color, str)
    assert figure.layout.coloraxis.colorscale[-1][1] == "#FDE725"
    assert figure.data[0].marker.line.width == charts.OUTLINE["width"]


def test_positive_values_filters_non_numeric_and_non_positive_entries():
    assert charts.positive_values(CATALOGUE, "missing").empty
    assert charts.positive_values(CATALOGUE, "stellar_mass_solar").tolist() == [2e8, 3e8]


def test_log_histogram_draws_ink_bars_and_the_median_as_the_one_accent_rule():
    assert charts.log_histogram(pd.Series(dtype=float), "x") is None

    figure = charts.log_histogram(pd.Series([1.0, 10.0, 100.0, 1000.0]), "R_eff [kpc]", bins=3)

    assert len(figure.data) == 1
    assert figure.data[0].marker.color == INK
    assert figure.data[0].y.tolist() == [1, 1, 2]
    assert figure.layout.xaxis.type == "log"
    assert figure.layout.xaxis.title.text == "R_eff [kpc]"
    assert [shape.line.color for shape in figure.layout.shapes] == [ACCENT]
    assert figure.layout.annotations[0].text == "median 55"


def test_histograms_read_their_catalogue_columns():
    assert charts.stellar_mass_histogram(CATALOGUE).data[0].y.sum() == 2
    assert charts.effective_radius_histogram(CATALOGUE).data[0].y.sum() == 4
    assert charts.stellar_mass_histogram(pd.DataFrame()) is None


def test_mass_radius_scatter_colours_by_completeness_on_log_axes():
    figure = charts.mass_radius_scatter(CATALOGUE)

    assert list(figure.data[0].text) == ["DF2", "DF44"]
    assert list(figure.data[0].marker.color) == [100.0, 80.0]
    assert figure.layout.xaxis.type == figure.layout.yaxis.type == "log"
    assert figure.layout.coloraxis.colorbar.title.text == "completeness %"

    unnamed = charts.mass_radius_scatter(CATALOGUE.drop(columns=["galaxy_name"]))
    assert list(unnamed.data[0].text) == ["", ""]

    assert charts.mass_radius_scatter(CATALOGUE.drop(columns=["completeness_pct"])) is None
    assert charts.mass_radius_scatter(CATALOGUE.assign(stellar_mass_solar=0.0)) is None


def test_restyle_map_draws_galaxies_without_the_measure_in_grey_instead_of_as_zero():
    frame = pd.DataFrame({"x": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 2.0], "z": [0.0, 1.0, 2.0], "m": [0.5, float("nan"), 1.0], "s": [3, 4, 5]})
    figure = px.scatter_3d(frame, x="x", y="y", z="z", color="m", size="s", custom_data=["s"])

    charts.restyle_map(figure)

    measured, grey = figure.data
    assert measured.x[0] == 0.0 and len(measured.x) == 2 and list(measured.marker.color) == [0.5, 1.0] and list(measured.marker.size) == [3, 5]
    assert list(grey.x) == [1.0] and grey.marker.color == MUTED and list(grey.marker.size) == [4]
    assert grey.name == charts.NO_VALUE and grey.showlegend is True and grey.marker.coloraxis is None
    assert [list(row) for row in grey.customdata] == [[4]]
    assert charts.split_missing(measured) is None
    assert all(trace.marker.line.color == charts.OUTLINE["color"] and trace.marker.line.width > 0 for trace in figure.data)


def test_pull_in_outliers_pins_far_points_to_the_quantile_radius_and_keeps_their_direction():
    figure = go.Figure(go.Scatter3d(x=[1.0, 0.0, 0.0, 30.0], y=[0.0, 2.0, 0.0, 40.0], z=[0.0, 0.0, 0.0, 0.0]))

    charts.pull_in_outliers(figure, quantile=0.5)

    trace = figure.data[0]
    np.testing.assert_allclose(list(trace.x), [1.0, 0.0, 0.0, 0.9])
    np.testing.assert_allclose(list(trace.y), [0.0, 1.5, 0.0, 1.2])
    assert list(trace.z) == [0.0, 0.0, 0.0, 0.0]


def test_px_discrete_figures_colour_the_six_largest_groups_and_fold_the_rest_off_the_legend():
    frame = pd.DataFrame({"x": range(9), "y": range(9), "z": range(9), "c": ["big", "big", *(str(i) for i in range(7))]})
    figure = px.scatter_3d(frame, x="x", y="y", z="z", color="c")

    charts.restyle_map(figure)

    by_name = {trace.name: trace for trace in figure.data}
    assert by_name["big"].marker.color == CATEGORICAL[0]
    assert [by_name[str(i)].marker.color for i in range(5)] == list(CATEGORICAL[1:])
    assert by_name["5"].marker.color == by_name["6"].marker.color == charts.OTHER
    assert by_name["6"].showlegend is False and by_name["big"].showlegend is True
