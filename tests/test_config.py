import os
import importlib
import pytest
import config

def test_config_loading_and_fallbacks(mocker):
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test_mock_key"})
    
    mock_yaml_data = {
        "model": "deepseek-custom-mock",
        "max_papers": 42,
        "timeout": 999
    }
    mocker.patch('yaml.safe_load', return_value=mock_yaml_data)
    mocker.patch('builtins.open', mocker.mock_open())
    
    importlib.reload(config)
    
    assert config.API_KEY == "test_mock_key"
    assert config.MODEL == "deepseek-custom-mock"
    assert config.MAX_PAPERS == 42
    assert config.TIMEOUT == 999
    
    assert config.SLEEP_BETWEEN == 5
    assert config.MAX_DIST_MPC == 5.0
    assert "sim" in config.FORBIDDEN_KEYWORDS