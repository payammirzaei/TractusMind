from app.conversations.history import ConversationTurn, format_history, retrieval_question


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


def test_explicit_new_question_does_not_inherit_previous_retrieval_context() -> None:
    question = "Explain the EDC control plane and data plane architecture in detail."

    assert retrieval_question(question, _history()) == question


def test_short_standalone_question_does_not_inherit_previous_context() -> None:
    question = "Explain EDC control plane."

    assert retrieval_question(question, _history()) == question


def test_anaphoric_follow_up_uses_previous_user_question() -> None:
    query = retrieval_question("How does that work?", _history())

    assert "Previous user question" in query


def test_formatted_history_is_clearly_role_delimited() -> None:
    rendered = format_history(_history())

    assert rendered.startswith("User: How do I create an asset")
    assert "Assistant: Use the asset service" in rendered
