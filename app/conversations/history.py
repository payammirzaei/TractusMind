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
_ASSESSMENT_TERMS = (
    "hardest part",
    "most difficult",
    "main challenge",
    "biggest challenge",
    "most challenging",
)
_TOPIC_CHARS = 1_000


def retrieval_question(question: str, history: list[ConversationTurn]) -> str:
    """Resolve a follow-up against the stable user topic instead of rolling answer text.

    Assistant answers are useful to the generator but are noisy retrieval input: a long answer
    about benefits, releases, or versions can pull the next follow-up away from the user's
    original task. For retrieval, anchor the chain to the most recent standalone user question
    and combine it with the current follow-up. This keeps third, fourth, and later turns on topic.
    """

    normalized = question.strip()
    if not history or not _needs_context(normalized):
        return normalized

    anchor = _topic_anchor(history)
    lines = [
        f"Conversation topic: {_compact(anchor, _TOPIC_CHARS)}",
        f"Current question: {normalized}",
    ]
    if _is_assessment(normalized):
        lines.append(
            "Retrieval focus: implementation challenges, prerequisites, deployment, "
            "configuration, operations, security, identity, connector setup, and maintenance."
        )
    return "\n".join(lines)


def routing_question(question: str, history: list[ConversationTurn]) -> str:
    """Route follow-ups using the stable user topic and no assistant-answer vocabulary."""

    normalized = question.strip()
    if not history or not _needs_context(normalized):
        return normalized

    anchor = _topic_anchor(history)
    return (
        f"Conversation topic: {_compact(anchor, _TOPIC_CHARS)}\n"
        f"Current question: {normalized}"
    )


def format_history(history: list[ConversationTurn]) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for turn in history:
        lines.append(f"User: {turn.question}")
        lines.append(f"Assistant: {turn.answer}")
    return "\n".join(lines)


def _topic_anchor(history: list[ConversationTurn]) -> str:
    for turn in reversed(history):
        candidate = turn.question.strip()
        if candidate and not _needs_context(candidate):
            return candidate
    return history[0].question.strip()


def _compact(text: str, limit: int) -> str:
    return " ".join(text.split())[:limit]


def _is_assessment(question: str) -> bool:
    lowered = question.casefold()
    return any(term in lowered for term in _ASSESSMENT_TERMS)


def _needs_context(question: str) -> bool:
    lowered = question.casefold()
    if lowered.startswith(_FOLLOW_UP_PREFIXES):
        return True
    tokens = {
        token.strip(".,?!:;()[]{}\"'")
        for token in lowered.split()
    }
    return bool(tokens & _ANAPHORIC_WORDS)
