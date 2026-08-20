from app.chunking.models import KnowledgeChunk


def build_embedding_text(chunk: KnowledgeChunk) -> str:
    """Add lightweight retrieval context without polluting the stored source text."""

    context: list[str] = [
        f"Repository: {chunk.repository}",
        f"Component: {chunk.component}",
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
