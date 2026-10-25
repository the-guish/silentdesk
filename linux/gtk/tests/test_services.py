"""What each service asks for to connect."""

from silentdesk.contract import ServiceStatus

from silentdesk_gtk import services


def test_required_fields_left_empty_are_named():
    assert services.missing("github", {"token": " ", "server": ""}) == ["Personal access token"]
    assert services.missing("jira", {"site": "acme.atlassian.net", "token": "t"}) == []
    assert services.missing("gmail", {}) == []


def test_connect_sends_trimmed_fields_without_empty_optional_ones():
    values = {"site": " acme.atlassian.net ", "email": "", "token": "t "}
    assert services.connect_params("jira", values) == {"site": "acme.atlassian.net", "token": "t"}


def test_each_service_says_where_it_stands():
    assert services.describe(ServiceStatus("gmail", True, True, "ana@example.com")) == "ana@example.com"
    assert services.describe(ServiceStatus("gmail", False, False, None)) == "Set SILENTDESK_GOOGLE_CLIENT_ID to connect"
    assert services.describe(ServiceStatus("slack", True, False, None)) == (
        "Not connected · signs in through your browser"
    )
    assert services.describe(ServiceStatus("github", True, False, None)) == "Not connected"


def test_deleting_reads_as_the_service_does_it():
    assert services.deletion("gmail", "item").heading == "Move this message to the trash?"
    assert services.deletion("gmail", "topic").done == "Moved to the trash"
    assert services.deletion("jira", "topic") == services.Deletion(
        "Delete this topic?", "SilentDesk deletes it in Jira.", "Deleted"
    )
