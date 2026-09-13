import asyncio
import gzip
import json
import logging

import httpx
import pandas as pd
from sci_etl_core import AsyncLLMClient

from udg_catalogue import pipeline as pipeline_module
from udg_catalogue.pipeline import EXTRACTION_RESULT_KEY, run_ingestion
from udg_catalogue.prompts import EXTRACTION_PROMPT, RELEVANCE_PROMPT

LISTING = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2601.00001v1</id>
    <title>Dragonfly 44 revisited</title>
    <summary>Deep imaging of an ultra-diffuse galaxy.</summary>
    <link href="http://arxiv.org/abs/2601.00001v1" rel="alternate" type="text/html"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2601.00002v1</id>
    <title>Ultra-diffuse galaxies in TNG50</title>
    <summary>Purely simulated galaxies.</summary>
  </entry>
</feed>"""
EMPTY_LISTING = b'<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
LATEX_SOURCE = rb"\documentclass{article}\begin{document}Dragonfly 44 has an effective radius of 4.6 kpc.\end{document}"
EXTRACTED_GALAXIES = [
    {
        "galaxy_name": "Dragonfly 44",
        "ra": 195.24,
        "dec": 26.98,
        "distance_mpc": 100.0,
        "effective_radius_kpc": 4.6,
        "stellar_mass_solar": 3e8,
        "dark_matter_fraction": 99.0,
    },
    {"galaxy_name": "mock_udg_1", "ra": 10.0, "dec": 10.0},
]


class ScriptedLLMClient(AsyncLLMClient):
    def __init__(self):
        self.calls = []
        self.closed = False

    async def complete_json(self, system_prompt, user_content, timeout=None):
        self.calls.append((system_prompt, user_content))
        if system_prompt == RELEVANCE_PROMPT:
            return {"relevant": "TNG50" not in user_content}
        return {EXTRACTION_RESULT_KEY: EXTRACTED_GALAXIES}

    async def aclose(self):
        self.closed = True


class FakeArxiv:
    def __init__(self):
        self.listing_requests = []

    def handle(self, request):
        if request.url.path == "/api/query":
            self.listing_requests.append(dict(request.url.params))
            start = int(request.url.params["start"])
            return httpx.Response(200, content=LISTING if start == 0 else EMPTY_LISTING)
        if request.url.path.startswith("/e-print/"):
            return httpx.Response(200, content=gzip.compress(LATEX_SOURCE))
        return httpx.Response(404)


def install_fake_clients(monkeypatch, arxiv, llm):
    created = {}

    def build_http_client(**kwargs):
        created["http_options"] = kwargs
        created["http_client"] = httpx.AsyncClient(transport=httpx.MockTransport(arxiv.handle))
        return created["http_client"]

    def build_llm_client(**kwargs):
        created["llm_options"] = kwargs
        return llm

    monkeypatch.setattr(pipeline_module, "build_async_client", build_http_client)
    monkeypatch.setattr(pipeline_module, "AsyncOpenAICompatibleClient", build_llm_client)
    return created


def test_ingestion_runs_arxiv_papers_through_the_assembled_pipeline(ingestion_config, monkeypatch):
    arxiv = FakeArxiv()
    llm = ScriptedLLMClient()
    created = install_fake_clients(monkeypatch, arxiv, llm)

    processed = asyncio.run(run_ingestion(ingestion_config, logging.getLogger("udg-test"), start_index=0))

    assert processed == 1
    assert pd.read_csv(ingestion_config.paths.raw_catalogue).to_dict("records") == [
        {
            "galaxy_name": "Dragonfly 44",
            "ra": 195.24,
            "dec": 26.98,
            "distance_mpc": 100.0,
            "effective_radius_kpc": 4.6,
            "stellar_mass_solar": 3e8,
            "dark_matter_fraction": 1.0,
        }
    ]
    assert set(ingestion_config.paths.processed_ids.read_text(encoding="utf-8").split()) == {
        "2601.00001v1",
        "2601.00002v1",
    }
    metadata = json.loads(ingestion_config.paths.pipeline_metadata.read_text(encoding="utf-8"))
    assert metadata["last_start_index"] == 2
    assert [request["start"] for request in arxiv.listing_requests] == ["0", "2"]
    assert arxiv.listing_requests[0]["search_query"] == ingestion_config.pipeline.search_query
    assert arxiv.listing_requests[0]["max_results"] == "2"
    assert [content for prompt, content in llm.calls if prompt == EXTRACTION_PROMPT] == [LATEX_SOURCE.decode()]
    assert created["http_options"] == {
        "timeout": ingestion_config.http.timeout,
        "user_agent": ingestion_config.http.user_agent,
    }
    assert created["llm_options"]["base_url"] == ingestion_config.llm.base_url
    assert created["llm_options"]["model"] == ingestion_config.llm.model
    assert llm.closed
    assert created["http_client"].is_closed


def test_resumed_ingestion_starts_from_the_saved_offset(ingestion_config, monkeypatch):
    arxiv = FakeArxiv()
    install_fake_clients(monkeypatch, arxiv, ScriptedLLMClient())
    ingestion_config.paths.pipeline_metadata.write_text(
        json.dumps({"last_run_date": None, "last_start_index": 2}),
        encoding="utf-8",
    )

    processed = asyncio.run(run_ingestion(ingestion_config, logging.getLogger("udg-test"), start_index=None))

    assert processed == 0
    assert [request["start"] for request in arxiv.listing_requests] == ["2"]
