"""Pushover and optional Twilio notification delivery."""

import os

import requests


class TwilioSmsSender:
    def __init__(
        self,
        account_sid=None,
        auth_token=None,
        from_number=None,
        to_number=None,
        timeout=20,
        session=None,
    ):
        self.account_sid = account_sid if account_sid is not None else os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = auth_token if auth_token is not None else os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = from_number if from_number is not None else os.getenv("TWILIO_FROM_NUMBER", "")
        self.to_number = to_number if to_number is not None else os.getenv("TWILIO_TO_NUMBER", "")
        self.timeout = timeout
        self.session = session or requests.Session()

    @property
    def configured(self):
        return all(
            [self.account_sid, self.auth_token, self.from_number, self.to_number]
        )

    def send(self, message):
        result = {
            "channel": "sms",
            "recipient": self.to_number,
            "message": message,
        }
        if not self.configured:
            result.update(
                {
                    "status": "not_configured",
                    "error": "Twilio environment variables are incomplete.",
                }
            )
            return result

        url = "https://api.twilio.com/2010-04-01/Accounts/{}/Messages.json".format(
            self.account_sid
        )
        try:
            response = self.session.post(
                url,
                auth=(self.account_sid, self.auth_token),
                data={
                    "From": self.from_number,
                    "To": self.to_number,
                    "Body": message,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            result.update({"status": "sent", "provider_id": payload.get("sid")})
        except (requests.RequestException, ValueError) as exc:
            result.update({"status": "failed", "error": str(exc)})
        return result


class PushoverSender:
    ENDPOINT = "https://api.pushover.net/1/messages.json"

    def __init__(self, user_key=None, api_token=None, timeout=20, session=None):
        self.user_key = user_key if user_key is not None else os.getenv("PUSHOVER_USER_KEY", "")
        self.api_token = api_token if api_token is not None else os.getenv("PUSHOVER_API_TOKEN", "")
        self.timeout = timeout
        self.session = session or requests.Session()

    @property
    def configured(self):
        return bool(self.user_key and self.api_token)

    def send(self, message):
        message = message[:1024]
        result = {
            "channel": "pushover",
            "recipient": "Pushover user",
            "message": message,
        }
        if not self.configured:
            result.update(
                {
                    "status": "not_configured",
                    "error": "Pushover environment variables are incomplete.",
                }
            )
            return result

        try:
            response = self.session.post(
                self.ENDPOINT,
                data={
                    "token": self.api_token,
                    "user": self.user_key,
                    "message": message,
                    "title": "Campfyr availability",
                    "sound": "gamelan",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            result.update({"status": "sent", "provider_id": payload.get("request")})
        except (requests.RequestException, ValueError) as exc:
            result.update({"status": "failed", "error": str(exc)})
        return result


def build_sender(provider=None):
    selected = (provider or os.getenv("NOTIFICATION_PROVIDER", "pushover")).strip().lower()
    if selected == "pushover":
        return PushoverSender()
    if selected == "twilio":
        return TwilioSmsSender()
    raise ValueError("NOTIFICATION_PROVIDER must be 'pushover' or 'twilio'.")
