from dataclasses import dataclass

from app.ingestion.models import SourceFile, SourceManifest
from app.state.store import StoredSourceFile


@dataclass(frozen=True)
class IncrementalPlan:
    added: tuple[SourceFile, ...]
    modified: tuple[SourceFile, ...]
    deleted_paths: tuple[str, ...]
    unchanged: tuple[SourceFile, ...]

    @property
    def changed_files(self) -> tuple[SourceFile, ...]:
        return self.added + self.modified

    @property
    def has_content_changes(self) -> bool:
        return bool(self.added or self.modified or self.deleted_paths)


def _source_file_path(source_file: SourceFile) -> str:
    return source_file.path


def build_incremental_plan(
    manifest: SourceManifest,
    previous: dict[str, StoredSourceFile],
) -> IncrementalPlan:
    current = {source_file.path: source_file for source_file in manifest.files}

    added: list[SourceFile] = []
    modified: list[SourceFile] = []
    unchanged: list[SourceFile] = []

    for path, source_file in current.items():
        stored = previous.get(path)
        if stored is None:
            added.append(source_file)
        elif stored.blob_sha != source_file.sha:
            modified.append(source_file)
        else:
            unchanged.append(source_file)

    deleted_paths = sorted(set(previous) - set(current))
    return IncrementalPlan(
        added=tuple(sorted(added, key=_source_file_path)),
        modified=tuple(sorted(modified, key=_source_file_path)),
        deleted_paths=tuple(deleted_paths),
        unchanged=tuple(sorted(unchanged, key=_source_file_path)),
    )
