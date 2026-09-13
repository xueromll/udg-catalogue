# Contributing to UDG Catalogue

First off, thank you for considering contributing to this project!

This project is open-source and welcomes contributions of all kinds — from bug reports and feature requests to code improvements and documentation updates.

---

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please be respectful and constructive in all interactions.

---

## How to Report a Bug

If you find a bug, please open an issue with:

- A clear and descriptive title
- Steps to reproduce the behavior
- Expected vs. actual behavior
- Relevant logs, screenshots, or code snippets
- Environment (Python version, OS, etc.)

---

## How to Propose a Feature

We welcome feature suggestions! Open an issue with:

- A clear description of the feature
- Why it would be useful
- Any possible implementation ideas (optional)

---

## How the Code Is Organized

The generic ETL machinery lives in [sci-etl-core](https://github.com/xueromll/sci-etl-core). This repository contains only what is specific to ultra-diffuse galaxies, as plug-ins to the library's interfaces:

- `udg_catalogue/naming.py` — `KeyNormalizer` that decides when two galaxy names are the same object
- `udg_catalogue/validation.py` — `RecordValidator` rules applied to every extracted galaxy
- `udg_catalogue/astrometry.py` — `NeighborMatcher`, `FeatureExtractor` and `Processor` implementations built on astropy
- `udg_catalogue/postprocess.py` — the `ProcessorChain` that builds the sorted catalogue
- `udg_catalogue/pipeline.py` — wiring of the sci-etl-core ingestion pipeline

If a change would help any scientific corpus rather than just this catalogue (a new extractor, parser, exporter or processor), propose it to sci-etl-core instead.

---

## How to Contribute Code

1. **Fork the repository**
   Click the "Fork" button on the top right of the GitHub page.

2. **Clone your fork**
   ```bash
   git clone https://github.com/YOUR_USERNAME/udg-catalogue.git
   cd udg-catalogue
   ```

3. **Create a new branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

4. **Make your changes**
   - Follow the existing code style (PEP 8).
   - Add or update tests; coverage must stay at 100%.
   - Ensure all tests pass: `pytest --cov`
   - Update documentation if needed.

5. **Commit and push** using [Conventional Commits](https://www.conventionalcommits.org/)
   ```bash
   git add .
   git commit -m "feat(validation): reject galaxies without a catalogue designation"
   git push origin feature/your-feature-name
   ```

6. **Open a Pull Request**
   Go to the original repository and click "New Pull Request". Provide a clear description of your changes and reference any related issues.

---

## Testing Guidelines

- We use `pytest` with `pytest-cov`.
- **All tests must be offline** — replace arXiv with `httpx.MockTransport` and DeepSeek with a scripted `AsyncLLMClient`, as `tests/test_pipeline.py` does.
- Run tests locally before submitting:
  ```bash
  pip install -r requirements-dev.txt
  pytest --cov
  ```

---

## Documentation

If you add or change functionality, please update the relevant documentation:
- `README.md` — for high‑level overview and usage
- Docstrings in code — for API‑level explanations
- Clear names and small functions rather than explanatory comments

---

## Development Setup

```bash
git clone https://github.com/xueromll/udg-catalogue.git
cd udg-catalogue

python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate

pip install -r requirements.txt -r requirements-dev.txt

pytest --cov
python main.py --skip-ingestion
```

To work on sci-etl-core at the same time, install `requirements-local.txt` instead of `requirements.txt`; it links a sibling checkout of the library in editable mode.

---

## Style Guide

- Follow [PEP 8](https://peps.python.org/pep-0008/) for Python code.
- Use **type hints** wherever possible.
- Write **clear, concise commit messages** in the Conventional Commits format.
- Keep functions **small** and **focused**.

---

## Questions?

Feel free to open a Discussion or reach out via email: [lanhua1122333@gmail.com](mailto:lanhua1122333@gmail.com)

---

**Thank you for making this project better! ❤️**
