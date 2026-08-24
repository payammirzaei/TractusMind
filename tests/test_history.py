from app.conversations.history import (
    ConversationTurn,
    format_history,
    retrieval_question,
    routing_question,
)


def _history() -> list[ConversationTurn]:
    return [
        ConversationTurn(
            question="How do I create an asset with the Tractus-X SDK?",
            answer="Use the asset service [S1].",
        )
    ]


def test_follow_up_uses_previous_user_question_for_retrieval() -> None:
    query = retrieval_question("What about contracts?", _history())

    assert "How do I create an asset" in query
    assert "What about contracts?" in query


def test_follow_up_uses_previous_answer_for_topic_resolution() -> None:
    query = retrieval_question("What else should I know about it?", _history())

    assert "Previous assistant answer: Use the asset service." in query
    assert "[S1]" not in query
    assert "What else should I know about it?" in query


def test_follow_up_keeps_two_recent_turns_when_last_answer_is_unhelpful() -> None:
    history = [
        ConversationTurn(
            question="How hard is it to run Tractus-X in a small company?",
            answer="You need deployment, identity, connector and operations knowledge [S1].",
        ),
        ConversationTurn(
            question="What else should I know about it?",
            answer="I don't have enough grounded Tractus-X evidence to answer this reliably.",
        ),
    ]

    query = retrieval_question("What is the hardest part?", history)

    assert "small company" in query
    assert "deployment, identity, connector and operations knowledge" in query
    assert "What is the hardest part?" in query


def test_routing_follow_up_uses_user_context_but_not_assistant_vocabulary() -> None:
    history = [
        ConversationTurn(
            question="I want to run Tractus-X on my server. What do I need?",
            answer=(
                "Use Ubuntu version 22.04 and install the required tools. "
                "Check the release documentation [S1]."
            ),
        )
    ]

    query = routing_question("What is the hardest part of this process?", history)

    assert "run Tractus-X on my server" in query
    assert "hardest part of this process" in query
    assert "Ubuntu version" not in query
    assert "release documentation" not in query


def test_explicit_new_question_does_not_inherit_previous_retrieval_context() -> None:
    question = "Explain the EDC control plane and data plane architecture in detail."

    assert retrieval_question(question, _history()) == question
    assert routing_question(question, _history()) == question


def test_short_standalone_question_does_not_inherit_previous_context() -> None:
    question = "Explain EDC control plane."

    assert retrieval_question(question, _history()) == question
    assert routing_question(question, _history()) == question


def test_anaphoric_follow_up_uses_previous_user_question() -> None:
    query = retrieval_question("How does that work?", _history())

    assert "Previous user question" in query


def test_formatted_history_is_clearly_role_delimited() -> None:
    rendered = format_history(_history())

    assert rendered.startswith("User: How do I create an asset")
    assert "Assistant: Use the asset service" in rendered
