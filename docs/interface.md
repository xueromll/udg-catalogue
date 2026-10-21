# The dashboard interface

The paper search page puts a query bar with chips, a result list, a graph
canvas and an inspector on one screen, with facets in the sidebar and a
persistent banner for anything the library could not do. This page says what
maps to what, what the Streamlit version does not do, and which tokens the
theme uses.

Run it with `streamlit run app.py`. The paper search page needs the paper
index (`python main.py --index-papers`); the table, map and analytics pages
work from the committed `data/udg_database_sorted.csv` alone.

## Board frame

Every page is laid out as an early-2000s bulletin board. A ruled site header
under a 4 px ink rule carries the title, the tagline
(`ui.forum.tagline_html`) and a nav strip (`ui.forum.nav_html`: a `?view=` link
per page, the current page in the accent, the time on the right); a
breadcrumb (`ui.forum.breadcrumb_html`) names the section and the page,
`UDG Catalogue › Galaxies › Data Table`. On the catalogue pages a board index
follows (`ui.forum.board_rows` and `board_html`): the eight largest
constellations and clusters of the selection as forum tables with a lamp
(■ the group has a confirmed galaxy, □ it has none), the galaxies, confirmed
and mapped counts, the nearest mapped galaxy, and a `... n more` row. Each
section is a board, a 1 px ink rule around a keyed `board-*` container whose
first row is an ink category bar; the sidebar's navigation, filters and
facets are `block-*` boards of the same kind. A statistics box
(`ui.forum.stats_lines`: catalogue and selection sizes, quality flags, the
mapped count and median distance, the largest and most massive galaxy, the
last build from the run manifest) with the lamp legend, and a footer with the
catalogue and sci-etl-core versions, close every page.

## Layout at 1440 px

One column = 12 px. The sidebar is Streamlit's (about 300 px); the main area
splits 3 / 5 / 3 between hits, canvas and inspector.

```
+-------------------------+--------------------------------------------------------------------------------------+
| Navigation              | Ultra-Diffuse Galaxies (UDG) Research Dashboard                                      |
| ( ) Data Table          | 1,927 galaxies in the catalogue                                                      |
| ( ) Analytics           +--------------------------------------------------------------------------------------+
| (o) Paper Search        | Search papers                              Match by      Papers mentioning a galaxy  |
|                         | [ "Malin 1" surface brightness -lensing ]  [Hybrid  v]   [                      v]  |
| Facets                  | ["Malin 1"] [surface] [brightness] [lensing]  [categories:astro-ph.GA]               |
| categories              | 2,118 matched · 20 shown · 61 ms                                                     |
|  astro-ph.GA · 8,412    +--------------------------------------------------------------------------------------+
|  astro-ph.CO · 1,207    | ! semantic leg failed: the embeddings could not be queried. Showing keyword results  |
|  astro-ph.IM · 311      | i communities in the graph are approximate: label propagation hit its pass limit.    |
|  ... 14 more            +--------------------------------------------------------------------------------------+
| year                    | [ ] Graph fullscreen                                                                 |
|  2023 · 1,922           +-----------------------+------------------------------------+-------------------------+
|  2022 · 1,870           | Hits  20 of 2,118     | Graph                              | Inspector               |
|  ...                    | +-------------------+ | [x] semantic  [x] metadata (...)   | 2301.04512              |
| [Clear filters]         | | 1. The giant low- | |                                    | The giant low-surface-  |
|                         | |  surface-brightne.| |        .  .   .  .        .        | brightness disc of      |
| Catalogue filters       | | 2301.04512 · 2023 | |     .    .  .      .   .     .     | Malin 1 revisited       |
| Constellation [All  v]  | |  · L1 S3 · 0.033  | |   .   . .  .  . .    .  .  . .     | Boissier S., Junais ... |
| Cluster ID    [All  v]  | | abstract: ...Malin| |  .  .   .   .   .  . .   . .  .    | year 2023 · astro-ph.GA |
| Completeness  [====  ]  | | 1 ... surface bri.| | .   .   ..  .  .  o---o   .   .    | [Open in graph]         |
| Quality Flag  [All  v]  | | [Select]          | |  .    .  .  . .  o--(@)--o  .  .   |-------------------------|
| 1,927 of 1,927 galaxies | +-------------------+ |   . .   .   . .  . o--o-o  .   .   | Galaxies from this paper|
| [Download filtered CSV] | +-------------------+ |  .   .  .  .   . .   o  .  . .  .  | galaxy_name  ra  dec ...|
|                         | | 2. HI kinematics  | |                                    | Malin 1   189.2  14.3   |
|                         | | 1910.02231 · 2019 | | 183 nodes · 412 edges · 97 dimmed  |-------------------------|
|                         | |  · L2 S1 · 0.031  | |  · seed 2301.04512                 | Rejected extractions    |
|                         | | [Select]          | | Select a node [               v]   | no review store in this |
|                         | +-------------------+ |                                    | workspace               |
|                         | 3. ...                |                                    |-------------------------|
|                         | ...                   |                                    | Extraction stamp        |
|                         | 20. ...               |                                    | model   deepseek-v4-fla |
|                         |                       |                                    | prompt  3f9a1c0e        |
|                         |                       |                                    | library sci-etl-core/0.7|
+-------------------------+-----------------------+------------------------------------+-------------------------+
```

`(@)` is the seed node in the accent colour with a halo; `o` nodes are hits at
full ink, filled by community; `.` nodes are everything else, dimmed to the
secondary colour at 40 %. `L1 S3` are `FusedHit.lexical_rank` and
`semantic_rank`, `-` when a leg did not return the hit; the last number is the
fused score, shown raw because it is comparable only within one result list.

## Regions

| Region | Here | Binds to |
|---|---|---|
| Query bar, mono, mode selector | `st.text_input` (`query-bar`, mono via CSS) and a `Match by` selectbox | `PaperLibrary.search(query, mode=...)`; a `SearchQueryError` shows its column |
| Chip bar | `ui.chips.query_chips`, rendered as inline spans; negated chips struck through in the secondary colour, group depth as a thicker left rule, the operator in the tooltip | `DiscoveryResult.chips` |
| Filter chips, dashed | `ui.chips.filter_chips` from the facet selection | `paper_filters(categories, years)` |
| Status line | `ui.chips.status_line`: `total_matched · shown · elapsed_ms` in mono | `DiscoveryResult.total_matched`, `elapsed_ms` |
| Banner, persistent, never a toast | `ui.chips.banner_lines` and `banner_html`: one line per condition, `!` for a failed leg, `i` for a skipped one or approximate communities; it is drawn on every run while the condition holds on the current result | `DiscoveryResult.degraded`, `skipped`, `DiscoveryGraph.communities_converged` |
| Facets sidebar, key → value (count), selecting re-queries | `ui.facets.facet_groups`: eight rows per key plus every selected row, a `... n more` line, one tertiary button per row, the selected row with a 2 px accent bar; clicking toggles the value and the search re-runs with the new filters | `DiscoveryResult.facets`; before a search, the index's category counts from `LibraryOverview` |
| Hit list | `ui.hits.hit_html` in a striped topic row per hit (a `topic-*` container), snippets with the matched words in bold, a `Select` button | `DiscoveryResult.hits`, `FusedHit.snippets` |
| Graph canvas | `ui.graph.build_canvas`: Plotly scatter, community ramp, degree-scaled radii, seed in the accent with a halo, hits at full ink, the rest dimmed, edges in the separator colour, one checkbox per edge kind present, click to select through `st.plotly_chart(on_select="rerun")`, a `Select a node` selectbox as the fallback, a `Graph fullscreen` toggle | `DiscoveryGraph` from `PaperLibrary.related_papers`, pruned by the active filters with `filter_graph` |
| Inspector | `ui.inspector`: id linked in mono, title in sans, authors and `year · categories` in the secondary colour; the catalogue rows whose `source_papers` (or raw `record_id`) name the paper, with the measured columns; the paper's rows of `data/rejected_galaxies.db`; the run manifest's model, prompt hashes, library version and build date as the extraction stamp; `Open in graph` recenters the graph on the inspected paper | `SearchDocument`, the catalogue CSV, the rejection store's `rejections` table, `data/run_manifest.json` |
| Empty states | One sentence in the secondary colour per region: no catalogue, no index, no search yet, no graph yet, no selection, no galaxies, no review store, no manifest | — |

Selection and the seed are two session keys. Selecting a hit sets both;
clicking a node or picking it in the selectbox sets the selection only, and
`Open in graph` copies the selection into the seed. A click on the canvas is
applied once per distinct point, so a stale Plotly selection cannot undo a
later hit selection.

## Deep links

`?view=papers` opens the paper search page, `&q=...` fills the query bar and
`&paper=<arXiv id>` selects that paper and centres the graph on it.
`?view=analytics` and `?view=table` open the other pages.

## What the Streamlit version does not do

- **Keyboard.** `/`, `j`/`k`, `Enter`, `Esc` and `g` have no counterpart.
  Streamlit widgets take focus through the browser only, and a page has no
  key handler without custom JavaScript, which the app does not ship.
  Streamlit 1.63's `st.button(shortcut=...)` is not used because it binds
  one key per button, not a cursor over a list.
- **Lasso and multi-select.** `st.plotly_chart` returns box and lasso
  selections, but the inspector binds to one record and comparing
  claims across papers needs a claim store this repository does not have. The canvas therefore takes `selection_mode="points"` only.
- **Shift-click to pin.** Plotly click events carry no modifier keys.
- **Large graphs.** The canvas draws the library's discovery graph, at most
  `search.graph.max_nodes` (80 in `config.yaml`) nodes, laid out with the
  O(n²) NumPy spring layout of `paper_views.spring_layout`. It does not draw
  every indexed paper at once.
- **Claims with evidence spans.** The pipeline writes galaxies and
  rejections, not `Claim` records, so the inspector shows the catalogue rows
  and the rejected extractions instead of claims and evidence.
- **Edge kinds.** sci-etl-core 0.7.0's `MetadataEdgeSource` emits one kind,
  `metadata`, for authors and categories together, so there is one toggle
  for both rather than `metadata:authors` and `metadata:categories`.
- **Motion and dark mode.** Hover transitions follow the 120 ms rule where
  CSS reaches; Streamlit's theme is fixed to the light slate palette.
- **Fonts.** Verdana is a system font; JetBrains Mono loads from Google
  Fonts when the browser is online, with the system mono as fallback; the
  application itself makes no network call.

## Theme tokens

`.streamlit/config.toml` sets what Streamlit's theme can express;
`udg_catalogue/ui/tokens.py` holds the same values for the charts and
`udg_catalogue/ui/theme.py` builds the one CSS block from them.

| Token | Value | Where |
|---|---|---|
| canvas | `#F4F5F7` | page, sidebar, panels, chart ground |
| ink | `#334155` | type, 1 px borders, node strokes, histogram bars, links |
| accent | `#6366F1` | the selection class only: seed node, selected facet bar, selected hit rule, the primary `Open in graph` button, the median rule of a histogram |
| separator | `#E2E5EA` | panel rules, hover, banner ground, graph edges, chart grid |
| muted | `#94A3B8` | secondary text, empty states, dimmed nodes at 40 %, the unclustered series of the map |
| halo | `#C7D2FE` | the ring of the seed and of the selected node |
| community ramp | `#263140 #334155 #43566F #566E90 #7088A9 #90A2BC` | node fill by community size rank, the sixth step gathers the tail; reversed, the continuous scale of the map and the scatter |
| mono | JetBrains Mono, IBM Plex Mono, SFMono-Regular, Menlo, Consolas | ids, numbers, chips, status lines, the query bar, facet rows, stamp |
| sans | Verdana, Tahoma, DejaVu Sans, Segoe UI | titles, body, headings, category bars |
| type scale | 12 / 14 / 16 px | secondary / body / inspector title |
| grid, border, radius | 8 px, 1 px, 0 px | spacing, every border, every corner |
| node radius | `clip(3 + 1.5 * sqrt(degree), 3, 14)` px | canvas marker size |
| shadows, gradients, colour bars on the canvas | none | — |

The charts of the other pages follow the same rules: the 3D map keeps the
layout of `maps.build_3d_figure` and is restyled by `ui.charts.restyle_map`
(ink scale for a measure, ramp steps per cluster, grey for the unclustered);
the analytics histograms and the mass against radius scatter are drawn by
`ui.charts` in Plotly, ink bars with the median as the one accent rule, and a
completeness colour on the ink scale.

## Tests

`udg_catalogue/ui` holds no Streamlit call, and `tests/test_ui_*.py` cover
every function in it without Streamlit's runtime; the repository's coverage
gate includes the package. `tests/test_app.py` drives `app.py` with
Streamlit's `AppTest` against the committed catalogue and a three-paper index
written for the test: search, chips, status line, hit selection, graph
controls, node selection, `Open in graph`, facets, the banner, the inspector
with and without a review store and a manifest, deep links, and the empty
states.
