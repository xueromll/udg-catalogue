import matplotlib
matplotlib.use('Agg')

import pytest
import runpy
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
    
    assert process_single_paper_task({"title": "T", "abstract": "A", "arxiv_id": "1"}, processed_ids) is False
    assert "1" in processed_ids
    mock_dependencies["save_id"].assert_called_once_with("1")
    mock_dependencies["fetch_text"].assert_not_called()

def test_process_single_paper_task_skipped_no_keywords(mock_dependencies):
    mock_dependencies["is_relevant"].return_value = True
    mock_dependencies["fetch_text"].return_value = "SKIPPED_NO_KEYWORDS"
    processed_ids = set()
    
    assert process_single_paper_task({"arxiv_id": "2"}, processed_ids) is False
    assert "2" in processed_ids
    mock_dependencies["save_id"].assert_called_once_with("2")
    mock_dependencies["extract_data"].assert_not_called()

def test_process_single_paper_task_success_with_galaxies(mock_dependencies):
    mock_dependencies["is_relevant"].return_value = True
    mock_dependencies["fetch_text"].return_value = "Valid paper text"
    mock_dependencies["extract_data"].return_value = [{"galaxy_name": "DF 44"}]
    processed_ids = {"0"}
    
    assert process_single_paper_task({"arxiv_id": "3"}, processed_ids) is True
    assert "3" in processed_ids
    mock_dependencies["upsert"].assert_called_once_with([{"galaxy_name": "DF 44"}])
    mock_dependencies["save_id"].assert_called_once_with("3")

def test_process_single_paper_task_success_no_galaxies(mock_dependencies):
    mock_dependencies["is_relevant"].return_value = True
    mock_dependencies["fetch_text"].return_value = "Valid paper text"
    mock_dependencies["extract_data"].return_value = []
    processed_ids = set()
    
    assert process_single_paper_task({"arxiv_id": "4"}, processed_ids) is True
    mock_dependencies["upsert"].assert_not_called()
    mock_dependencies["save_id"].assert_called_once_with("4")

@pytest.fixture
def mock_orchestrator_deps(mocker):
    return {
        "load_processed": mocker.patch("data_processor.load_processed_ids", return_value=set()),
        "load_meta": mocker.patch("incremental.load_pipeline_metadata", return_value={"last_start_index": 0}),
        "save_meta": mocker.patch("incremental.save_pipeline_metadata"),
        "search": mocker.patch("arxiv_client.search_arxiv"),
        "parse": mocker.patch("arxiv_client.parse_arxiv_xml"),
        "sleep": mocker.patch("time.sleep"),
        "clean_dups": mocker.patch("data_processor.clean_duplicates"),
        "process_db": mocker.patch("data_processor.process_database"),
        "analytics": mocker.patch("analytics.generate_analytics_report"),
        "visualize": mocker.patch("visualization.visualize_udg_3d"),
    }

@pytest.fixture
def mock_executor(mocker):
    mock_thread_pool = mocker.patch("concurrent.futures.ThreadPoolExecutor")
    mock_as_completed = mocker.patch("concurrent.futures.as_completed")
    
    mock_instance = mocker.MagicMock()
    mock_thread_pool.return_value.__enter__.return_value = mock_instance
    
    return mock_instance, mock_as_completed

def execute_main_block(mocker):
    mocker.patch("sys.argv", ["main.py"])
    runpy.run_module('main', run_name='__main__')

def test_main_empty_page(mocker, mock_orchestrator_deps):
    mock_orchestrator_deps["search"].return_value = None
    
    execute_main_block(mocker)
    
    mock_orchestrator_deps["search"].assert_called_once()
    mock_orchestrator_deps["parse"].assert_not_called()
    mock_orchestrator_deps["clean_dups"].assert_called_once()
    mock_orchestrator_deps["visualize"].assert_called_once()

def test_main_no_more_papers(mocker, mock_orchestrator_deps):
    mock_orchestrator_deps["search"].return_value = b"<xml>data</xml>"
    mock_orchestrator_deps["parse"].return_value = ([], 0)
    
    execute_main_block(mocker)
    
    mock_orchestrator_deps["search"].assert_called_once()
    mock_orchestrator_deps["parse"].assert_called_once()
    mock_orchestrator_deps["clean_dups"].assert_called_once()
    mock_orchestrator_deps["process_db"].assert_called_once()

def test_main_exit_on_max_papers(mocker, mock_orchestrator_deps, mock_executor):
    mocker.patch("config.MAX_PAPERS", 2)
    
    mock_orchestrator_deps["search"].return_value = b"<xml>data</xml>"
    mock_orchestrator_deps["parse"].return_value = ([{"id": "1"}, {"id": "2"}, {"id": "3"}], 3)
    
    mock_instance, mock_as_completed = mock_executor
    
    f1, f2, f3 = mocker.MagicMock(), mocker.MagicMock(), mocker.MagicMock()
    f1.result.return_value = True
    f2.result.return_value = True
    f3.result.return_value = True
    mock_as_completed.return_value = [f1, f2, f3]
    
    execute_main_block(mocker)
    
    assert mock_instance.submit.call_count == 3
    mock_orchestrator_deps["save_meta"].assert_called_once()
    mock_orchestrator_deps["analytics"].assert_called_once()

def test_main_future_exception(mocker, mock_orchestrator_deps, mock_executor):
    mocker.patch("config.MAX_PAPERS", 2)
    
    mock_orchestrator_deps["search"].return_value = b"<xml>data</xml>"
    mock_orchestrator_deps["parse"].return_value = ([{"id": "1"}, {"id": "2"}], 2)
    
    mock_instance, mock_as_completed = mock_executor
    
    f1, f2 = mocker.MagicMock(), mocker.MagicMock()
    f1.result.side_effect = Exception("Worker Thread Crashed")
    f2.result.return_value = True
    mock_as_completed.return_value = [f1, f2]
    
    execute_main_block(mocker)
    
    mock_orchestrator_deps["clean_dups"].assert_called_once()
    mock_orchestrator_deps["process_db"].assert_called_once()