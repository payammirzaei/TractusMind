import asyncio
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.engine import make_url
from starlette.background import BackgroundTask

from app.api.ops_auth import require_ops_admin
from app.core.config import Settings, get_settings
from app.ingestion.registry import DEFAULT_REGISTRY_PATH, load_source_registry

logger = structlog.get_logger()
_BACKUP_LOCK = asyncio.Lock()

router = APIRouter(
    prefix="/v1/ops",
    tags=["operations"],
    dependencies=[Depends(require_ops_admin)],
)


class BackupGenerationError(RuntimeError):
    """Raised when one of the durable backup components cannot be captured."""


def _postgres_environment(settings: Settings) -> tuple[dict[str, str], str]:
    url = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql":
        raise BackupGenerationError("DATABASE_URL is not PostgreSQL")
    if not url.database:
        raise BackupGenerationError("DATABASE_URL does not include a database name")

    env = os.environ.copy()
    if url.host:
        env["PGHOST"] = url.host
    if url.port:
        env["PGPORT"] = str(url.port)
    if url.username:
        env["PGUSER"] = url.username
    if url.password:
        env["PGPASSWORD"] = url.password

    sslmode = url.query.get("sslmode") or url.query.get("ssl")
    if sslmode:
        env["PGSSLMODE"] = str(sslmode)
    return env, url.database


async def _dump_postgres(settings: Settings, destination: Path) -> None:
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise BackupGenerationError("pg_dump is not installed in the API image")

    env, database = _postgres_environment(settings)
    process = await asyncio.create_subprocess_exec(
        pg_dump,
        "--dbname",
        database,
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--file",
        str(destination),
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await process.communicate()
    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        logger.error(
            "system_backup_postgres_failed",
            returncode=process.returncode,
            detail=detail[-1000:],
        )
        raise BackupGenerationError("PostgreSQL dump failed")
    if not destination.exists() or destination.stat().st_size == 0:
        raise BackupGenerationError("PostgreSQL dump was empty")


async def _snapshot_qdrant(settings: Settings, destination_dir: Path) -> Path:
    base_url = settings.qdrant_url.rstrip("/")
    headers = {"api-key": settings.qdrant_api_key} if settings.qdrant_api_key else {}
    timeout = httpx.Timeout(600.0, connect=15.0)
    snapshot_name: str | None = None

    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        follow_redirects=False,
    ) as client:
        try:
            # A full-storage snapshot captures every collection plus aliases on this
            # single-node Qdrant instance. It is deliberately independent of
            # QDRANT_COLLECTION so backup cannot silently miss or fail on a renamed
            # collection.
            created = await client.post(f"{base_url}/snapshots")
            created.raise_for_status()
            result = created.json().get("result") or {}
            snapshot_name = result.get("name")
            if not snapshot_name:
                raise BackupGenerationError("Qdrant did not return a snapshot name")

            safe_name = Path(str(snapshot_name)).name
            if safe_name != snapshot_name:
                raise BackupGenerationError("Qdrant returned an unsafe snapshot name")

            destination = destination_dir / safe_name
            snapshot_path = quote(snapshot_name, safe="")
            async with client.stream(
                "GET",
                f"{base_url}/snapshots/{snapshot_path}",
            ) as response:
                response.raise_for_status()
                with destination.open("wb") as handle:
                    async for chunk in response.aiter_bytes():
                        handle.write(chunk)

            if not destination.exists() or destination.stat().st_size == 0:
                raise BackupGenerationError("Qdrant snapshot was empty")
            return destination
        except BackupGenerationError:
            raise
        except httpx.HTTPStatusError as exc:
            logger.error(
                "system_backup_qdrant_failed",
                error=type(exc).__name__,
                status_code=exc.response.status_code,
                detail=exc.response.text[-500:],
            )
            raise BackupGenerationError("Qdrant snapshot failed") from exc
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.error("system_backup_qdrant_failed", error=type(exc).__name__)
            raise BackupGenerationError("Qdrant snapshot failed") from exc
        finally:
            if snapshot_name:
                snapshot_path = quote(snapshot_name, safe="")
                try:
                    cleanup = await client.delete(f"{base_url}/snapshots/{snapshot_path}")
                    cleanup.raise_for_status()
                except httpx.HTTPError:
                    logger.warning(
                        "system_backup_qdrant_snapshot_cleanup_failed",
                        snapshot_name=snapshot_name,
                    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_archive(
    archive_path: Path,
    postgres_path: Path,
    qdrant_path: Path,
    registry_path: Path | None,
    manifest: dict[str, object],
) -> None:
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.write(postgres_path, "postgres/tractusmind.dump")
        archive.write(qdrant_path, f"qdrant/{qdrant_path.name}")
        if registry_path is not None:
            archive.write(registry_path, "config/sources.toml")
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
        archive.writestr(
            "RESTORE.txt",
            "TractusMind full-system backup\n"
            "==============================\n\n"
            "Contents:\n"
            "- postgres/tractusmind.dump: PostgreSQL custom-format dump.\n"
            "- qdrant/*.snapshot: Qdrant collection snapshot.\n"
            "- config/sources.toml: curated source registry, when present.\n"
            "- manifest.json: checksums and capture metadata.\n\n"
            "Redis is intentionally excluded because it stores transient queue/lock state.\n"
            "Environment secrets are not exported as standalone files.\n\n"
            "Restore PostgreSQL with pg_restore into a clean database, then restore the Qdrant\n"
            "snapshot into the collection named in manifest.json. Validate application migrations\n"
            "and health checks before switching production traffic to the restored stores.\n",
        )


async def build_backup_archive(settings: Settings, workdir: Path) -> Path:
    created_at = datetime.now(UTC)
    postgres_dir = workdir / "postgres"
    qdrant_dir = workdir / "qdrant"
    postgres_dir.mkdir(parents=True, exist_ok=True)
    qdrant_dir.mkdir(parents=True, exist_ok=True)

    postgres_path = postgres_dir / "tractusmind.dump"
    await _dump_postgres(settings, postgres_path)
    qdrant_path = await _snapshot_qdrant(settings, qdrant_dir)

    registry_path: Path | None = None
    if DEFAULT_REGISTRY_PATH.exists():
        registry_path = workdir / "sources.toml"
        await asyncio.to_thread(shutil.copy2, DEFAULT_REGISTRY_PATH, registry_path)

    postgres_sha, qdrant_sha = await asyncio.gather(
        asyncio.to_thread(_sha256, postgres_path),
        asyncio.to_thread(_sha256, qdrant_path),
    )
    registry_sha = (
        await asyncio.to_thread(_sha256, registry_path)
        if registry_path is not None
        else None
    )

    sources = [
        {
            "id": source.id,
            "repository": source.full_name,
            "component": source.component,
            "ref": source.ref,
            "enabled": source.enabled,
        }
        for source in load_source_registry()
    ]
    manifest: dict[str, object] = {
        "format_version": 2,
        "created_at": created_at.isoformat(),
        "deploy_revision": os.environ.get("TRACTUSMIND_DEPLOY_REV"),
        "components": {
            "postgresql": {
                "file": "postgres/tractusmind.dump",
                "format": "pg_dump-custom",
                "sha256": postgres_sha,
            },
            "qdrant": {
                "file": f"qdrant/{qdrant_path.name}",
                "collection": settings.qdrant_collection,
                "sha256": qdrant_sha,
            },
            "source_registry": {
                "file": "config/sources.toml" if registry_path is not None else None,
                "sha256": registry_sha,
            },
            "redis": {
                "included": False,
                "reason": (
                    "Transient queues, locks, and runtime coordination are rebuilt after restore."
                ),
            },
        },
        "sources": sources,
        "security": {
            "standalone_environment_secrets_included": False,
            "note": (
                "The PostgreSQL dump contains application credential hashes required for recovery."
            ),
        },
    }

    filename = created_at.strftime("tractusmind-backup-%Y%m%dT%H%M%SZ.zip")
    archive_path = workdir / filename
    await asyncio.to_thread(
        _write_archive,
        archive_path,
        postgres_path,
        qdrant_path,
        registry_path,
        manifest,
    )
    return archive_path


@router.post("/backup", response_class=FileResponse)
async def download_system_backup(request: Request) -> FileResponse:
    if _BACKUP_LOCK.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A system backup is already being generated",
        )

    async with _BACKUP_LOCK:
        workdir = Path(tempfile.mkdtemp(prefix="tractusmind-backup-"))
        try:
            archive_path = await build_backup_archive(get_settings(), workdir)
        except BackupGenerationError as exc:
            shutil.rmtree(workdir, ignore_errors=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            shutil.rmtree(workdir, ignore_errors=True)
            logger.exception("system_backup_failed")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="System backup generation failed",
            ) from exc

    logger.info(
        "system_backup_ready",
        filename=archive_path.name,
        size_bytes=archive_path.stat().st_size,
    )
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=archive_path.name,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "X-TractusMind-Backup": "postgresql,qdrant,source-registry",
        },
        background=BackgroundTask(shutil.rmtree, workdir, ignore_errors=True),
    )
