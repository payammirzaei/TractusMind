import argparse
import asyncio
import json

from app.core.config import get_settings
from app.ingestion.github import GitHubSourceScanner
from app.ingestion.registry import get_enabled_sources, get_source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover version-pinned Tractus-X source manifests")
    parser.add_argument(
        "--source",
        action="append",
        dest="source_ids",
        help="Source id from config/sources.toml. Repeat to select multiple sources.",
    )
    return parser.parse_args()


async def run(source_ids: list[str] | None) -> None:
    settings = get_settings()
    sources = (
        [get_source(source_id) for source_id in source_ids]
        if source_ids
        else get_enabled_sources()
    )

    async with GitHubSourceScanner(token=settings.github_token) as scanner:
        for source in sources:
            manifest = await scanner.discover(source)
            print(json.dumps(manifest.model_dump(), indent=2))


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args.source_ids))
