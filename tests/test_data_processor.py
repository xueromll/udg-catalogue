import pytest
import pandas as pd
import numpy as np
import sys
from astropy.coordinates import SkyCoord
import astropy.units as u

from data_processor import (
    universal_normalize_name, load_processed_ids, save_processed_id,
    is_valid_galaxy, clean_duplicates, upsert_to_csv, calculate_completeness,
    assign_constellations, assign_3d_clusters, assign_quality_flag, process_database
)

@pytest.mark.parametrize("name, expected", [
    ("DF 44", "dragonfly44"),
    ("df-44", "dragonfly44"),
    ("DF044", "dragonfly44"),
    ("VCC 1234", "vcc1234"),
    (None, ""),
    (float('nan'), ""),
    ("", "")
])
def test_universal_normalize_name(name, expected):
    assert universal_normalize_name(name) == expected

def test_load_processed_ids_missing_file(mocker):
    mocker.patch('os.path.isfile', return_value=False)
    assert load_processed_ids() == set()

def test_load_processed_ids_success(mocker):
    mocker.patch('os.path.isfile', return_value=True)
    mock_file = mocker.mock_open(read_data="http://arxiv.org/abs/1234\nhttp://arxiv.org/pdf/5678.pdf\n\n9999\n")
    mocker.patch('builtins.open', mock_file)
    
    assert load_processed_ids() == {"1234", "5678", "9999"}

def test_load_processed_ids_exception(mocker):
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch('builtins.open', side_effect=Exception("IO Error"))
    assert load_processed_ids() == set()

def test_save_processed_id(mocker):
    mock_file = mocker.mock_open()
    mocker.patch('builtins.open', mock_file)
    
    save_processed_id("1234")
    mock_file().write.assert_called_once_with("1234\n")

@pytest.mark.parametrize("galaxy_data, expected", [
    ({"galaxy_name": "Dragonfly 44", "ra": 10.0, "dec": -10.0}, True),
    ({"galaxy_name": "illustris_galaxy_1", "ra": 10.0}, False),
    ({"galaxy_name": "mock_catalog_obj", "ra": 10.0}, False),
    ({"galaxy_name": "DF 1", "ra": 400.0, "dec": 0.0}, False),
    ({"galaxy_name": "DF 2", "ra": 10.0, "dec": -100.0}, False),
    ({"galaxy_name": "DF 3", "ra": "invalid", "dec": 0.0}, False),
    ({"galaxy_name": "DF 4", "ra": 10.0, "dec": "invalid"}, False),
    ({"galaxy_name": "NaN", "ra": 10.0}, False),
    ({"galaxy_name": "ValidName"}, False),
    (None, False),
    ({}, False)
])
def test_is_valid_galaxy(galaxy_data, expected):
    assert is_valid_galaxy(galaxy_data) is expected

def test_clean_duplicates_missing_file(mocker):
    mocker.patch('os.path.isfile', return_value=False)
    clean_duplicates("dummy.csv")

def test_clean_duplicates_empty_df(mocker):
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch('shutil.copyfile')
    mocker.patch('pandas.read_csv', return_value=pd.DataFrame())
    clean_duplicates("dummy.csv")

def test_clean_duplicates_logic(mocker):
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch('shutil.copyfile')
    
    df = pd.DataFrame({
        "galaxy_name": ["G1", "G1_dup", "G2"],
        "ra": [10.0, 10.0001, 50.0],
        "dec": [20.0, 20.0001, -30.0],
        "distance_mpc": [None, 15.0, 10.0]
    })
    mocker.patch('pandas.read_csv', return_value=df)
    
    saved_dfs = []
    mocker.patch('pandas.DataFrame.to_csv', new=lambda self, *args, **kwargs: saved_dfs.append(self))
    
    clean_duplicates("dummy.csv")
    
    assert len(saved_dfs) > 0
    saved_df = saved_dfs[-1]
    
    assert len(saved_df) == 2
    merged_g1 = saved_df[saved_df["galaxy_name"] == "G1"]
    assert merged_g1["distance_mpc"].iloc[0] == 15.0

def test_clean_duplicates_orig_i_less_than_orig_j(mocker):
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch('shutil.copyfile')
    df = pd.DataFrame({
        "galaxy_name": ["Target_A", "Target_B"],
        "ra": [10.0, 10.0001],
        "dec": [20.0, 20.0001],
        "distance_mpc": [None, 50.0]
    })
    mocker.patch('pandas.read_csv', return_value=df)
    
    saved_dfs = []
    mocker.patch('pandas.DataFrame.to_csv', new=lambda self, *args, **kwargs: saved_dfs.append(self))
    
    clean_duplicates("dummy.csv", max_sep_arcsec=3.0)
    
    assert len(saved_dfs) > 0
    saved_df = saved_dfs[-1]
    assert len(saved_df) == 1
    assert saved_df["distance_mpc"].iloc[0] == 50.0

def test_clean_duplicates_single_valid_coord(mocker):
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch('shutil.copyfile')
    df = pd.DataFrame({
        "galaxy_name": ["G1", "G2"],
        "ra": [10.0, np.nan],
        "dec": [20.0, np.nan]
    })
    mocker.patch('pandas.read_csv', return_value=df)
    
    saved_dfs = []
    mocker.patch('pandas.DataFrame.to_csv', new=lambda self, *args, **kwargs: saved_dfs.append(self))
    
    clean_duplicates("dummy.csv")
    assert len(saved_dfs[-1]) == 2

def test_clean_duplicates_exception(mocker):
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch('shutil.copyfile', side_effect=Exception("Copy failed"))
    clean_duplicates("dummy.csv")

def test_upsert_to_csv_empty(mocker):
    mock_read = mocker.patch('pandas.read_csv')
    upsert_to_csv([])
    mock_read.assert_not_called()

def test_upsert_to_csv_no_file(mocker):
    mocker.patch('os.path.isfile', return_value=False)
    saved_dfs = []
    mocker.patch('pandas.DataFrame.to_csv', new=lambda self, *args, **kwargs: saved_dfs.append(self))
    
    upsert_to_csv([{"galaxy_name": "New G", "ra": 10.0, "dec": 20.0, "distance_mpc": 5.0}])
    
    assert len(saved_dfs) == 1
    assert len(saved_dfs[0]) == 1

def test_upsert_to_csv_empty_file(mocker):
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch('os.path.getsize', return_value=0)
    saved_dfs = []
    mocker.patch('pandas.DataFrame.to_csv', new=lambda self, *args, **kwargs: saved_dfs.append(self))
    
    upsert_to_csv([{"galaxy_name": "New G", "ra": 10.0, "dec": 20.0, "distance_mpc": 5.0}])
    
    assert len(saved_dfs) == 1
    assert len(saved_dfs[0]) == 1

def test_upsert_to_csv_invalid_numeric_update(mocker):
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch('os.path.getsize', return_value=100)
    existing_df = pd.DataFrame({"galaxy_name": ["Dragonfly 44"], "ra": [None]})
    mocker.patch('pandas.read_csv', return_value=existing_df)
    
    saved_dfs = []
    mocker.patch('pandas.DataFrame.to_csv', new=lambda self, *args, **kwargs: saved_dfs.append(self))
    
    upsert_to_csv([{"galaxy_name": "Dragonfly 44", "ra": "invalid_string"}])
    
    assert len(saved_dfs) == 1
    assert pd.isna(saved_dfs[0]["ra"].iloc[0])

def test_upsert_to_csv_no_galaxy_name(mocker):
    mocker.patch('os.path.isfile', return_value=False)
    saved_dfs = []
    mocker.patch('pandas.DataFrame.to_csv', new=lambda self, *args, **kwargs: saved_dfs.append(self))
    
    upsert_to_csv([{"galaxy_name": None, "ra": 10.0}, {"galaxy_name": "", "ra": 20.0}])
    
    assert len(saved_dfs) == 1
    assert len(saved_dfs[0]) == 0

def test_upsert_to_csv_logic(mocker):
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch('os.path.getsize', return_value=100)
    
    existing_df = pd.DataFrame({
        "galaxy_name": ["Dragonfly 44"],
        "ra": [10.0],
        "dark_matter_fraction": [0.5]
    })
    mocker.patch('pandas.read_csv', return_value=existing_df)
    
    saved_dfs = []
    mocker.patch('pandas.DataFrame.to_csv', new=lambda self, *args, **kwargs: saved_dfs.append(self))
    
    records = [
        {"galaxy_name": "DF 44", "dec": 20.0, "dark_matter_fraction": 1.5, "ra": 10.0},
        {"galaxy_name": "New UDG", "ra": 100.0, "dec": -50.0, "dark_matter_fraction": 0.8},
        {"galaxy_name": "InvalidType", "ra": "bad", "dec": 10.0}
    ]
    
    upsert_to_csv(records)
    
    assert len(saved_dfs) > 0
    saved_df = saved_dfs[-1]
    assert len(saved_df) == 2
    
    df44 = saved_df[saved_df["galaxy_name"] == "Dragonfly 44"].iloc[0]
    assert df44["dec"] == 20.0
    assert df44["dark_matter_fraction"] == 0.5
    
    new_udg = saved_df[saved_df["galaxy_name"] == "New UDG"].iloc[0]
    assert new_udg["ra"] == 100.0
    assert new_udg["dark_matter_fraction"] == 0.8

def test_calculate_completeness():
    df = pd.DataFrame({
        "ra": [10.0, None],
        "dec": [20.0, -10.0],
        "distance_mpc": [5.0, None],
        "effective_radius_kpc": [2.0, 1.5],
        "stellar_mass_solar": [1e8, None],
        "dark_matter_fraction": [0.99, None]
    })
    result = calculate_completeness(df)
    assert result["completeness_pct"].iloc[0] == 100.0
    assert result["completeness_pct"].iloc[1] == 33.3

def test_calculate_completeness_no_fields():
    df = pd.DataFrame({"random_col": [1]})
    result = calculate_completeness(df)
    assert result["completeness_pct"].iloc[0] == 0

def test_assign_constellations():
    df = pd.DataFrame({
        "ra": [83.633],
        "dec": [-5.361]
    })
    result = assign_constellations(df)
    assert result["constellation"].iloc[0] == "Orion"

def test_assign_constellations_returns_none(mocker):
    df = pd.DataFrame({"ra": [10.0], "dec": [20.0]})
    mock_coords = mocker.MagicMock()
    mock_coords.get_constellation.return_value = [None]
    mocker.patch('data_processor.SkyCoord', return_value=mock_coords)
    
    result = assign_constellations(df)
    assert result["constellation"].iloc[0] is None

def test_assign_constellations_astropy_exception(mocker):
    df = pd.DataFrame({"ra": [10.0], "dec": [20.0]})
    mocker.patch('data_processor.SkyCoord', side_effect=Exception("Astropy err"))
    
    mock_loader = mocker.patch('skyfield.api.Loader')
    result = assign_constellations(df)
    
    assert result["constellation"].iloc[0] == "Unknown"
    mock_loader.assert_called_once()

def test_assign_constellations_skyfield_import_error(mocker):
    df = pd.DataFrame({"ra": [10.0], "dec": [20.0]})
    mocker.patch('data_processor.SkyCoord', side_effect=Exception("Astropy err"))
    mocker.patch.dict('sys.modules', {'skyfield.api': None})
    
    result = assign_constellations(df)
    assert result["constellation"].iloc[0] == "Unknown"

def test_assign_constellations_skyfield_exception(mocker):
    df = pd.DataFrame({"ra": [10.0], "dec": [20.0]})
    mocker.patch('data_processor.SkyCoord', side_effect=Exception("Astropy err"))
    mocker.patch('skyfield.api.Loader', side_effect=Exception("Skyfield err"))
    
    result = assign_constellations(df)
    assert result["constellation"].iloc[0] == "Unknown"

def test_assign_constellations_no_coords():
    df = pd.DataFrame({"ra": [np.nan], "dec": [np.nan]})
    result = assign_constellations(df)
    assert result["constellation"].iloc[0] == "Unknown"

def test_assign_3d_clusters():
    df = pd.DataFrame({
        "ra": [10.0, 10.1, 100.0, np.nan],
        "dec": [20.0, 20.1, -50.0, 10.0],
        "distance_mpc": [15.0, 15.1, 80.0, 10.0]
    })
    result = assign_3d_clusters(df, max_dist_mpc=2.0, min_samples=2)
    
    clusters = result["cluster_id"].tolist()
    assert clusters[0] == clusters[1]
    assert clusters[0] != -1
    assert clusters[2] == -1
    assert clusters[3] == -1

def test_assign_3d_clusters_exact_min_samples():
    df = pd.DataFrame({
        "ra": [10.0, 10.1],
        "dec": [20.0, 20.1],
        "distance_mpc": [15.0, 15.1]
    })
    result = assign_3d_clusters(df, max_dist_mpc=2.0, min_samples=2)
    assert len(result["cluster_id"].unique()) == 1
    assert result["cluster_id"].iloc[0] != -1

def test_assign_3d_clusters_low_samples():
    df = pd.DataFrame({"ra": [10.0], "dec": [20.0], "distance_mpc": [15.0]})
    result = assign_3d_clusters(df, min_samples=5)
    assert result["cluster_id"].iloc[0] == -1

def test_assign_quality_flag():
    df = pd.DataFrame({"completeness_pct": [100.0, 50.0, 49.9, np.nan]})
    result = assign_quality_flag(df)
    flags = result["quality_flag"].tolist()
    assert flags == ["Confirmed", "Needs Review", "Low Confidence", "Low Confidence"]

def test_process_database_missing_file(mocker):
    mocker.patch('os.path.isfile', return_value=False)
    mock_read = mocker.patch('pandas.read_csv')
    process_database()
    mock_read.assert_not_called()

def test_process_database_empty(mocker):
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch('pandas.read_csv', return_value=pd.DataFrame())
    mock_to_csv = mocker.patch('pandas.DataFrame.to_csv')
    process_database()
    mock_to_csv.assert_not_called()

def test_process_database_no_key_fields(mocker):
    mocker.patch('os.path.isfile', return_value=True)
    df = pd.DataFrame({"galaxy_name": ["G1"], "some_col": [1]})
    mocker.patch('pandas.read_csv', return_value=df)
    
    saved_dfs = []
    mocker.patch('pandas.DataFrame.to_csv', new=lambda self, *args, **kwargs: saved_dfs.append(self))
    
    process_database()
    assert saved_dfs[-1]["completeness_pct"].iloc[0] == 0.0

def test_process_database_full(mocker):
    mocker.patch('os.path.isfile', return_value=True)
    
    df = pd.DataFrame({
        "galaxy_name": ["G1", "G2"],
        "ra": [10.0, 20.0],
        "dec": [10.0, 20.0],
        "distance_mpc": [5.0, 10.0],
        "dark_matter_fraction": [0.5, 1.5]
    })
    
    mocker.patch('pandas.read_csv', return_value=df)
    
    saved_dfs = []
    mocker.patch('pandas.DataFrame.to_csv', new=lambda self, *args, **kwargs: saved_dfs.append(self))

    process_database()

    assert len(saved_dfs) > 0
    saved_df = saved_dfs[0]
    
    assert saved_df["dark_matter_fraction"].iloc[0] <= 1.0
    assert saved_df["dark_matter_fraction"].iloc[1] <= 1.0
    assert "completeness_pct" in saved_df.columns
    assert "quality_flag" in saved_df.columns
    assert "constellation" in saved_df.columns
    assert "cluster_id" in saved_df.columns