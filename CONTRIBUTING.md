# Contributing to UDG Catalogue

Contributions of two kinds are welcome: **corrections to the catalogue** and **improvements to the software**. By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Contents

1. [Reporting Catalogue Errors](#1-reporting-catalogue-errors)
2. [Reporting Software Defects](#2-reporting-software-defects)
3. [Proposing Features](#3-proposing-features)
4. [Code Organisation](#4-code-organisation)
5. [Development Environment](#5-development-environment)
6. [Changes That Affect the Catalogue](#6-changes-that-affect-the-catalogue)
7. [Testing Requirements](#7-testing-requirements)
8. [Style and Documentation](#8-style-and-documentation)
9. [Submitting a Pull Request](#9-submitting-a-pull-request)

---

## 1. Reporting Catalogue Errors

Catalogue values are extracted automatically and may contain errors (see [Known Limitations](README.md#known-limitations) in the README). If you find an incorrect, duplicated or misattributed entry, please open an issue with:

| Field | Example |
|---|---|
| Object designation, as listed in the catalogue | `DF44` |
| Affected column(s) | `stellar_mass_solar` |
| Catalogue value | `3.0e9` |
| Correct value, with units | `3.0e8 M☉` |
| Reference | arXiv identifier or DOI, plus the table, figure or page |
| Nature of the problem | wrong value, unit error, duplicate entry, not a UDG, simulated object |

A reference to the original publication is required. Corrections that cite no source cannot be verified.

## 2. Reporting Software Defects

Open an issue using the bug report template and include:

- a concise, descriptive title;
- the steps needed to reproduce the problem;
- the expected and the observed behaviour;
- relevant log excerpts from `pipeline.log` or tracebacks, in code blocks;
- your operating system, Python version and commit hash.

Remove API keys from anything you paste.

## 3. Proposing Features

Open an issue describing the problem the feature addresses, the proposed behaviour and any alternatives you considered. For changes that alter the scientific content of the catalogue, please discuss them in an issue before starting the implementation.

## 4. Code Organisation

The generic ETL machinery lives in [sci-etl-core](https://github.com/xueromll/sci-etl-core). This repository contains only what is specific to ultra-diffuse galaxies, implemented as plug-ins to the library's interfaces:

| Module | Responsibility |
|---|---|
| `udg_catalogue/prompts.py` | Relevance and extraction prompts |
| `udg_catalogue/naming.py` | `KeyNormalizer` deciding when two designations refer to the same object |
| `udg_catalogue/validation.py` | `RecordValidator` rules applied to every extracted galaxy |
| `udg_catalogue/astrometry.py` | `NeighborMatcher`, `FeatureExtractor` and `Processor` implementations built on astropy |
| `udg_catalogue/postprocess.py` | `ProcessorChain` producing the sorted catalogue |
| `udg_catalogue/pipeline.py` | Assembly of the sci-etl-core ingestion pipeline |
| `udg_catalogue/maps.py`, `udg_catalogue/analytics.py` | Figures shared by `main.py` and the dashboard |

Changes that would benefit any scientific corpus, not just this catalogue, belong in sci-etl-core. Examples include new extractors, parsers, exporters and generic processors.

## 5. Development Environment

```bash
git clone https://github.com/<your-username>/udg-catalogue.git
cd udg-catalogue
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest --cov
```

On Windows, activate the environment with `.venv\Scripts\activate`.

The raw ingestion output `udg_database.csv` is not version-controlled. On a fresh clone, `python main.py --skip-ingestion` therefore has no input to rebuild from. The dashboard (`streamlit run app.py`) does work on a fresh clone, because it reads the released `udg_database_sorted.csv`.

To develop sci-etl-core alongside this project, install `requirements-local.txt` instead of `requirements.txt`. It installs a sibling checkout of the library in editable mode.

## 6. Changes That Affect the Catalogue

Some changes alter which objects are catalogued or what values they carry: prompts, validation rules, name normalisation, cross-match radius, clustering parameters and quality-flag thresholds. For these changes, the pull request should state:

- **Motivation**, with references to the literature where a threshold or definition is involved;
- **Effect on the released catalogue**, measured by rebuilding the sorted catalogue before and after the change and reporting the differences in row count, quality-flag distribution, number of spatial groups and any objects merged or split;
- **Tests** that pin the new behaviour, such as designations that must or must not resolve to the same key.

## 7. Testing Requirements

- Tests use `pytest` and `pytest-cov`.
- **All tests must run offline.** Replace arXiv with `httpx.MockTransport` and DeepSeek with a scripted `AsyncLLMClient`, as in `tests/test_pipeline.py`.
- Line coverage of `udg_catalogue` and `main.py` must remain at 100%. The threshold is enforced by `pyproject.toml` and by continuous integration.

```bash
pytest --cov
```

## 8. Style and Documentation

- Follow [PEP 8](https://peps.python.org/pep-0008/) and annotate functions with type hints.
- Keep functions small and focused. Express intent through clear names and structure rather than explanatory comments.
- Update the README when behaviour, parameters, outputs or catalogue statistics change, and keep the methodology section consistent with the code.

## 9. Submitting a Pull Request

1. Fork the repository and create a branch from `main`:

   ```bash
   git checkout -b feat/short-description
   ```

2. Make your changes, then run the test suite locally.
3. Commit using [Conventional Commits](https://www.conventionalcommits.org/):

   ```bash
   git commit -m "feat(validation): reject galaxies without a catalogue designation"
   ```

4. Push the branch and open a pull request against `main`. Complete the pull request template, and link the related issue.

## Questions

Please open an issue, or contact the maintainer at [lanhua1122333@gmail.com](mailto:lanhua1122333@gmail.com).
