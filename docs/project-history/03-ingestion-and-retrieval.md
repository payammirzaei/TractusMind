# 03 — Knowledge Ingestion and Retrieval Pipeline

## Curated source registry

Knowledge ingestion is allowlist-based. Each source definition controls:

- GitHub owner/repository,
- component identity,
- priority,
- requested ref,
- enabled/disabled state,
- archive policy,
- maximum file size,
- include globs,
- exclude globs.

This prevents the system from indexing generated assets, build outputs, archived material or unrelated organization repositories merely because they are reachable.

## Immutable source discovery

The ingestion pipeline resolves a configured ref to a concrete source manifest and snapshot commit before fetching content.

The manifest records enough state to make an ingestion run reproducible:

- source ID,
- repository,
- requested ref,
- resolved commit SHA,
- selected files,
- content metadata.

A truncated GitHub repository tree is treated as an error rather than silently producing an incomplete corpus.

## Content fetching

Selected files are fetched through a bounded-concurrency GitHub client with timeout/retry/circuit-breaker behavior.

Content is normalized into `RawDocument` objects with provenance such as:

- path,
- language,
- content type,
- source/ref/snapshot identity,
- file size/hash,
- source URL.

## Smart chunking

We built separate chunking strategies instead of splitting all files by arbitrary character windows.

### Markdown/documentation

Markdown is chunked around logical documentation structure while preserving source line ranges.

### Structured content

JSON, YAML, semantic models and other structured data receive a dedicated structured-data path.

### Source code

Code chunking is symbol-aware. The system attempts to preserve declarations such as classes, functions and methods, including symbol names and parent symbols.

For Java/Kotlin/TypeScript/JavaScript, tree-sitter remains useful for syntax-aware parsing.

For Python, the implementation was later changed to use Python's standard-library AST after a real upstream Tractus-X file triggered a native tree-sitter SIGSEGV in GitHub Actions. That incident and fix are documented in [`08-incidents-and-decisions.md`](./08-incidents-and-decisions.md).

### Fallback

Unsupported or non-structured text falls back to bounded line-based chunking with overlap.

## Incremental synchronization

A source synchronization run does not blindly re-embed the entire source every time.

PostgreSQL stores source/file state. The incremental planner compares the new manifest against the previous source state and classifies files as:

- added,
- modified,
- deleted,
- unchanged.

Only added/modified content needs to be fetched and re-embedded. Deleted/stale vectors are removed or updated accordingly.

The sync result records operational counters including:

- discovered files,
- added/modified/deleted/unchanged files,
- fetched documents,
- generated chunks,
- indexed chunks.

## Qdrant indexing

Each knowledge chunk stores:

- a dense vector,
- a sparse BM25 vector,
- provenance payload,
- source/ref/snapshot metadata,
- path/language/kind,
- symbol/parent symbol where applicable,
- source line boundaries,
- debug text.

Collections are model-scoped to prevent incompatible embedding configurations from being mixed accidentally.

Payload indexes are created for commonly filtered provenance fields.

## Background ingestion

The same sync path is available through Dramatiq workers rather than only through a local CLI. A scheduler can periodically enqueue enabled sources.

Operationally, this separates:

- API request latency,
- expensive GitHub fetch/chunk/embed work,
- periodic source refresh behavior.

## Full-corpus validation work

We later added self-contained GitHub Actions infrastructure for corpus validation:

- ephemeral PostgreSQL,
- ephemeral Qdrant,
- GitHub Actions job token for public Tractus-X repositories,
- clean schema bootstrap,
- synchronization of all six enabled sources,
- corpus/ref validation,
- retrieval benchmark,
- debug benchmark,
- evidence-threshold calibration,
- artifact/reproducibility output.

This eliminated the need for a separately hosted validation database or Qdrant instance.

The first complete corpus run exposed a real native Python parsing failure, which was then fixed through PR #11. This is a good example of why the project moved from unit-only confidence to real corpus execution.

See also:

- [`../incremental-ingestion.md`](../incremental-ingestion.md)
- [`../background-ingestion.md`](../background-ingestion.md)
- [`../full-corpus-validation.md`](../full-corpus-validation.md)
