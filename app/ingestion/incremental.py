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
    key = lambda source_file: source_file.path
    return IncrementalPlan(
        added=tuple(sorted(added, key=key)),
        modified=tuple(sorted(modified, key=key)),
        deleted_paths=tuple(deleted_paths),
        unchanged=tuple(sorted(unchanged, key=key)),
    )
