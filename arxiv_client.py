import io
import json
import tarfile
import time
import re
import pypdf
import pdfplumber
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

from config import API_KEY, MODEL, USER_AGENT, MAX_RETRIES
from prompts import FILTER_PROMPT, EXTRACTION_PROMPT, STRICT_SIMULATION_PROMPT
from logger import logger

session = requests.Session()
retries = Retry(
    total=5,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504]
)
session.mount("https://", HTTPAdapter(max_retries=retries))

client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")

def search_arxiv(query: str, max_results: int = 5, start_index: int = 0) -> bytes | None:
    base_url = "https://export.arxiv.org/api/query"
    params = {"search_query": query, "start": start_index, "max_results": max_results, "sortBy": "submittedDate", "sortOrder": "descending"}
    time.sleep(3)
    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(base_url, params=params, headers={"User-Agent": USER_AGENT}, timeout=(10, 60))
            if response.status_code == 429:
                time.sleep(20)
                continue
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1: 
                time.sleep(5 * (attempt + 1))
            else:
                logger.error(f"arXiv search failed after {MAX_RETRIES} attempts: {e}")
    return None

def parse_arxiv_xml(xml_text: bytes, processed_ids: set[str]) -> tuple[list[dict], int]:
    soup = BeautifulSoup(xml_text, "xml")
    entries = []
    xml_entries = soup.find_all("entry")
    total_found_in_xml = len(xml_entries)
    if total_found_in_xml == 0: 
        return [], 0

    skipped = 0
    for entry in xml_entries:
        raw_id = entry.id.get_text(strip=True) if entry.id else ""
        arxiv_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id
        if arxiv_id in processed_ids:
            skipped += 1
            continue
        entries.append({
            "arxiv_id": arxiv_id,
            "title": entry.title.get_text(strip=True) if entry.title else "",
            "abstract": entry.summary.get_text(strip=True) if entry.summary else "",
            "html_link": next((link.get("href") for link in entry.find_all("link") if "html" in link.get("href", "")), None)
        })
    logger.info(f"Skipped previously processed: {skipped} | New: {len(entries)}")
    return entries, total_found_in_xml

def extract_tables_from_pdf(pdf_bytes: bytes) -> str:
    table_texts = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if table:
                        row_strings = [" | ".join([str(cell) if cell else "" for cell in row]) for row in table]
                        table_texts.append("\n".join(row_strings))
    except Exception as e:
        logger.error(f"pdfplumber table extraction error: {e}")
    return "\n".join(table_texts)


def trim_references(text: str) -> str:
    if not text:
        return text

    patterns = [
        r'\\begin\{thebibliography\}',
        r'\\bibliography\{',
        r'\\printbibliography',
        r'\n\s*references\s*\n',
        r'\n\s*bibliography\s*\n',
        r'\n\s*acknowledgments?\s*\n',
        r'\n\s*literature cited\s*\n',
    ]

    min_index = len(text)
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match and match.start() < min_index:
            min_index = match.start()


    if min_index < len(text):
        trimmed = text[:min_index]
        return trimmed.rstrip()
    
    return text

def fetch_paper_text(entry: dict) -> str:
    arxiv_id: str = entry.get("arxiv_id", "")
    if not arxiv_id: 
        return entry.get("abstract", "")

        
    source_url = f"https://arxiv.org/e-print/{arxiv_id}"
    try:
        with session.get(source_url, headers={"User-Agent": USER_AGENT}, timeout=25, verify=False, stream=True) as r:
            if r.status_code == 200:
                tex_files_content = []
                try:
                    with tarfile.open(mode="r|gz", fileobj=r.raw) as tar:
                        for member in tar:
                            if member.isfile() and member.name.endswith(".tex"):
                                f = tar.extractfile(member)
                                if f: 
                                    tex_files_content.append(f.read().decode("utf-8", errors="ignore"))
                except Exception: 
                    pass

                if tex_files_content:
                    byte_elements = [item.encode('utf-8', errors='ignore') if isinstance(item, str) else item for item in tex_files_content]
                    clean_tex = re.sub(rb'(?<!\\)%.*', b'', b"\n".join(byte_elements)).decode("utf-8", errors="ignore")
                    return trim_references(clean_tex)
    except Exception as e:
        logger.warning(f"LaTeX fetch failed for {arxiv_id}: {e}")

    try:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        r = session.get(pdf_url, headers={"User-Agent": USER_AGENT}, timeout=30)
        if r.status_code == 200:
            pdf_bytes = r.content
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as reader:
                full_text = "\n".join([p.extract_text() for p in reader.pages if p and p.extract_text()])
            
            tables_text = extract_tables_from_pdf(pdf_bytes)
            combined_text = f"{full_text}\n\n--- EXTRACTED TABLES ---\n{tables_text}"
            
            if combined_text.strip(): 
                return trim_references(combined_text)
    except Exception as e:
        logger.error(f"pdfplumber processing error for {arxiv_id}: {e}")

    return entry.get("abstract", "")

def is_paper_relevant(title: str, abstract: str) -> bool:
    if not abstract: 
        return True 
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": STRICT_SIMULATION_PROMPT},
                {"role": "user", "content": f"Title: {title}\nAbstract: {abstract}"}
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            timeout=20
        )
        data = json.loads(response.choices[0].message.content.strip())
        is_rel: bool = bool(data.get("relevant", False))
        logger.info(f"Abstract filter: relevant = {is_rel}")
        return is_rel
    except Exception as e:
        logger.warning(f"Filter error: {e}. Proceeding to download.")
        return True

def extract_udg_data(text: str | bytes) -> list[dict]:
    cleaned = text.decode('utf-8', errors='ignore') if isinstance(text, bytes) else text
    if "<" in cleaned[:200]: 
        cleaned = BeautifulSoup(cleaned, "html.parser").get_text(separator=" ", strip=True)
    if len(cleaned) > 120000: 
        cleaned = cleaned[:120000]

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": EXTRACTION_PROMPT}, {"role": "user", "content": cleaned}],
            temperature=0.0, response_format={"type": "json_object"}, timeout=120
        )
        data = json.loads(response.choices[0].message.content.strip())
        return data.get("galaxies", []) if "galaxies" in data else (list(data.values())[0] if len(data) == 1 else [])
    except Exception as e:
        logger.error(f"DeepSeek error: {e}")
        return []