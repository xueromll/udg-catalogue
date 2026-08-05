from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from config import MAX_PAPERS, SEARCH_QUERY, SORTED_CSV_FILE, HTML_MAP_FILE, SLEEP_BETWEEN
from logger import logger
from arxiv_client import search_arxiv, parse_arxiv_xml, is_paper_relevant, fetch_paper_text, extract_udg_data
from data_processor import load_processed_ids, save_processed_id, upsert_to_csv, clean_duplicates, process_database
from visualization import visualize_udg_3d
from incremental import load_pipeline_metadata, save_pipeline_metadata
from analytics import generate_analytics_report


def process_single_paper_task(paper: dict, processed_ids: set[str]) -> bool:
    title = paper.get("title", "")
    abstract = paper.get("abstract", "")
    arxiv_id = paper.get("arxiv_id", "")

    logger.info(f"Processing: {title[:80]}...")

    if not is_paper_relevant(title, abstract):
        logger.info(f"Skipped by abstract filter: {arxiv_id}")
        if arxiv_id:
            save_processed_id(arxiv_id)
            processed_ids.add(arxiv_id)
        return False

    text = fetch_paper_text(paper)
    if text == "SKIPPED_NO_KEYWORDS":
        if arxiv_id:
            save_processed_id(arxiv_id)
            processed_ids.add(arxiv_id)
        return False

    galaxies = extract_udg_data(text)
    if galaxies:
        upsert_to_csv(galaxies)

    if arxiv_id:
        save_processed_id(arxiv_id)
        processed_ids.add(arxiv_id)
        
    return True

if __name__ == "__main__":
    logger.info("Starting pipeline")
    
    processed_ids = load_processed_ids()
    meta = load_pipeline_metadata()
    start_index = meta.get("last_start_index", 0)
    papers_processed = 0
    max_workers = 6
    
    while papers_processed < MAX_PAPERS:
        logger.info(f"--- arXiv page: start_index = {start_index} ---")
        xml_data = search_arxiv(SEARCH_QUERY, max_results=MAX_PAPERS, start_index=start_index)
        
        if not xml_data: 
            break
        papers, total_in_xml = parse_arxiv_xml(xml_data, processed_ids)
        
        if total_in_xml == 0 or not papers:
            break
            
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_single_paper_task, paper, processed_ids): paper for paper in papers}
            
            for future in as_completed(futures):
                try:
                    success = future.result()
                    if success:
                        papers_processed += 1
                    if papers_processed >= MAX_PAPERS:
                        break
                except Exception as exc:
                    logger.error(f"Paper processing generated an exception: {exc}")
                
        start_index += MAX_PAPERS
        save_pipeline_metadata(start_index)
        time.sleep(SLEEP_BETWEEN)

    logger.info(f"[SUMMARY] Total successfully processed papers: {papers_processed}")
    
    logger.info("Starting automatic duplicate cleanup...")
    clean_duplicates()
    
    logger.info("Starting calculation...")
    process_database()
    
    logger.info("Starting analytics report generation...")
    generate_analytics_report(SORTED_CSV_FILE)

    logger.info("Starting 3D map generation...")
    visualize_udg_3d(csv_file=SORTED_CSV_FILE, html_output_file=HTML_MAP_FILE)
    
    logger.info("Pipeline completed successfully!")