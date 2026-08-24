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
    "what is the hardest part",
    "what's the hardest part",
    "which part",
    "which step",
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
_ROUTING_CONTEXT_TURNS = 2


def retrieval_question(question: str, history: list[ConversationTurn]) -> str:
    """Resolve conversational follow-ups into a retrieval query with recent topic context.

    Retrieval benefits from recent assistant answers because those answers often contain the
    concrete entities and concepts hidden behind follow-ups such as "what else should I know?".
    Keep the context small and citation-free so it helps semantic search without turning the
    entire conversation into the query.
    """

    normalized = question.strip()
    if not history or not _needs_context(normalized):
        return normalized

    lines = ["Recent conversation context for retrieval:"]
    for turn in history[-_RETRIEVAL_CONTEXT_TURNS:]:
        previous_question = _compact(turn.question, 800)
        previous_answer = _retrieval_answer(turn.answer)
        if previous_question:
            lines.append(f"Previous user question: {previous_question}")
        if previous_answer:
            lines.append(f"Previous assistant answer: {previous_answer}")
    lines.append(f"Current question: {normalized}")
    return "\n".join(lines)


def routing_question(question: str, history: list[ConversationTurn]) -> str:
    """Build routing context without assistant-answer vocabulary pollution.

    The deterministic router looks for high-signal words such as "version", "release", "EDC",
    and "connector". Feeding previous assistant answers into it can accidentally route a generic
    follow-up to the wrong domain just because an earlier answer happened to contain one of those
    words. For follow-ups, use recent *user questions only* to preserve topic continuity while
    keeping routing intent clean.
    """

    normalized = question.strip()
    if not history or not _needs_context(normalized):
        return normalized

    lines = ["Recent user context for routing:"]
    for turn in history[-_ROUTING_CONTEXT_TURNS:]:
        previous_question = _compact(turn.question, 800)
        if previous_question:
            lines.append(f"Previous user question: {previous_question}")
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


def _compact(text: str, limit: int) -> str:
    return " ".join(text.split())[:limit]


def _retrieval_answer(answer: str) -> str:
    without_citations = _CITATION_RE.sub("", answer)
    return _compact(without_citations, _RETRIEVAL_ANSWER_CHARS)


def _needs_context(question: str) -> bool:
    lowered = question.casefold()
    if lowered.startswith(_FOLLOW_UP_PREFIXES):
        return True
    tokens = {
        token.strip(".,?!:;()[]{}\"'")
        for token in lowered.split()
    }
    return bool(tokens & _ANAPHORIC_WORDS)
