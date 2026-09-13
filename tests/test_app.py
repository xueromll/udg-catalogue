from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"
COLOR_SELECTOR = "Select color mapping parameter:"


def color_selector(app):
    return next(selectbox for selectbox in app.selectbox if selectbox.label == COLOR_SELECTOR)


def test_dashboard_renders_every_view_of_the_committed_catalogue():
    app = AppTest.from_file(str(APP_PATH), default_timeout=120).run()

    assert not app.exception
    assert app.title[0].value == "Ultra-Diffuse Galaxies (UDG) Research Dashboard"
    assert len(app.dataframe) == 1

    for option in ("Cluster ID", "Distance (Mpc)", "Completeness (%)"):
        color_selector(app).set_value(option).run()
        assert not app.exception

    app.sidebar.radio[0].set_value("Analytics").run()
    assert not app.exception
    assert app.subheader[-1].value == "Statistical Analytics"
