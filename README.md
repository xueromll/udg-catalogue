
# UDG Catalogue — Automated ETL Pipeline for Ultra-Diffuse Galaxies

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.20+-red.svg)](https://streamlit.io/)
[![DeepSeek](https://img.shields.io/badge/DeepSeek-V4_Flash-purple.svg)](https://deepseek.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **A fully automated ETL pipeline that scrapes 540+ astrophysics papers from arXiv, extracts structured data about Ultra-Diffuse Galaxies (UDGs) using DeepSeek V4-Flash, and visualizes 1,768 galaxies in an interactive 3D map — all built in 72 hours at a cost of $2.61.**

---

## Key Features

- **Multi-format extraction** — retrieves text from LaTeX sources, PDFs, and HTML abstracts
- **AI-powered structured extraction** — uses DeepSeek V4-Flash with strict JSON schema enforcement
- **Interactive 3D visualization** — Plotly map with color-coded parameters and rich hover tooltips
- **Streamlit dashboard** — real-time filtering, analytics, and CSV export
- **Scientific processing** — DBSCAN clustering (71 groups), constellation mapping (45 constellations), quality flags
- **Parallel ingestion** — ThreadPoolExecutor with 6 workers for high throughput
- **Fault-tolerant** — exponential backoff, retries, state management, and graceful shutdown
- **Container-ready** — Dockerfile included for reproducible deployment

---

## Results at a Glance

| Metric | Value |
|--------|-------|
| **Papers processed** | 540+ |
| **Unique galaxies catalogued** | 1,769 |
| **100% completeness objects** | 85 |
| **3D spatial clusters (DBSCAN)** | 71 |
| **Constellations mapped** | 45 |
| **Total API cost** | **$2.61** |
| **Development time** | 72 hours |
| **Codebase** | ~800 lines (modular) |

---

## Tech Stack

| Domain | Technologies |
|--------|-------------|
| **Language** | Python 3.11.9 |
| **AI / LLM** | DeepSeek V4-Flash via OpenAI SDK |
| **Data Extraction** | arXiv API, BeautifulSoup, pypdf, pdfplumber, tarfile |
| **Data Processing** | pandas, numpy, scikit-learn (DBSCAN) |
| **Astronomy** | astropy, skyfield (coordinates, constellations) |
| **Visualization** | plotly, matplotlib, seaborn |
| **Dashboard** | Streamlit |
| **Configuration** | YAML, python-dotenv, Pydantic |
| **Logging** | structlog-style with file + console |
| **Containerization** | Docker |

---

## Project Structure

```
udg-catalogue/
├── main.py                 # Pipeline orchestration
├── app.py                  # Streamlit dashboard
├── config.py & config.yaml # Settings (Pydantic + YAML)
├── arxiv_client.py         # arXiv API & PDF/LaTeX parsing
├── data_processor.py       # DBSCAN clustering & data cleaning
├── visualization.py        # Plotly 3D engine
├── analytics.py            # Statistical reports
├── cross_match.py          # Reference catalog comparison
├── incremental.py          # Pipeline state (metadata)
├── prompts.py              # LLM system prompts
├── logger.py               # Logging setup
├── requirements.txt        # Dependencies
├── Dockerfile              # Container setup
├── LICENSE                 # MIT License
└── README.md               # This file
```

---

## Quick Start

### Local Installation

```bash
git clone https://github.com/your-username/udg-catalogue.git
cd udg-catalogue

python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env

python main.py

streamlit run app.py
```

### Docker

```bash
docker build -t udg-catalogue .

docker run -p 8501:8501 --env-file .env udg-catalogue
```

---

## Dashboard Features

- **3D Interactive Map** — explore 1,768 galaxies with color-coding by:
  - Dark Matter Fraction
  - Completeness (%)
  - Distance (Mpc)
  - Cluster ID
- **Real-time Filtering** — filter by constellation, cluster, completeness, and quality flag
- **Analytics View** — distribution plots (mass, radius) and mass-radius scatter with completeness coloring
- **Data Export** — download filtered data as CSV

---

## Gallery

###  Galaxy Map

![3D Map](assets/demo.png)

*Interactive 3D map showing UDG distribution across 45 constellations. Hover over any point to see detailed galaxy parameters.*

### Analytics Dashboard

![Analytics](assets/analytics.png)

*Statistical plots: stellar mass distribution, effective radius distribution, and mass–radius correlation.*

---

## License

MIT License — feel free to use, modify, and build upon this work. See the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- **arXiv** for providing open access to astrophysics papers
- **DeepSeek** for their affordable and powerful LLM API
- All the astrophysicists whose papers made this catalogue possible

---

## Contact

Maintained by **Lan**  
GitHub: [xueromll](https://github.com/xueromll)  
Email: [lanhua1122333@gmail.com](mailto:lanhua1122333@gmail.com)

---

**Made with ❤️ and curiosity.**