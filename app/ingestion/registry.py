import tomllib
from pathlib import Path

from app.ingestion.models import SourceDefinition

DEFAULT_REGISTRY_PATH = Path("config/sources.toml")


def load_source_registry(path: Path = DEFAULT_REGISTRY_PATH) -> list[SourceDefinition]:
    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    sources = [SourceDefinition.model_validate(item) for item in raw.get("sources", [])]
    ids = [source.id for source in sources]
    if len(ids) != len(set(ids)):
        raise ValueError("Source registry contains duplicate source ids")

    return sources


def get_enabled_sources(path: Path = DEFAULT_REGISTRY_PATH) -> list[SourceDefinition]:
    return [source for source in load_source_registry(path) if source.enabled]


def get_source(source_id: str, path: Path = DEFAULT_REGISTRY_PATH) -> SourceDefinition:
    for source in load_source_registry(path):
        if source.id == source_id:
            return source
    raise KeyError(f"Unknown source id: {source_id}")
