from app.routing.filters import build_route_filter
from app.routing.models import QueryIntent, QueryRoute
from app.routing.service import QueryRouter


def test_sdk_query_routes_to_sdk_and_docs() -> None:
    route = QueryRouter().route("How do I create an asset with the Tractus-X SDK?")

    assert route.intent is QueryIntent.SDK
    assert route.source_ids == ["tractusx-sdk", "tractusx-docs"]
    assert "matched_sdk" in route.reasons


def test_debug_query_keeps_debug_intent_and_component_scope() -> None:
    route = QueryRouter().route("EDC connector returns 500 error during transfer")

    assert route.intent is QueryIntent.DEBUG
    assert "tractusx-edc" in route.source_ids
    assert "tractusx-docs" in route.source_ids
    assert "tractusx-sdk" not in route.source_ids


def test_semantic_version_query_adds_release_source_without_hard_version_filter() -> None:
    route = QueryRouter().route("What changed for SAMM semantic models in release 24.05?")

    assert route.intent is QueryIntent.SEMANTIC
    assert route.version == "24.05"
    assert "semantic-models" in route.source_ids
    assert "tractusx-release" in route.source_ids
    assert route.ref is None


def test_semantic_model_hyphen_query_routes_to_semantic_source() -> None:
    route = QueryRouter().route("Which semantic-model files define the relevant aspect?")

    assert route.intent is QueryIntent.SEMANTIC
    assert route.source_ids == ["semantic-models", "tractusx-docs"]
    assert "matched_semantic_models" in route.reasons


def test_generic_asset_query_routes_across_sdk_and_edc() -> None:
    route = QueryRouter().route("How do I create an asset?")

    assert "tractusx-sdk" in route.source_ids
    assert "tractusx-edc" in route.source_ids
    assert "tractusx-docs" in route.source_ids


def test_explicit_ref_and_commit_become_exact_filter_constraints() -> None:
    route = QueryRouter().route(
        "Check EDC ref:v0.9.0 commit:abcdef1234567 for this connector behavior"
    )
    query_filter = build_route_filter(route)

    assert route.ref == "v0.9.0"
    assert route.commit_sha == "abcdef1234567"
    assert query_filter is not None
    dumped = query_filter.model_dump(mode="json")
    must = dumped["must"]
    assert any(condition.get("key") == "source_id" for condition in must)
    assert any(condition.get("key") == "version_ref" for condition in must)
    assert any(condition.get("key") == "snapshot_commit_sha" for condition in must)


def test_general_query_has_no_hard_qdrant_filter() -> None:
    route = QueryRouter().route("Explain the Tractus-X ecosystem at a high level")

    assert route.intent is QueryIntent.GENERAL
    assert route.source_ids == []
    assert build_route_filter(route) is None


def test_route_model_reports_filter_presence() -> None:
    assert QueryRoute().has_filter is False
    assert QueryRoute(source_ids=["tractusx-sdk"]).has_filter is True
