import pytest
from main import process_single_paper_task

@pytest.fixture
def mock_dependencies(mocker):
    return {
        "is_relevant": mocker.patch("main.is_paper_relevant"),
        "fetch_text": mocker.patch("main.fetch_paper_text"),
        "extract_data": mocker.patch("main.extract_udg_data"),
        "upsert": mocker.patch("main.upsert_to_csv"),
        "save_id": mocker.patch("main.save_processed_id"),
    }

def test_process_single_paper_task_irrelevant(mock_dependencies):
    mock_dependencies["is_relevant"].return_value = False
    processed_ids = set()
    paper = {"title": "Test", "abstract": "Test", "arxiv_id": "1111.2222"}
    
    result = process_single_paper_task(paper, processed_ids)
    
    assert result is False
    assert "1111.2222" in processed_ids
    mock_dependencies["save_id"].assert_called_once_with("1111.2222")
    mock_dependencies["fetch_text"].assert_not_called()

def test_process_single_paper_task_skipped_no_keywords(mock_dependencies):
    mock_dependencies["is_relevant"].return_value = True
    mock_dependencies["fetch_text"].return_value = "SKIPPED_NO_KEYWORDS"
    processed_ids = set()
    paper = {"arxiv_id": "3333.4444"}
    
    result = process_single_paper_task(paper, processed_ids)
    
    assert result is False
    assert "3333.4444" in processed_ids
    mock_dependencies["save_id"].assert_called_once_with("3333.4444")
    mock_dependencies["extract_data"].assert_not_called()

def test_process_single_paper_task_success_with_galaxies(mock_dependencies):
    mock_dependencies["is_relevant"].return_value = True
    mock_dependencies["fetch_text"].return_value = "Valid paper text"
    mock_dependencies["extract_data"].return_value = [{"galaxy_name": "DF 44"}]
    processed_ids = {"existing_id"}
    paper = {"arxiv_id": "5555.6666"}
    
    result = process_single_paper_task(paper, processed_ids)
    
    assert result is True
    assert "5555.6666" in processed_ids
    mock_dependencies["upsert"].assert_called_once_with([{"galaxy_name": "DF 44"}])
    mock_dependencies["save_id"].assert_called_once_with("5555.6666")

def test_process_single_paper_task_success_no_galaxies(mock_dependencies):
    mock_dependencies["is_relevant"].return_value = True
    mock_dependencies["fetch_text"].return_value = "Valid paper text"
    mock_dependencies["extract_data"].return_value = []
    processed_ids = set()
    paper = {"arxiv_id": "7777.8888"}
    
    result = process_single_paper_task(paper, processed_ids)
    
    assert result is True
    mock_dependencies["upsert"].assert_not_called()
    mock_dependencies["save_id"].assert_called_once_with("7777.8888")