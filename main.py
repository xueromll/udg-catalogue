from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from sci_etl_core import PipelineAborted, configure_logging

from udg_catalogue.analytics import generate_analytics_report
from udg_catalogue.config import API_KEY_ENV_VAR, DEFAULT_CONFIG_PATH, load_catalogue_config
from udg_catalogue.maps import write_3d_map
from udg_catalogue.pipeline import run_ingestion
from udg_catalogue.postprocess import build_sorted_catalogue

EXIT_OK = 0
EXIT_INGESTION_ABORTED = 1
EXIT_MISSING_API_KEY = 2
LOGGER_NAME = "UDGPipeline"


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the ultra-diffuse galaxy catalogue from arXiv papers.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to the YAML configuration file.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue from the saved listing offset instead of rescanning from the newest submissions.",
    )
    parser.add_argument(
        "--skip-ingestion",
        action="store_true",
        help="Only rebuild the sorted catalogue, analytics report and 3D map from existing data.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    config = load_catalogue_config(arguments.config)
    log = configure_logging(LOGGER_NAME, config.paths.log_file)
    exit_code = EXIT_OK

    if not arguments.skip_ingestion:
        if not config.llm.api_key.get_secret_value():
            log.error(f"{API_KEY_ENV_VAR} is not set; add it to .env or the environment")
            return EXIT_MISSING_API_KEY
        start_index = None if arguments.resume else 0
        try:
            processed = asyncio.run(run_ingestion(config, log, start_index))
            log.info(f"Relevant papers processed: {processed}")
        except PipelineAborted as aborted:
            log.error(
                f"Ingestion aborted after {aborted.partial_count} relevant papers: "
                f"{aborted} (cause: {aborted.__cause__!r})"
            )
            exit_code = EXIT_INGESTION_ABORTED

    catalogue = build_sorted_catalogue(config, log.info)
    if catalogue is not None:
        generate_analytics_report(catalogue, config.paths.analytics_dir, log.info)
        write_3d_map(catalogue, config.paths.html_map, log.info)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
