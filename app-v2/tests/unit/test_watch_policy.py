import pytest
from pydantic import ValidationError

from quantinue.orchestration.policy import Mvp2Config, WatchConfig


def test_watch_config_defaults_to_a_disabled_one_minute_regular_session() -> None:
    # Given / When
    config = WatchConfig()

    # Then
    assert config.enabled is False
    assert config.interval_minutes == 1
    assert config.session == "regular"


def test_mvp2_config_owns_the_watch_config() -> None:
    # Given / When
    config = Mvp2Config.model_validate(
        {"watch": {"enabled": True, "interval_minutes": 5, "session": "regular"}}
    )

    # Then
    assert config.watch == WatchConfig(enabled=True, interval_minutes=5)


def test_watch_config_rejects_an_unknown_session() -> None:
    # Given / When / Then
    with pytest.raises(ValidationError):
        WatchConfig.model_validate({"session": "extended"})
