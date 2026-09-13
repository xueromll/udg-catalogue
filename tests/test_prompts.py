from udg_catalogue.config import KEY_COLUMN, MEASUREMENT_FIELDS
from udg_catalogue.pipeline import EXTRACTION_RESULT_KEY
from udg_catalogue.prompts import EXTRACTION_PROMPT, RELEVANCE_PROMPT


def test_prompts_mention_json_as_json_mode_requires():
    assert "JSON" in EXTRACTION_PROMPT
    assert "JSON" in RELEVANCE_PROMPT


def test_extraction_prompt_asks_for_every_exported_field_under_the_result_key():
    assert f'"{EXTRACTION_RESULT_KEY}"' in EXTRACTION_PROMPT
    for field in (KEY_COLUMN, *MEASUREMENT_FIELDS):
        assert f'"{field}"' in EXTRACTION_PROMPT


def test_relevance_prompt_asks_for_the_relevant_verdict():
    assert '{"relevant": true}' in RELEVANCE_PROMPT
    assert '{"relevant": false}' in RELEVANCE_PROMPT
