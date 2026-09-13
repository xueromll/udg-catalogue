# UDG Catalogue — Automated ETL Pipeline for Ultra-Diffuse Galaxies

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg?style=flat-square)](https://www.python.org/)
[![sci-etl-core](https://img.shields.io/badge/built_on-sci--etl--core_0.1-0b7285.svg?style=flat-square)](https://github.com/xueromll/sci-etl-core)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.63-red.svg?style=flat-square)](https://streamlit.io/)
[![DeepSeek](https://img.shields.io/badge/DeepSeek-V4_Flash-purple.svg?style=flat-square)](https://deepseek.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

</div>

> **A fully automated ETL pipeline that scrapes 540+ astrophysics papers from arXiv, extracts structured data about Ultra-Diffuse Galaxies (UDGs) using DeepSeek V4-Flash, and visualizes 1,285 galaxies in an interactive dashboard.**
>
> The ETL machinery (arXiv access, LLM steps, CSV upserts, resumable state, dataframe processors) comes from [sci-etl-core](https://github.com/xueromll/sci-etl-core). This repository holds the astronomy: prompts, galaxy naming and validation rules, sky-position matching, clustering features, and the dashboard.

---

## Quickstart

```bash
git clone https://github.com/xueromll/udg-catalogue.git && cd udg-catalogue
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## Key Features

- **Multi-format extraction** — LaTeX sources (tarballs or single gzipped files, assembled in document order), PDFs with their tables, and the abstract as a last resort
- **AI-powered structured extraction** — DeepSeek V4-Flash in JSON mode; every extracted galaxy is checked against the catalogue rules before it is stored
- **Interactive 3D visualization** — Plotly map with color-coded parameters and rich hover tooltips
- **Streamlit dashboard** — real-time filtering, analytics, and CSV export
- **Scientific processing** — sky-position deduplication, DBSCAN clustering (56 groups), constellation mapping (43 constellations), quality flags
- **Bounded async ingestion** — up to six papers in flight at once
- **Fault-tolerant** — retries with backoff, crash-safe CSV and state writes, and papers that fail are retried on the next run instead of being marked done
- **Container-ready** — Dockerfile and Compose file included

---

## Results at a Glance

| Metric | Value |
|--------|-------|
| **Papers processed** | 540+ |
| **Unique galaxies catalogued** | 1,285 |
| **100% completeness objects** | 66 |
| **3D spatial clusters (DBSCAN)** | 56 |
| **Constellations mapped** | 43 |
| **Pipeline runs (for testing)** | 4 full ETL runs |
| **Total API cost (all runs)** | **$2.61** |
| **Development time** | 72 hours |
| **ETL framework** | sci-etl-core 0.1.0 |

---

## Engineering Approach

- **Iterative testing** — the pipeline was executed 4 times from scratch with cleared state, simulating first‑run conditions. Each run verified:
  - Robustness against missing or malformed PDFs
  - Correctness of the extraction schema (JSON parsing, percentage conversion)
  - Performance of the deduplication and clustering steps (successfully dropping 484 duplicates automatically)
- **Fault‑tolerance by design** — retries with exponential backoff, fallback strategies (LaTeX → PDF → abstract), and persistent state (`processed_arxiv_ids.txt`, `pipeline_meta.json`). An arXiv outage stops the run with an explicit error instead of looking like the end of the data, and a failed LLM extraction leaves the paper to be retried.
- **Verified migration** — moving onto sci-etl-core was checked by replaying the catalogue through the old and new code: the CSV upserts matched exactly, and the sorted catalogue matched cell for cell apart from three rows with an invalid right ascension. The walkthrough is the case study in sci-etl-core's [MIGRATION.md](https://github.com/xueromll/sci-etl-core/blob/master/MIGRATION.md).
- **Cost‑conscious** — every API call was logged and counted. The total spend stayed under $3 even with multiple full runs, proving the system can be maintained on a minimal budget.

---

## Tech Stack

| Domain | Technologies |
|--------|-------------|
| **Language** | Python 3.11 |
| **ETL framework** | sci-etl-core (arXiv extraction, LLM steps, CSV upsert, state, processors) |
| **AI / LLM** | DeepSeek V4-Flash through sci-etl-core's OpenAI-compatible client |
| **Data Processing** | pandas, numpy, scikit-learn (DBSCAN) |
| **Astronomy** | astropy (coordinates, cross-matching, constellations) |
| **Visualization** | plotly, matplotlib, seaborn |
| **Dashboard** | Streamlit |
| **Configuration** | YAML + `.env`, validated by Pydantic |
| **Containerization** | Docker Compose |

---

## Project Structure

```text
udg-catalogue/
├── main.py                  # Command-line entrypoint: ingest, post-process, report
├── app.py                   # Streamlit dashboard
├── config.yaml              # Pipeline, paths, clustering and deduplication settings
├── udg_catalogue/
│   ├── config.py            # CatalogueConfig, built on sci-etl-core's BaseAppConfig
│   ├── pipeline.py          # Assembles the sci-etl-core ingestion pipeline
│   ├── prompts.py           # LLM system prompts
│   ├── naming.py            # Galaxy name normalizer used as the catalogue key
│   ├── validation.py        # Rules every extracted galaxy must pass
│   ├── astrometry.py        # Sky matching, 3D features, constellations, cross-matching
│   ├── postprocess.py       # Processor chain that builds the sorted catalogue
│   ├── maps.py              # Plotly 3D map shared by main.py and the dashboard
│   └── analytics.py         # Statistical figures shared by main.py and the dashboard
├── vendor/                  # Pinned sci-etl-core wheel used by Docker and CI
├── requirements.txt         # Runtime install with the vendored sci-etl-core
├── requirements-local.txt   # Runtime install against a local sci-etl-core checkout
├── requirements-app.txt     # Pinned third-party dependencies
├── requirements-dev.txt     # Test dependencies
├── tests/                   # Offline test suite
├── Dockerfile               # Container setup
├── docker.yaml              # Docker Compose file used by this repo
├── LICENSE                  # MIT License
└── README.md                # This file
```

---

## Quick Start

### Local Installation

```bash
git clone https://github.com/xueromll/udg-catalogue.git
cd udg-catalogue

python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env       # then set DEEPSEEK_API_KEY

python main.py

streamlit run app.py
```

Run `pip install` from the project root: pip resolves the vendored wheel's path from the current directory.

### Running the Pipeline

| Command | What it does |
|---------|--------------|
| `python main.py` | Rescans arXiv from the newest submission, skipping papers already processed, then rebuilds the sorted catalogue, analytics figures and 3D map |
| `python main.py --resume` | Continues from the listing offset saved in `pipeline_meta.json` instead of rescanning |
| `python main.py --skip-ingestion` | Rebuilds the outputs from the existing `udg_database.csv` without calling arXiv or DeepSeek |
| `python main.py --config other.yaml` | Uses another configuration file; its paths are resolved relative to that file |

The exit code is `0` on success, `1` when ingestion was aborted (the outputs are still rebuilt from the data already collected), and `2` when `DEEPSEEK_API_KEY` is missing.

### Developing Against a Local sci-etl-core

To change the library and this project together, install sci-etl-core in editable mode instead of from the vendored wheel. `requirements-local.txt` expects the checkout at `../../sci-etl-core`; adjust the path if yours lives elsewhere.

```bash
pip install -r requirements-local.txt
python -c "import sci_etl_core; print(sci_etl_core.__file__)"
```

The second command should print a path inside your sci-etl-core checkout. If you move that checkout, reinstall: an editable install records its absolute path.

To upgrade the vendored library, build a wheel from the release tag and update the file name in `requirements.txt`:

```bash
pip wheel --no-deps -w vendor path/to/sci-etl-core
```

### Rebuilding the Catalogue From Scratch

The committed catalogue was extracted before the migration, when name matching could merge distinct galaxies that shared a catalogue number (for example `KDG 44` and `DF 44`, or `NGC 1052-DF2` and `NGC 1052-DF4`). The current code keeps such galaxies apart, but it cannot split rows that were merged earlier. To rebuild the catalogue with the current rules, archive the raw data and state, then run the pipeline:

```bash
mkdir -p archive
mv udg_database.csv processed_arxiv_ids.txt pipeline_meta.json archive/
python main.py
```

A rebuild reprocesses every matching paper, so expect roughly the API cost of one full run.

### Docker (Recommended)

This repository includes a Docker Compose file named `docker.yaml`. If you prefer the conventional `docker-compose.yml` name you may rename it locally or adapt the command below.

Build and run the container using Docker Compose (this repo uses `docker.yaml` by default):

```bash
docker compose -f docker.yaml up --build
```

The Streamlit dashboard will be available at `http://localhost:8501`. The Compose file passes `DEEPSEEK_API_KEY` from your environment and mounts the project directory, so the container reads and writes the same catalogue files as a local run.

---

## Dashboard Features

* **3D Interactive Map** — explore 1,285 galaxies with color-coding by:
  * Dark Matter Fraction
  * Completeness (%)
  * Distance (Mpc)
  * Cluster ID

* **Real-time Filtering** — filter by constellation, cluster, completeness, and quality flag
* **Analytics View** — distribution plots (mass, radius) and mass–radius scatter with completeness coloring
* **Data Export** — download filtered data as CSV

---

## Gallery

### Galaxy Map

![3D Map](assets/demo.png)

*Interactive 3D map showing UDG distribution across constellations. Hover over any point to see detailed galaxy parameters.*

### Analytics Dashboard

![Analytics](assets/analytics.png)

*Statistical plots: stellar mass distribution, effective radius distribution, and mass–radius correlation.*

---

## Testing

The test suite runs offline. arXiv is replaced by an in-memory Atom feed and e-print, DeepSeek by a scripted client, and the dashboard is exercised with Streamlit's `AppTest`.

```bash
pip install -r requirements-dev.txt
pytest --cov
```

Coverage of `udg_catalogue` and `main.py` is required to stay at 100%.

---

## Future Work

* [x] Integrate **sci-etl-core** as a reusable library
* [ ] Add support for other astronomical catalogues (e.g., dSph, LSB galaxies)
* [ ] Deploy Streamlit dashboard to Streamlit Cloud
* [ ] Add automated weekly updates via GitHub Actions

---

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Citation

If you use this project in your research, please cite it as:

```bibtex
@misc{udg-catalogue-2026,
  author = {Lan},
  title = {UDG Catalogue: Automated ETL Pipeline for Ultra-Diffuse Galaxies},
  year = {2026},
  publisher = {GitHub},
  howpublished = {\url{https://github.com/xueromll/udg-catalogue}}
}
```

---

## License

MIT License — feel free to use, modify, and build upon this work. See the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

* **arXiv** for providing open access to astrophysics papers
* **DeepSeek** for their affordable and powerful LLM API
* All the astrophysicists whose papers made this catalogue possible

---

## Contact

Maintained by **Lan**

GitHub: [xueromll](https://github.com/xueromll)

Email: [lanhua1122333@gmail.com](mailto:lanhua1122333@gmail.com)

---

**Made with ❤️ and curiosity.**
