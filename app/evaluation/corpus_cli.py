import argparse
import asyncio
import json
from pathlib import Path

from app.core.config import get_settings
from app.evaluation.corpus import inspect_full_corpus
from app.ingestion.registry import DEFAULT_REGISTRY_PATH


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tractusmind-corpus-validate")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--report-only", action="store_true")
    return parser


async def _run(args: argparse.Namespace) -> int:
    report = await inspect_full_corpus(get_settings(), registry_path=args.registry)
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.passed or args.report_only else 1


def main() -> None:
    args = _parser().parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
