import pytest

from prompts import EXTRACTION_PROMPT, FILTER_PROMPT, STRICT_SIMULATION_PROMPT

def test_prompts_not_empty():
    assert isinstance(EXTRACTION_PROMPT, str) and len(EXTRACTION_PROMPT) > 0
    assert isinstance(FILTER_PROMPT, str) and len(FILTER_PROMPT) > 0
    assert isinstance(STRICT_SIMULATION_PROMPT, str) and len(STRICT_SIMULATION_PROMPT) > 0

def test_prompts_contain_key_instructions():
    assert "JSON object" in EXTRACTION_PROMPT
    assert "relevant" in FILTER_PROMPT
    assert "observational" in STRICT_SIMULATION_PROMPT.lower()