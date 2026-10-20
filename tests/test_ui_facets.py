from sci_etl_core.discovery import Facet

from udg_catalogue.ui.facets import (
    FacetGroup,
    FacetRow,
    facet_groups,
    overview_facets,
    selection_filters,
    toggled,
)

CATEGORIES = Facet("categories", (("astro-ph.GA", 8412), ("astro-ph.CO", 1207), ("astro-ph.IM", 311)))
YEARS = Facet("year", (("2023", 1922), ("2022", 1870)))


def test_facet_groups_cut_each_facet_to_the_limit_but_keep_selected_rows():
    assert facet_groups([CATEGORIES, YEARS], {}, limit=2) == [
        FacetGroup(
            "categories",
            (FacetRow("categories", "astro-ph.GA", 8412), FacetRow("categories", "astro-ph.CO", 1207)),
            hidden=1,
        ),
        FacetGroup("year", (FacetRow("year", "2023", 1922), FacetRow("year", "2022", 1870))),
    ]
    assert facet_groups([CATEGORIES], {"categories": ("astro-ph.IM",)}, limit=1) == [
        FacetGroup(
            "categories",
            (FacetRow("categories", "astro-ph.GA", 8412), FacetRow("categories", "astro-ph.IM", 311, selected=True)),
            hidden=1,
        )
    ]


def test_facet_row_label_and_widget_key():
    row = FacetRow("constellation", "Coma Berenices", 1234)

    assert row.label == "Coma Berenices  1,234"
    assert row.widget_key == "facet-constellation-Coma_Berenices"
    assert FacetRow("categories", "astro-ph.GA", 1, selected=True).widget_key == "facet-on-categories-astro-ph.GA"


def test_toggled_adds_removes_and_drops_empty_keys():
    assert toggled({}, "year", "2019") == {"year": ("2019",)}
    assert toggled({"year": ("2019",)}, "year", "2019") == {}
    assert toggled({"categories": ("b",), "year": ()}, "categories", "a") == {"categories": ("a", "b")}
    assert toggled({"categories": ("a",)}, "year", "2020") == {"categories": ("a",), "year": ("2020",)}


def test_selection_filters_sort_categories_and_span_the_chosen_years():
    assert selection_filters({}) == ((), None)
    assert selection_filters({"categories": ("b", "a"), "year": ("2021", "2019", "n.d.")}) == (
        ("a", "b"),
        (2019, 2021),
    )
    assert selection_filters({"year": ("n.d.",)}) == ((), None)


def test_overview_facets_offer_the_index_categories_before_a_search():
    assert overview_facets([("astro-ph.GA", 3)]) == [Facet("categories", (("astro-ph.GA", 3),))]
