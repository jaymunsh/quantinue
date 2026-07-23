from datetime import timedelta

from quantinue.orchestration.policy import EventIngestionConfig


def test_event_sources_have_exact_cadences_and_explicit_overlap() -> None:
    # Given
    config = EventIngestionConfig()

    # When
    schedules = {
        name: (source.cadence, source.overlap)
        for name, source in config.sources.items()
    }

    # Then
    assert schedules == {
        "sec": (timedelta(minutes=30), timedelta(minutes=60)),
        "news": (timedelta(minutes=15), timedelta(minutes=30)),
        "wire": (timedelta(minutes=10), timedelta(minutes=20)),
    }
