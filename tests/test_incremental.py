import pytest
import json
from incremental import load_pipeline_metadata, save_pipeline_metadata

def test_load_pipeline_metadata_exists(mocker):
    mocker.patch("os.path.exists", return_value=True)
    mock_data = '{"last_run_date": "2023-01-01T12:00:00", "last_start_index": 150}'
    mocker.patch("builtins.open", mocker.mock_open(read_data=mock_data))
    
    result = load_pipeline_metadata()
    
    assert result["last_start_index"] == 150
    assert result["last_run_date"] == "2023-01-01T12:00:00"

def test_load_pipeline_metadata_not_exists(mocker):
    mocker.patch("os.path.exists", return_value=False)
    
    result = load_pipeline_metadata()
    
    assert result["last_start_index"] == 0
    assert result["last_run_date"] is None

def test_load_pipeline_metadata_corrupted(mocker):
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("builtins.open", mocker.mock_open(read_data="{invalid_json}"))
    
    result = load_pipeline_metadata()
    
    assert result["last_start_index"] == 0
    assert result["last_run_date"] is None

def test_save_pipeline_metadata(mocker):
    mock_file = mocker.mock_open()
    mocker.patch("builtins.open", mock_file)
    mock_datetime = mocker.patch("incremental.datetime")
    mock_datetime.now.return_value.isoformat.return_value = "2023-10-10T10:10:10"
    
    save_pipeline_metadata(500)
    
    mock_file.assert_called_once_with("pipeline_meta.json", "w", encoding="utf-8")
    
    written_content = "".join(call.args[0] for call in mock_file().write.call_args_list)
    saved_data = json.loads(written_content)
    
    assert saved_data["last_start_index"] == 500
    assert saved_data["last_run_date"] == "2023-10-10T10:10:10"