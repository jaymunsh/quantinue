"""MVP-2 vocabularies added to the canonical ontology."""

from quantinue.core.ontology import AccountStatus, LlmTask, Side, UserRole


def test_side_supports_sell() -> None:
    assert Side.SELL == "sell"
    assert {item.value for item in Side} == {"buy", "hold", "sell"}


def test_account_status_vocabulary() -> None:
    assert {item.value for item in AccountStatus} == {"active", "paused", "closed"}


def test_user_role_vocabulary() -> None:
    assert {item.value for item in UserRole} == {"admin", "user"}


def test_llm_task_vocabulary_matches_call_sites() -> None:
    assert {item.value for item in LlmTask} == {
        "disclosure",
        "news",
        "strategy",
        "critic",
        "review",
    }
