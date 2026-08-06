import pytest
import json
import io
import requests
from bs4 import BeautifulSoup

from arxiv_client import (
    search_arxiv, parse_arxiv_xml, extract_tables_from_pdf,
    trim_references, fetch_paper_text, is_paper_relevant, extract_udg_data, session
)

def test_search_arxiv_success(mocker):
    mock_get = mocker.patch.object(session, 'get')
    mock_get.return_value.status_code = 200
    mock_get.return_value.content = b"<xml></xml>"
    mocker.patch('arxiv_client.time.sleep')
    
    assert search_arxiv("test") == b"<xml></xml>"

def test_search_arxiv_429_retry(mocker):
    mock_get = mocker.patch.object(session, 'get')
    response_429 = mocker.MagicMock()
    response_429.status_code = 429
    response_200 = mocker.MagicMock()
    response_200.status_code = 200
    response_200.content = b"success"
    
    mock_get.side_effect = [response_429, response_200]
    mocker.patch('arxiv_client.time.sleep')
    
    assert search_arxiv("test") == b"success"
    assert mock_get.call_count == 2

def test_search_arxiv_request_exception(mocker):
    mock_get = mocker.patch('arxiv_client.session.get', side_effect=requests.exceptions.RequestException("Error"))
    mocker.patch('arxiv_client.time.sleep')
    mocker.patch('arxiv_client.MAX_RETRIES', 2)
    
    assert search_arxiv("test") is None
    assert mock_get.call_count == 2

def test_parse_arxiv_xml_empty():
    assert parse_arxiv_xml(b"", set()) == ([], 0)
    assert parse_arxiv_xml(b"<feed></feed>", set()) == ([], 0)

def test_parse_arxiv_xml_with_entries():
    xml_data = b"""
    <feed>
        <entry>
            <id>http://arxiv.org/abs/1234.5678</id>
            <title>Test Title</title>
            <summary>Test Summary</summary>
            <link href="http://arxiv.org/html/1234.5678" />
        </entry>
        <entry>
            <id>http://arxiv.org/abs/skipped.1234</id>
            <title>Skipped Title</title>
        </entry>
    </feed>
    """
    processed = {"skipped.1234"}
    entries, total = parse_arxiv_xml(xml_data, processed)
    
    assert total == 2
    assert len(entries) == 1
    assert entries[0]["arxiv_id"] == "1234.5678"
    assert entries[0]["title"] == "Test Title"
    assert entries[0]["abstract"] == "Test Summary"
    assert entries[0]["html_link"] == "http://arxiv.org/html/1234.5678"

def test_extract_tables_from_pdf_success(mocker):
    mock_pdf = mocker.patch('arxiv_client.pdfplumber.open')
    mock_page = mocker.MagicMock()
    mock_page.extract_tables.return_value = [[["Cell 1", "Cell 2"], [None, "Cell 4"]]]
    mock_pdf.return_value.__enter__.return_value.pages = [mock_page]
    
    result = extract_tables_from_pdf(b"fakebytes")
    assert "Cell 1 | Cell 2\n | Cell 4" in result

def test_extract_tables_from_pdf_exception(mocker):
    mocker.patch('arxiv_client.pdfplumber.open', side_effect=Exception("PDF Error"))
    assert extract_tables_from_pdf(b"fakebytes") == ""

@pytest.mark.parametrize("text, expected", [
    (None, None),
    ("", ""),
    ("Before \\begin{thebibliography} After", "Before"),
    ("Main text. \n references \n cited works.", "Main text."),
    ("Text \n bibliography \n list", "Text"),
    ("No references here", "No references here"),
])
def test_trim_references(text, expected):
    assert trim_references(text) == expected

def test_fetch_paper_text_no_id():
    assert fetch_paper_text({"abstract": "fallback"}) == "fallback"

def test_fetch_paper_text_tarball_success(mocker):
    mock_get = mocker.patch.object(session, 'get')
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mock_get.return_value.__enter__.return_value = mock_response
    
    mock_tar = mocker.patch('arxiv_client.tarfile.open')
    mock_member = mocker.MagicMock()
    mock_member.isfile.return_value = True
    mock_member.name = "paper.tex"
    
    mock_file = mocker.MagicMock()
    mock_file.read.return_value = b"Test Tex Content"
    
    mock_tar.return_value.__enter__.return_value.__iter__.return_value = [mock_member]
    mock_tar.return_value.__enter__.return_value.extractfile.return_value = mock_file
    
    result = fetch_paper_text({"arxiv_id": "1234"})
    assert result == "Test Tex Content"

def test_fetch_paper_text_pdf_fallback(mocker):
    mock_get = mocker.patch.object(session, 'get')
    
    tar_response = mocker.MagicMock()
    tar_response.status_code = 404
    tar_response.__enter__.return_value = tar_response
    
    pdf_response = mocker.MagicMock()
    pdf_response.status_code = 200
    pdf_response.content = b"pdfbytes"
    
    mock_get.side_effect = [tar_response, pdf_response]
    
    mock_pdf = mocker.patch('arxiv_client.pdfplumber.open')
    mock_page = mocker.MagicMock()
    mock_page.extract_text.return_value = "PDF Text"
    mock_page.extract_tables.return_value = []
    mock_pdf.return_value.__enter__.return_value.pages = [mock_page]
    
    result = fetch_paper_text({"arxiv_id": "1234"})
    assert "PDF Text" in result
    assert "EXTRACTED TABLES" in result

def test_fetch_paper_text_complete_failure(mocker):
    mocker.patch('arxiv_client.session.get', side_effect=Exception("Network Error"))
    assert fetch_paper_text({"arxiv_id": "1234", "abstract": "abstract text"}) == "abstract text"

def test_is_paper_relevant_empty_abstract():
    assert is_paper_relevant("Title", "") is True

def test_is_paper_relevant_true(mocker):
    mock_response = mocker.MagicMock()
    mock_response.choices[0].message.content = '{"relevant": true}'
    mocker.patch('arxiv_client.client.chat.completions.create', return_value=mock_response)
    
    assert is_paper_relevant("Title", "Abstract") is True

def test_is_paper_relevant_false(mocker):
    mock_response = mocker.MagicMock()
    mock_response.choices[0].message.content = '{"relevant": false}'
    mocker.patch('arxiv_client.client.chat.completions.create', return_value=mock_response)
    
    assert is_paper_relevant("Title", "Abstract") is False

def test_is_paper_relevant_exception(mocker):
    mocker.patch('arxiv_client.client.chat.completions.create', side_effect=Exception("API Error"))
    assert is_paper_relevant("Title", "Abstract") is True

def test_extract_udg_data_bytes_and_html(mocker):
    mock_response = mocker.MagicMock()
    mock_response.choices[0].message.content = '{"galaxies": [{"galaxy_name": "G1"}]}'
    mock_create = mocker.patch('arxiv_client.client.chat.completions.create', return_value=mock_response)
    
    result = extract_udg_data(b"<html><body>Test HTML</body></html>")
    assert result[0]["galaxy_name"] == "G1"
    assert "Test HTML" in mock_create.call_args[1]["messages"][1]["content"]

def test_extract_udg_data_long_text(mocker):
    mock_response = mocker.MagicMock()
    mock_response.choices[0].message.content = '{"galaxies": []}'
    mock_create = mocker.patch('arxiv_client.client.chat.completions.create', return_value=mock_response)
    
    long_text = "A" * 150000
    extract_udg_data(long_text)
    
    called_content = mock_create.call_args[1]["messages"][1]["content"]
    assert len(called_content) == 120000

def test_extract_udg_data_fallback_format(mocker):
    mock_response = mocker.MagicMock()
    mock_response.choices[0].message.content = '{"custom_key": [{"galaxy_name": "G2"}]}'
    mocker.patch('arxiv_client.client.chat.completions.create', return_value=mock_response)
    
    result = extract_udg_data("Test")
    assert result[0]["galaxy_name"] == "G2"

def test_extract_udg_data_exception(mocker):
    mocker.patch('arxiv_client.client.chat.completions.create', side_effect=Exception("Timeout"))
    assert extract_udg_data("Test") == []