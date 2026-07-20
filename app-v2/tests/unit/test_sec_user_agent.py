"""SEC fair-access requires a User-Agent that carries a contact address.

`www.sec.gov` returns 403 for a bare product token like `quantinue/0.1`;
`data.sec.gov` happens not to enforce it, so the gap stayed invisible until the
ticker-map fetch was added. Mock transports never see this — only a live run does.
"""

import os

from quantinue.market_data.http_client import build_http_client, sec_user_agent


def test_default_user_agent_declares_a_contact_address() -> None:
    assert "@" in sec_user_agent()


def test_user_agent_is_overridable_for_deployment() -> None:
    previous = os.environ.get("QUANTINUE_HTTP_USER_AGENT")
    os.environ["QUANTINUE_HTTP_USER_AGENT"] = "acme/2.0 ops@acme.test"
    try:
        assert sec_user_agent() == "acme/2.0 ops@acme.test"
    finally:
        if previous is None:
            del os.environ["QUANTINUE_HTTP_USER_AGENT"]
        else:
            os.environ["QUANTINUE_HTTP_USER_AGENT"] = previous


def test_the_shared_client_keeps_the_bare_product_token() -> None:
    # NASDAQ resets the connection when the User-Agent carries a contact
    # address, so the contact-bearing form is attached per SEC request only.
    # The two upstreams demand opposite things.
    assert "@" not in build_http_client().headers["User-Agent"]
