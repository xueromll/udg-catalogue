"""The dashboard's presentation layer: pure functions that turn library results into things Streamlit draws.

Nothing in this package imports Streamlit, so every function is testable
without its runtime. ``app.py`` is the only place that calls ``st.*``.
"""
