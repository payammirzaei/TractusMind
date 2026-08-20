import argparse
import asyncio
import json

from app.chunking import SmartChunker
from app.core.config import Settings, get_settings
from app.infra.postgres import create_postgres_engine
from app.infra.qdrant import create_qdrant_client
from app.ingestion.pipeline import SourceIngestionPipeline
from app.ingestion.registry import get_source
from app.ingestion.sync import IncrementalSourceSync
from app.retrieval.factory import (
    create_hybrid_retrieval_service,
    create_reranked_retrieval_service,
)
from app.routing.service import QueryRouter
from app.state import SourceStateStore


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

    index = subparsers.add_parser("index", help="Fetch, chunk, embed, and hybrid-index one source")
    index.add_argument("source_id")
    index.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional smoke-test file limit. Full indexing cleans stale source versions.",
    )

    sync = subparsers.add_parser(
        "sync",
        help="Incrementally synchronize one source using PostgreSQL file state",
    )
    sync.add_argument("source_id")

    search = subparsers.add_parser("search", help="Run routed retrieval against Qdrant")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--mode", choices=("dense", "hybrid", "rerank"), default="rerank")

    return parser


def _retrieval_services(settings: Settings):
    qdrant = create_qdrant_client(settings)
    retrieval = create_hybrid_retrieval_service(settings, qdrant)
    reranked = create_reranked_retrieval_service(settings, qdrant)
    return qdrant, retrieval, reranked


async def _run_search(args: argparse.Namespace, settings: Settings) -> None:
    route = QueryRouter().route(args.query)
    qdrant, retrieval, reranked = _retrieval_services(settings)
    try:
        if args.mode == "dense":
            hits = await retrieval.search_dense(
                args.query,
                limit=args.limit,
                route=route,
            )
        elif args.mode == "hybrid":
            hits = await retrieval.search_hybrid(
                args.query,
                limit=args.limit,
                prefetch_limit=settings.hybrid_prefetch_k,
                route=route,
            )
        else:
            hits = await reranked.search(
                args.query,
                limit=args.limit,
                route=route,
            )
    finally:
        await qdrant.close()

    print(
        json.dumps(
            {
                "query": args.query,
                "mode": args.mode,
                "route": route.model_dump(mode="json"),
                "result_count": len(hits),
                "results": [
                    {
                        "rank": rank,
                        "score": round(hit.score, 6),
                        "retrieval_score": (
                            round(hit.retrieval_score, 6)
                            if hit.retrieval_score is not None
                            else None
                        ),
                        "rerank_score": (
                            round(hit.rerank_score, 6)
                            if hit.rerank_score is not None
                            else None
                        ),
                        "debug_score": (
                            round(hit.debug_score, 6)
                            if hit.debug_score is not None
                            else None
                        ),
                        "retrieval_methods": hit.retrieval_methods,
                        "source_id": hit.source_id,
                        "repository": hit.repository,
                        "component": hit.component,
                        "version_ref": hit.version_ref,
                        "snapshot_commit_sha": hit.snapshot_commit_sha,
                        "content_commit_sha": hit.commit_sha,
                        "path": hit.path,
                        "kind": hit.kind,
                        "language": hit.language,
                        "symbol": hit.symbol,
                        "parent_symbol": hit.parent_symbol,
                        "section_path": hit.section_path,
                        "start_line": hit.start_line,
                        "end_line": hit.end_line,
                        "source_url": hit.source_url,
                        "preview": hit.text[:500],
                    }
                    for rank, hit in enumerate(hits, start=1)
                ],
            },
            indent=2,
        )
    )


async def _run_sync(args: argparse.Namespace, settings: Settings) -> None:
    source = get_source(args.source_id)
    engine = create_postgres_engine(settings)
    qdrant = create_qdrant_client(settings)
    retrieval = create_hybrid_retrieval_service(settings, qdrant)
    state = SourceStateStore(engine)

    try:
        async with SourceIngestionPipeline(token=settings.github_token) as pipeline:
            result = await IncrementalSourceSync(
                pipeline=pipeline,
                retrieval=retrieval,
                state=state,
            ).sync(source)
    finally:
        await qdrant.close()
        await engine.dispose()

    print(json.dumps(result.__dict__, indent=2))


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()

    if args.command == "search":
        await _run_search(args, settings)
        return
    if args.command == "sync":
        await _run_sync(args, settings)
        return

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

        if args.command in {"chunk", "index"}:
            chunks = SmartChunker().chunk_many(documents)

            if args.command == "index":
                qdrant, retrieval, _ = _retrieval_services(settings)
                try:
                    indexed = await retrieval.index(
                        chunks,
                        remove_stale_source_versions=args.limit is None,
                    )
                finally:
                    await qdrant.close()

                print(
                    json.dumps(
                        {
                            "source_id": manifest.source_id,
                            "repository": manifest.repository,
                            "version_ref": manifest.requested_ref,
                            "commit_sha": manifest.commit_sha,
                            "document_count": len(documents),
                            "chunk_count": len(chunks),
                            "indexed_count": indexed,
                            "collection": retrieval.store.collection_name,
                            "dense_model": settings.embedding_model,
                            "sparse_model": settings.sparse_embedding_model,
                            "full_source_index": args.limit is None,
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
                        "version_ref": manifest.requested_ref,
                        "commit_sha": manifest.commit_sha,
                        "document_count": len(documents),
                        "chunk_count": len(chunks),
                        "chunk_kinds": sorted({chunk.kind.value for chunk in chunks}),
                        "chunks": [
                            {
                                "chunk_id": chunk.chunk_id,
                                "version_ref": chunk.version_ref,
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
                    "version_ref": manifest.requested_ref,
                    "commit_sha": manifest.commit_sha,
                    "documents": [
                        {
                            "document_id": document.document_id,
                            "version_ref": document.version_ref,
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
