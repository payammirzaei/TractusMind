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
    "does that",
    "can it",
    "can that",
    "same ",
)


def retrieval_question(question: str, history: list[ConversationTurn]) -> str:
    normalized = question.strip()
    if not history or not _needs_context(normalized):
        return normalized
    previous = history[-1].question.strip()[:800]
    return f"Previous user question: {previous}\nCurrent question: {normalized}"


def format_history(history: list[ConversationTurn]) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for turn in history:
        lines.append(f"User: {turn.question}")
        lines.append(f"Assistant: {turn.answer}")
    return "\n".join(lines)


def _needs_context(question: str) -> bool:
    lowered = question.casefold()
    if lowered.startswith(_FOLLOW_UP_PREFIXES):
        return True
    return len(question.split()) <= 6
