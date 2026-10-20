# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The version is `udg_catalogue.__version__`, and the run manifest records it next to the sci-etl-core version. Catalogue runs published before 1.0.0 predate versioning, so their manifests carry no catalogue version.

## [Unreleased]

## [1.0.0] - 2026-10-20

First versioned release, on the released sci-etl-core 0.7.0.

### Added

<!-- dashboard: see interface changelog -->
- **`python main.py --reprocess ARXIV_ID ...`** forgets the given papers on the run's state manager (`forget`, new in sci-etl-core 0.7) and pages the listing from its first entry, so a corrected prompt or validator re-extracts chosen papers. The log names the ids forgotten and the ids that were never processed. With `--index-papers` the ids are forgotten in the indexing state instead. The CSV exporter and the paper memory replace a paper's earlier rows and passages, and cached LLM answers are reused when the prompt and model are unchanged.
- **Embedding prescreen** (`prescreen.enabled`, off by default): an `AsyncEmbeddingRelevanceFilter` over the configured embeddings provider runs before the DeepSeek relevance check through `AsyncCascadingRelevanceFilter`, and rejects a paper whose title and abstract score below `prescreen.threshold` against every `prescreen.concepts` entry without an LLM call. An active prescreen is logged as a warning because it changes what the run screens and costs. It requires `embeddings.enabled`.
- **Text index tuning** (`search_index.cache_size_mb`, default 64, and `search_index.mmap_size_mb`, default none) passed to the FTS5 store as `SqliteTuning`.
- **Contract suites** under `tests/contract/`: sci-etl-core's `ExtractorContract` runs against `LoggingExtractor` over the arXiv extractor, and `ExporterContract` against the raw-catalogue CSV exporter. `requirements/dev.txt` installs the `testing` extra.
- **Package version** `udg_catalogue.__version__`, recorded in the run manifest as `software.udg-catalogue`, where earlier manifests recorded `null`.

### Changed

- **sci-etl-core 0.7** is required: `sci-etl-core[...]>=0.7.0,<0.8` in `requirements.txt`, `requirements/dev.txt` and `requirements/local.txt`, and the suite runs with `-W error::DeprecationWarning`.
- **Paper search's "papers contain every keyword" figure** comes from `count_matches`, which counts in the index, instead of loading every matching id.
- **Hybrid search draws 500 candidates per leg** instead of 100, following the sci-etl-core 0.7 default; set `search.hybrid.candidate_pool: 100` in `config.yaml` to keep the old pool.
- **Continuous integration** installs sci-etl-core from PyPI instead of its `master` branch and fails on any `DeprecationWarning`.

[Unreleased]: https://github.com/xueromll/udg-catalogue/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/xueromll/udg-catalogue/releases/tag/v1.0.0
