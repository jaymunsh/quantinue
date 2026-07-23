import logging

from quantinue.core.logging import configure_logging


def test_http_client_loggers_do_not_emit_secret_bearing_urls() -> None:
    # Given
    logging.getLogger().setLevel(logging.INFO)
    logger_names = ("httpx", "httpcore", "httpx2", "httpcore2", "hpack")
    for name in logger_names:
        logging.getLogger(name).setLevel(logging.NOTSET)

    # When
    configure_logging(debug=False)

    # Then
    for name in logger_names:
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING
