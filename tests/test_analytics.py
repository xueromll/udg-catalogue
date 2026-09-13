import numpy as np
import pandas as pd

from udg_catalogue.analytics import (
    REPORT_FIGURES,
    effective_radius_histogram,
    generate_analytics_report,
    mass_radius_scatter,
    stellar_mass_histogram,
)


def sample_catalogue():
    return pd.DataFrame(
        {
            "stellar_mass_solar": [1e8, 3e8, np.nan, 0.0],
            "effective_radius_kpc": [1.5, 2.5, 3.0, -1.0],
            "completeness_pct": [100.0, 50.0, 33.3, 16.7],
        }
    )


def test_figures_are_built_from_positive_measurements():
    assert stellar_mass_histogram(sample_catalogue()) is not None
    assert effective_radius_histogram(sample_catalogue()) is not None
    scatter = mass_radius_scatter(sample_catalogue())
    assert scatter.axes[0].get_xscale() == "log"
    assert scatter.axes[0].get_yscale() == "log"


def test_figures_are_skipped_without_usable_data():
    unusable = pd.DataFrame(
        {"stellar_mass_solar": [np.nan], "effective_radius_kpc": [0.0], "completeness_pct": [0.0]}
    )

    assert stellar_mass_histogram(unusable) is None
    assert effective_radius_histogram(unusable) is None
    assert mass_radius_scatter(unusable) is None
    assert stellar_mass_histogram(pd.DataFrame()) is None
    assert mass_radius_scatter(pd.DataFrame({"stellar_mass_solar": [1.0]})) is None


def test_generate_analytics_report_writes_the_available_figures(tmp_path):
    messages = []

    complete = generate_analytics_report(sample_catalogue(), tmp_path / "complete", messages.append)
    partial = generate_analytics_report(
        pd.DataFrame({"effective_radius_kpc": [1.0, 2.0]}), tmp_path / "partial", messages.append
    )

    assert [path.name for path in complete] == list(REPORT_FIGURES)
    assert all(path.stat().st_size > 0 for path in complete)
    assert [path.name for path in partial] == ["radius_dist.png"]
    assert messages[-1] == f"Analytics report written to {tmp_path / 'partial'}"
