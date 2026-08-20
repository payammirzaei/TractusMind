from app.chunking.models import KnowledgeChunk


def build_embedding_text(chunk: KnowledgeChunk) -> str:
    """Add semantic context for dense retrieval without mutating source text."""

    context: list[str] = [
        f"Repository: {chunk.repository}",
        f"Component: {chunk.component}",
        f"Version ref: {chunk.version_ref}",
        f"Path: {chunk.path}",
    ]

    if chunk.language:
        context.append(f"Language: {chunk.language}")
    if chunk.section_path:
        context.append(f"Section: {' > '.join(chunk.section_path)}")
    if chunk.parent_symbol and chunk.symbol:
        context.append(f"Symbol: {chunk.parent_symbol} > {chunk.symbol}")
    elif chunk.symbol:
        context.append(f"Symbol: {chunk.symbol}")

    return "\n".join(context) + "\n\n" + chunk.text


def build_sparse_text(chunk: KnowledgeChunk) -> str:
    """Favor exact identifiers, paths, headings, and source tokens for lexical retrieval."""

    identifiers = [
        chunk.repository,
        chunk.component,
        chunk.version_ref,
        chunk.path,
    ]
    if chunk.language:
        identifiers.append(chunk.language)
    identifiers.extend(chunk.section_path)
    if chunk.parent_symbol:
        identifiers.append(chunk.parent_symbol)
    if chunk.symbol:
        identifiers.append(chunk.symbol)

    return "\n".join(identifiers) + "\n\n" + chunk.text
