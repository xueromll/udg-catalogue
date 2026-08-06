import pytest
import pandas as pd
from data_processor import clean_duplicates

def test_cross_match_astrometry_merging(mocker):
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch('shutil.copyfile')
    
    df = pd.DataFrame({
        "galaxy_name": ["Target_1", "Target_1_Dup", "Target_2_Isolated"],
        "ra": [15.000000, 15.000100, 35.000000],
        "dec": [30.000000, 30.000100, -10.000000],
        "distance_mpc": [None, 45.5, 12.0],
        "stellar_mass_solar": [1e9, None, 5e8],
        "dark_matter_fraction": [0.9, 0.95, 0.3]
    })
    
    mocker.patch('pandas.read_csv', return_value=df)
    
    saved_dfs = []
    def mock_to_csv_side_effect(self, *args, **kwargs):
        saved_dfs.append(self)

    mocker.patch('pandas.DataFrame.to_csv', new=mock_to_csv_side_effect)
    
    clean_duplicates("test_db.csv", max_sep_arcsec=3.0)
    
    assert len(saved_dfs) > 0, "to_csv was not called"
    saved_df = saved_dfs[-1]
    
    assert len(saved_df) == 2
    
    merged_row = saved_df[saved_df["galaxy_name"] == "Target_1"].iloc[0]
    assert merged_row["distance_mpc"] == 45.5
    assert merged_row["stellar_mass_solar"] == 1e9
    assert merged_row["dark_matter_fraction"] == 0.9
    
    assert "Target_1_Dup" not in saved_df["galaxy_name"].values

def test_cross_match_no_merging_outside_radius(mocker):
    mocker.patch('os.path.isfile', return_value=True)
    mocker.patch('shutil.copyfile')
    
    df = pd.DataFrame({
        "galaxy_name": ["Galaxy_A", "Galaxy_B"],
        "ra": [10.000, 10.005],
        "dec": [20.000, 20.005]
    })
    
    mocker.patch('pandas.read_csv', return_value=df)
    
    saved_dfs = []
    def mock_to_csv_side_effect(self, *args, **kwargs):
        saved_dfs.append(self)

    mocker.patch('pandas.DataFrame.to_csv', new=mock_to_csv_side_effect)
    
    clean_duplicates("test_db.csv", max_sep_arcsec=1.0)
    
    assert len(saved_dfs) > 0, "to_csv was not called"
    saved_df = saved_dfs[-1]
    
    assert len(saved_df) == 2