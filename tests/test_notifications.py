from campfyr.notifications import PushoverSender


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"status": 1, "request": "request-id"}


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


def test_pushover_reports_missing_configuration():
    result = PushoverSender(user_key="", api_token="").send("hello")
    assert result["status"] == "not_configured"


def test_pushover_sends_expected_payload_and_truncates_message():
    session = FakeSession()
    sender = PushoverSender(user_key="user", api_token="token", session=session)
    result = sender.send("x" * 1200)

    assert result["status"] == "sent"
    assert result["provider_id"] == "request-id"
    url, request = session.calls[0]
    assert url == "https://api.pushover.net/1/messages.json"
    assert request["data"]["user"] == "user"
    assert request["data"]["token"] == "token"
    assert len(request["data"]["message"]) == 1024
