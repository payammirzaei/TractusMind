import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationTurn:
    question: str
    answer: str


_FOLLOW_UP_PREFIXES = (
    "and ",
    "also ",
    "what about",
    "how about",
    "what if",
    "what else",
    "tell me more",
    "continue",
    "go on",
    "anything else",
    "does that",
    "can it",
    "can that",
    "same ",
)
_ANAPHORIC_WORDS = {
    "it",
    "that",
    "this",
    "these",
    "those",
    "them",
    "they",
    "same",
}
_CITATION_RE = re.compile(r"\s*\[S\d+\]")
_RETRIEVAL_CONTEXT_TURNS = 2
_RETRIEVAL_ANSWER_CHARS = 1_200


def retrieval_question(question: str, history: list[ConversationTurn]) -> str:
    """Resolve conversational follow-ups into a retrieval query with recent topic context.

    Retrieval needs more than the previous user sentence for questions such as "what else
    should I know about it?". The assistant answer often contains the concrete entities and
    concepts needed to recover the topic. Keep the context small and citation-free so it helps
    semantic search without turning the entire conversation into the query.
    """

    normalized = question.strip()
    if not history or not _needs_context(normalized):
        return normalized

    lines = ["Recent conversation context for retrieval:"]
    for turn in history[-_RETRIEVAL_CONTEXT_TURNS:]:
        previous_question = " ".join(turn.question.split())[:800]
        previous_answer = _retrieval_answer(turn.answer)
        if previous_question:
            lines.append(f"Previous user question: {previous_question}")
        if previous_answer:
            lines.append(f"Previous assistant answer: {previous_answer}")
    lines.append(f"Current question: {normalized}")
    return "\n".join(lines)


def format_history(history: list[ConversationTurn]) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for turn in history:
        lines.append(f"User: {turn.question}")
        lines.append(f"Assistant: {turn.answer}")
    return "\n".join(lines)


def _retrieval_answer(answer: str) -> str:
    without_citations = _CITATION_RE.sub("", answer)
    return " ".join(without_citations.split())[:_RETRIEVAL_ANSWER_CHARS]


def _needs_context(question: str) -> bool:
    lowered = question.casefold()
    if lowered.startswith(_FOLLOW_UP_PREFIXES):
        return True
    tokens = {
        token.strip(".,?!:;()[]{}\"'")
        for token in lowered.split()
    }
    return bool(tokens & _ANAPHORIC_WORDS)
