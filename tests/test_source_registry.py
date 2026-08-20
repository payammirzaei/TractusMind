from app.ingestion.github import _content_type, _is_selected
from app.ingestion.registry import get_enabled_sources, get_source


def test_registry_contains_critical_sources() -> None:
    source_ids = {source.id for source in get_enabled_sources()}
    assert "tractusx-sdk" in source_ids
    assert "tractusx-edc" in source_ids
    assert "semantic-models" in source_ids


def test_archived_sources_are_blocked_by_default() -> None:
    assert all(not source.allow_archived for source in get_enabled_sources())


def test_sdk_selection_keeps_code_and_excludes_build_artifacts() -> None:
    source = get_source("tractusx-sdk")
    assert _is_selected("tractusx_sdk/dataspace/services/connector.py", source)
    assert _is_selected("examples/consumer.py", source)
    assert not _is_selected("build/generated/consumer.py", source)


def test_content_types() -> None:
    assert _content_type("README.md") == "documentation"
    assert _content_type("src/Connector.java") == "code"
    assert _content_type("models/Part.ttl") == "semantic_model"
    assert _content_type("config/application.yaml") == "configuration"
