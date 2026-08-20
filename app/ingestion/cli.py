import argparse
import asyncio
import json

from app.chunking import SmartChunker
from app.core.config import get_settings
from app.ingestion.pipeline import SourceIngestionPipeline
from app.ingestion.registry import get_source


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tractusmind-ingest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="Resolve a source to a pinned manifest")
    discover.add_argument("source_id")

    fetch = subparsers.add_parser("fetch", help="Fetch selected source documents")
    fetch.add_argument("source_id")
    fetch.add_argument("--limit", type=int, default=3)

    chunk = subparsers.add_parser("chunk", help="Fetch and smart-chunk selected source documents")
    chunk.add_argument("source_id")
    chunk.add_argument("--limit", type=int, default=3)

    return parser


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    source = get_source(args.source_id)

    async with SourceIngestionPipeline(token=settings.github_token) as pipeline:
        if args.command == "discover":
            manifest = await pipeline.discover(source)
            print(
                json.dumps(
                    {
                        "source_id": manifest.source_id,
                        "repository": manifest.repository,
                        "requested_ref": manifest.requested_ref,
                        "commit_sha": manifest.commit_sha,
                        "file_count": len(manifest.files),
                        "content_types": sorted(
                            {source_file.content_type for source_file in manifest.files}
                        ),
                    },
                    indent=2,
                )
            )
            return

        manifest, documents = await pipeline.fetch(source, limit=args.limit)

        if args.command == "chunk":
            chunks = SmartChunker().chunk_many(documents)
            print(
                json.dumps(
                    {
                        "source_id": manifest.source_id,
                        "repository": manifest.repository,
                        "commit_sha": manifest.commit_sha,
                        "document_count": len(documents),
                        "chunk_count": len(chunks),
                        "chunk_kinds": sorted({chunk.kind.value for chunk in chunks}),
                        "chunks": [
                            {
                                "chunk_id": chunk.chunk_id,
                                "path": chunk.path,
                                "kind": chunk.kind.value,
                                "symbol": chunk.symbol,
                                "parent_symbol": chunk.parent_symbol,
                                "section_path": chunk.section_path,
                                "start_line": chunk.start_line,
                                "end_line": chunk.end_line,
                                "part": chunk.part,
                                "source_url": chunk.line_source_url,
                            }
                            for chunk in chunks[:20]
                        ],
                    },
                    indent=2,
                )
            )
            return

        print(
            json.dumps(
                {
                    "source_id": manifest.source_id,
                    "repository": manifest.repository,
                    "commit_sha": manifest.commit_sha,
                    "documents": [
                        {
                            "document_id": document.document_id,
                            "path": document.path,
                            "language": document.language,
                            "content_type": document.content_type,
                            "size_bytes": document.size_bytes,
                            "content_sha256": document.content_sha256,
                            "source_url": document.source_url,
                        }
                        for document in documents
                    ],
                },
                indent=2,
            )
        )


def main() -> None:
    args = _parser().parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
