from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

from sci_etl_core import (
    EmbeddingError,
    PipelineAborted,
    PipelineInterrupted,
    SearchStoreError,
    ShutdownSignal,
)

from udg_catalogue.analytics import generate_analytics_report
from udg_catalogue.config import (
    API_KEY_ENV_VAR,
    DEFAULT_CONFIG_PATH,
    EMBEDDING_API_KEY_ENV_VAR,
    CatalogueConfig,
    embedding_key_missing,
    load_catalogue_config,
)
from udg_catalogue.logs import configure_run_logging
from udg_catalogue.manifest import write_manifest
from udg_catalogue.maps import write_3d_map
from udg_catalogue.pipeline import forget_papers, run_ingestion, run_paper_indexing
from udg_catalogue.postprocess import build_sorted_catalogue

EXIT_OK = 0
EXIT_INGESTION_ABORTED = 1
EXIT_MISSING_API_KEY = 2
EXIT_INTERRUPTED = 130

Stage = Callable[[CatalogueConfig, logging.Logger, int | None, ShutdownSignal], Awaitable[int]]


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the ultra-diffuse galaxy catalogue from arXiv papers.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to the YAML configuration file.",
    )
    parser.add_argument(
        "--rescan",
        action="store_true",
        help="Page the whole arXiv listing from the newest submission instead of resuming where the last run stopped.",
    )
    parser.add_argument(
        "--replace-catalogue",
        action="store_true",
        help=(
            "Write the sorted catalogue even when the raw catalogue has fewer rows than the published one, "
            "as after a rebuild from scratch."
        ),
    )
    parser.add_argument(
        "--reprocess",
        nargs="+",
        metavar="ARXIV_ID",
        default=(),
        help=(
            "Forget these arXiv ids so the run extracts them again, after a prompt or validation change, "
            "and page the whole listing from the newest submission as --rescan does. "
            "With --index-papers, the ids are forgotten in the indexing state instead."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--skip-ingestion",
        action="store_true",
        help="Only rebuild the sorted catalogue, analytics report and 3D map from existing data.",
    )
    mode.add_argument(
        "--index-papers",
        action="store_true",
        help="Index relevant papers missing from the paper search index, without extracting galaxies.",
    )
    arguments = parser.parse_args(argv)
    if arguments.reprocess and arguments.skip_ingestion:
        parser.error("--reprocess needs an ingestion run; drop --skip-ingestion")
    return arguments


def run_stage(stage: Stage, config: CatalogueConfig, log: logging.Logger, start_index: int | None) -> int:
    try:
        processed = asyncio.run(stage(config, log, start_index, ShutdownSignal()))
    except PipelineInterrupted as interrupted:
        log.warning(
            f"Stopped on request after {interrupted.partial_count} relevant papers; run again to continue"
        )
        return EXIT_INTERRUPTED
    except PipelineAborted as aborted:
        log.error(
            f"Ingestion aborted after {aborted.partial_count} relevant papers: "
            f"{aborted} (cause: {aborted.__cause__!r})"
        )
        return EXIT_INGESTION_ABORTED
    except (EmbeddingError, SearchStoreError) as error:
        log.error(f"Paper memory could not be opened: {error}")
        return EXIT_INGESTION_ABORTED
    log.info(f"Relevant papers processed: {processed}")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    config = load_catalogue_config(arguments.config)
    log = configure_run_logging(config.paths.log_file)
    exit_code = EXIT_OK

    if not arguments.skip_ingestion:
        if not config.llm.api_key.get_secret_value():
            log.error(f"{API_KEY_ENV_VAR} is not set; add it to .env or the environment")
            return EXIT_MISSING_API_KEY
        if embedding_key_missing(config):
            log.error(
                f"{EMBEDDING_API_KEY_ENV_VAR} is not set but embeddings.provider is openai; "
                "set the key or use the local provider"
            )
            return EXIT_MISSING_API_KEY
        if arguments.reprocess:
            asyncio.run(forget_papers(config, log, arguments.reprocess, indexing=arguments.index_papers))
        stage = run_paper_indexing if arguments.index_papers else run_ingestion
        start_index = 0 if arguments.rescan or arguments.reprocess else None
        exit_code = run_stage(stage, config, log, start_index)
        if arguments.index_papers or exit_code == EXIT_INTERRUPTED:
            return exit_code

    catalogue = build_sorted_catalogue(config, log.info, replace=arguments.replace_catalogue)
    if catalogue is not None:
        generate_analytics_report(catalogue, config.paths.analytics_dir, log.info)
        write_3d_map(catalogue, config.paths.html_map, log.info)
        write_manifest(config, log.info)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
