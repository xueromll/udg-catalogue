import numpy as np
import pandas as pd
import pytest
from sci_etl_core.processors import ClusteringStep, DeduplicationStep

from udg_catalogue.astrometry import (
    CartesianDistanceFeatures,
    ConstellationStep,
    NamesakeSplitStep,
    SkyPositionMatcher,
    cartesian_coordinates,
    cross_match_catalogues,
    located_rows,
)


def test_located_rows_requires_both_coordinates_within_range():
    frame = pd.DataFrame(
        {"ra": [10.0, 400.0, np.nan, 20.0, "bad"], "dec": [0.0, 0.0, 0.0, -95.0, 1.0]}
    )

    assert located_rows(frame).tolist() == [True, False, False, False, False]


def test_located_rows_without_coordinate_columns():
    assert not located_rows(pd.DataFrame({"ra": [1.0]})).any()


def test_cartesian_coordinates_on_the_axes():
    points = cartesian_coordinates([0.0, 90.0, 0.0], [0.0, 0.0, 90.0], [2.0, 3.0, 4.0])

    np.testing.assert_allclose(points, [[2.0, 0.0, 0.0], [0.0, 3.0, 0.0], [0.0, 0.0, 4.0]], atol=1e-12)


def test_sky_position_matcher_pairs_close_neighbours_once():
    frame = pd.DataFrame({"ra": [15.0, 15.0001, 35.0, np.nan], "dec": [30.0, 30.0001, -10.0, 0.0]})

    assert SkyPositionMatcher().find_matches(frame, threshold=3.0) == [(0, 1)]


def test_sky_position_matcher_pairs_rows_at_identical_coordinates():
    frame = pd.DataFrame({"ra": [15.0, 15.0, 35.0], "dec": [30.0, 30.0, -10.0]})

    assert SkyPositionMatcher().find_matches(frame, threshold=3.0) == [(0, 1)]


def test_sky_position_matcher_groups_every_row_of_a_triplet():
    frame = pd.DataFrame({"ra": [15.0, 15.0003, 15.0, 80.0], "dec": [30.0, 30.0, 30.0005, 5.0]})

    assert SkyPositionMatcher().find_matches(frame, threshold=3.0) == [(0, 1), (0, 2)]


def test_sky_position_matcher_joins_a_chain_of_close_rows_into_one_group():
    step = 2.5 / 3600
    frame = pd.DataFrame({"ra": [15.0, 15.0 + step, 15.0 + 2 * step], "dec": [0.0, 0.0, 0.0]}, index=[7, 3, 5])

    assert SkyPositionMatcher().find_matches(frame, threshold=3.0) == [(3, 5), (3, 7)]


def test_sky_position_matcher_ignores_pairs_beyond_threshold():
    frame = pd.DataFrame({"ra": [10.0, 10.005], "dec": [20.0, 20.005]})

    assert SkyPositionMatcher().find_matches(frame, threshold=1.0) == []


def test_sky_position_matcher_needs_two_located_rows():
    assert SkyPositionMatcher().find_matches(pd.DataFrame({"ra": [1.0], "dec": [1.0]}), 3.0) == []


def test_sky_deduplication_fills_gaps_from_the_merged_row():
    frame = pd.DataFrame(
        {
            "_norm_key": ["target1", "target1dup", "target2"],
            "galaxy_name": ["Target_1", "Target_1_Dup", "Target_2_Isolated"],
            "ra": [15.0, 15.0001, 35.0],
            "dec": [30.0, 30.0001, -10.0],
            "distance_mpc": [np.nan, 45.5, 12.0],
            "stellar_mass_solar": [1e9, np.nan, 5e8],
            "dark_matter_fraction": [0.9, 0.95, 0.3],
        }
    )

    merged = DeduplicationStep("_norm_key", matcher=SkyPositionMatcher(), match_threshold=3.0).process(frame)

    assert merged["galaxy_name"].tolist() == ["Target_1", "Target_2_Isolated"]
    target = merged.iloc[0]
    assert target["distance_mpc"] == 45.5
    assert target["stellar_mass_solar"] == 1e9
    assert target["dark_matter_fraction"] == 0.9


def test_cartesian_distance_features_use_fully_located_rows_only():
    frame = pd.DataFrame(
        {"ra": [10.0, 10.1, np.nan], "dec": [20.0, 20.1, 10.0], "distance_mpc": [15.0, np.nan, 10.0]},
        index=[5, 6, 7],
    )

    features, index = CartesianDistanceFeatures().extract(frame)

    assert index.tolist() == [5]
    assert features.shape == (1, 3)


def test_cartesian_distance_features_without_distance_column():
    features, index = CartesianDistanceFeatures().extract(pd.DataFrame({"ra": [1.0], "dec": [1.0]}))

    assert features.shape == (0, 3)
    assert len(index) == 0


def test_clustering_groups_nearby_galaxies_in_three_dimensions():
    frame = pd.DataFrame(
        {
            "ra": [10.0, 10.1, 100.0, np.nan],
            "dec": [20.0, 20.1, -50.0, 10.0],
            "distance_mpc": [15.0, 15.1, 80.0, 10.0],
        }
    )

    clusters = ClusteringStep(CartesianDistanceFeatures(), eps=2.0, min_samples=2).process(frame)["cluster_id"].tolist()

    assert clusters[0] == clusters[1] != -1
    assert clusters[2] == -1
    assert clusters[3] == -1


def test_constellation_step_names_located_galaxies_only():
    frame = pd.DataFrame({"ra": [83.633, np.nan, 83.633], "dec": [-5.361, 0.0, 120.0]})

    assert ConstellationStep().process(frame)["constellation"].tolist() == ["Orion", "Unknown", "Unknown"]


def test_constellation_step_without_coordinates():
    frame = pd.DataFrame({"galaxy_name": ["G1"]})

    assert ConstellationStep().process(frame)["constellation"].tolist() == ["Unknown"]


def test_cross_match_returns_matched_rows_with_separation():
    ours = pd.DataFrame({"galaxy_name": ["A", "B", "C"], "ra": [10.0, 50.0, np.nan], "dec": [20.0, -30.0, 0.0]})
    reference = pd.DataFrame({"ra": [10.0002, 200.0], "dec": [20.0, 10.0]})

    matched = cross_match_catalogues(ours, reference, max_separation_arcsec=3.0)

    assert matched["galaxy_name"].tolist() == ["A"]
    assert matched["matched_with_ref"].all()
    expected_arcsec = 0.0002 * 3600 * np.cos(np.deg2rad(20.0))
    assert matched["separation_arcsec"].iloc[0] == pytest.approx(expected_arcsec, rel=1e-3)


def test_cross_match_with_empty_reference_returns_empty_frame():
    ours = pd.DataFrame({"galaxy_name": ["A"], "ra": [10.0], "dec": [20.0]})

    matched = cross_match_catalogues(ours, pd.DataFrame({"ra": [], "dec": []}))

    assert matched.empty
    assert {"separation_arcsec", "matched_with_ref"}.issubset(matched.columns)


def namesakes(**columns):
    return pd.DataFrame({"_norm_key": ["udg5"] * len(next(iter(columns.values()))), **columns})


def test_namesakes_in_different_fields_become_different_galaxies():
    frame = namesakes(
        ra=[159.03, 234.39, 159.0301],
        dec=[-27.32, 58.58, -27.3201],
        distance_mpc=[51.0, 42.7, 51.0],
    )

    assert NamesakeSplitStep("_norm_key").process(frame)["_norm_key"].tolist() == ["udg5", "udg5#1", "udg5"]


def test_a_namesake_without_a_position_joins_the_galaxy_its_distance_agrees_with():
    frame = namesakes(
        ra=[194.79, 40.445, np.nan, np.nan],
        dec=[29.007, -8.403, np.nan, np.nan],
        distance_mpc=[100.0, 20.0, 22.1, 98.0],
    )

    assert NamesakeSplitStep("_norm_key").process(frame)["_norm_key"].tolist() == ["udg5", "udg5#1", "udg5#1", "udg5"]


def test_the_closest_agreeing_distance_wins_over_a_galaxy_without_a_distance():
    frame = namesakes(
        ra=[10.0, 50.0, 90.0, np.nan],
        dec=[0.0, 0.0, 0.0, np.nan],
        distance_mpc=[np.nan, 70.0, 100.0, 95.0],
    )

    assert NamesakeSplitStep("_norm_key").process(frame)["_norm_key"].tolist() == ["udg5", "udg5#1", "udg5#2", "udg5#2"]


def test_a_distance_no_galaxy_fits_joins_the_only_galaxy_without_a_distance():
    frame = namesakes(ra=[10.0, 50.0, np.nan], dec=[0.0, 0.0, np.nan], distance_mpc=[np.nan, 30.0, 95.0])

    assert NamesakeSplitStep("_norm_key").process(frame)["_norm_key"].tolist() == ["udg5", "udg5#1", "udg5"]


def test_namesakes_that_cannot_be_placed_are_kept_together_apart_from_the_rest():
    frame = namesakes(
        ra=[159.03, 234.39, np.nan, np.nan],
        dec=[-27.32, 58.58, np.nan, np.nan],
        distance_mpc=[51.0, 42.7, np.nan, 5.0],
    )

    assert NamesakeSplitStep("_norm_key").process(frame)["_norm_key"].tolist() == ["udg5", "udg5#1", "udg5#2", "udg5#2"]


def test_a_namesake_group_numbers_its_galaxies_from_its_first_row():
    frame = namesakes(ra=[np.nan, 234.39, 159.03], dec=[np.nan, 58.58, -27.32], distance_mpc=[51.0, 42.7, 51.0])

    assert NamesakeSplitStep("_norm_key").process(frame)["_norm_key"].tolist() == ["udg5", "udg5#1", "udg5"]


def test_namesakes_in_one_place_stay_one_galaxy_whatever_their_distances():
    frame = namesakes(
        ra=[40.445, 40.4453, np.nan, np.nan],
        dec=[-8.403, -8.4031, np.nan, np.nan],
        distance_mpc=[20.0, 22.1, 13.0, np.nan],
    )

    assert NamesakeSplitStep("_norm_key").process(frame) is frame


def test_namesakes_lie_together_within_the_configured_separation():
    frame = namesakes(ra=[10.0, 10.1], dec=[0.0, 0.0], distance_mpc=[20.0, 20.0])

    assert NamesakeSplitStep("_norm_key").process(frame) is frame
    split = NamesakeSplitStep("_norm_key", max_separation_arcmin=5.0).process(frame)
    assert split["_norm_key"].tolist() == ["udg5", "udg5#1"]


def test_namesake_split_leaves_unique_and_missing_keys_and_reads_no_distance_without_the_column():
    unique = pd.DataFrame({"_norm_key": ["df44", "", ""], "ra": [1.0, 2.0, 90.0], "dec": [0.0, 0.0, 0.0]})
    assert NamesakeSplitStep("_norm_key").process(unique) is unique

    frame = pd.DataFrame({"_norm_key": ["w79", "w79", "w79"], "ra": [49.59, 49.91, np.nan], "dec": [41.77, 41.20, np.nan]})
    split = NamesakeSplitStep("_norm_key").process(frame)
    assert split["_norm_key"].tolist() == ["w79", "w79#1", "w79#2"]
    assert frame["_norm_key"].tolist() == ["w79", "w79", "w79"]
