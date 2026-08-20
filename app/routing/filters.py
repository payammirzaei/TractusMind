from qdrant_client import models

from app.routing.models import QueryRoute


def build_route_filter(route: QueryRoute | None) -> models.Filter | None:
    """Translate an inspectable route into exact Qdrant payload filters."""

    if route is None:
        return None

    must: list[models.FieldCondition] = []
    if route.source_ids:
        must.append(
            models.FieldCondition(
                key="source_id",
                match=models.MatchAny(any=route.source_ids),
            )
        )
    if route.ref:
        must.append(
            models.FieldCondition(
                key="version_ref",
                match=models.MatchValue(value=route.ref),
            )
        )
    if route.commit_sha:
        must.append(
            models.FieldCondition(
                key="snapshot_commit_sha",
                match=models.MatchValue(value=route.commit_sha),
            )
        )

    return models.Filter(must=must) if must else None
