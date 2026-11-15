import pytest

from assistant_core.config import DEFAULT_SYSTEM_PROMPT, validate_local_ollama_url, validate_model_tag


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:11434",
        "http://ollama.example.com:11434",
        "http://127.0.0.1:11434/proxy",
        "http://user:pass@localhost:11434",
    ],
)
def test_ollama_url_rejects_non_local_or_ambiguous_urls(url):
    with pytest.raises(ValueError):
        validate_local_ollama_url(url)


@pytest.mark.parametrize("url", ["http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"])
def test_ollama_url_accepts_loopback_only(url):
    assert validate_local_ollama_url(url) == url


@pytest.mark.parametrize("model", ["qwen3:cloud", "qwen3:4b:cloud", "qwen3:8b-cloud", "llama3.1:8b", "https://host/model"])
def test_model_policy_rejects_cloud_and_unverified_families(model):
    with pytest.raises(ValueError):
        validate_model_tag(model)


def test_model_policy_accepts_local_qwen3_tag():
    assert validate_model_tag("QWEN3:4B") == "qwen3:4b"


def test_default_persona_allows_permissioned_tools_without_overclaiming():
    assert "tools explicitly provided" in DEFAULT_SYSTEM_PROMPT
    assert "permission and confirmation requirements" in DEFAULT_SYSTEM_PROMPT
    assert "no tools in this version" not in DEFAULT_SYSTEM_PROMPT

