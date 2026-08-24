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

    assert "Conversation topic: How do I create an asset" in query
    assert "What about contracts?" in query


def test_follow_up_does_not_pollute_retrieval_with_assistant_answer() -> None:
    query = retrieval_question("What else should I know about it?", _history())

    assert "How do I create an asset with the Tractus-X SDK?" in query
    assert "Use the asset service" not in query
    assert "[S1]" not in query
    assert "What else should I know about it?" in query


def test_third_turn_stays_anchored_to_original_standalone_topic() -> None:
    history = [
        ConversationTurn(
            question="How can I have Tractus-X for my small company?",
            answer="SMEs can use Tractus-X solutions with reduced infrastructure [S1].",
        ),
        ConversationTurn(
            question="What is the benefit?",
            answer="It improves interoperability and data sharing [S2].",
        ),
    ]

    query = retrieval_question("What is the hardest part?", history)

    assert "Conversation topic: How can I have Tractus-X for my small company?" in query
    assert "What is the benefit?" not in query
    assert "improves interoperability" not in query
    assert "Current question: What is the hardest part?" in query
    assert "implementation challenges" in query
    assert "prerequisites" in query


def test_routing_follow_up_uses_topic_anchor_but_not_assistant_vocabulary() -> None:
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

    assert "Conversation topic" in query


def test_formatted_history_is_clearly_role_delimited() -> None:
    rendered = format_history(_history())

    assert rendered.startswith("User: How do I create an asset")
    assert "Assistant: Use the asset service" in rendered
