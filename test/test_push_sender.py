import sys
import types

from src.push.sender import send_push_to_user


class MemoryPushStorage:
    def __init__(self, records: list[dict]) -> None:
        self.records = records
        self.deleted = []

    def subscriptions_for_user(self, user_id: str) -> list[dict]:
        return [record for record in self.records if record["user_id"] == user_id]

    def delete_subscription(self, endpoint: str) -> None:
        self.deleted.append(endpoint)


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class FakeWebPushException(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.response = FakeResponse(status_code) if status_code else None


def record(endpoint: str) -> dict:
    return {
        "endpoint": endpoint,
        "user_id": "alice",
        "subscription": {"endpoint": endpoint, "keys": {"p256dh": "x", "auth": "y"}},
    }


def install_pywebpush(monkeypatch, webpush):
    module = types.SimpleNamespace(webpush=webpush, WebPushException=FakeWebPushException)
    monkeypatch.setitem(sys.modules, "pywebpush", module)


def test_send_push_to_user_sends_to_all_subscriptions(monkeypatch) -> None:
    calls = []
    install_pywebpush(monkeypatch, lambda **kwargs: calls.append(kwargs))
    storage = MemoryPushStorage([record("one"), record("two")])

    result = send_push_to_user(
        storage,
        "alice",
        "Hello",
        "Body",
        "/friends",
        vapid_private_key="private",
        vapid_subject="mailto:test@example.com",
    )

    assert result == {"sent": 2, "removed": 0, "errors": []}
    assert [call["subscription_info"]["endpoint"] for call in calls] == ["one", "two"]
    assert all(call["vapid_private_key"] == "private" for call in calls)


def test_send_push_to_user_removes_expired_subscriptions(monkeypatch) -> None:
    def webpush(**kwargs):
        raise FakeWebPushException("expired", 410)

    install_pywebpush(monkeypatch, webpush)
    storage = MemoryPushStorage([record("expired")])

    result = send_push_to_user(
        storage,
        "alice",
        "Hello",
        "Body",
        vapid_private_key="private",
        vapid_subject="mailto:test@example.com",
    )

    assert result == {"sent": 0, "removed": 1, "errors": []}
    assert storage.deleted == ["expired"]


def test_send_push_to_user_keeps_subscription_on_other_errors(monkeypatch) -> None:
    def webpush(**kwargs):
        raise FakeWebPushException("server error", 500)

    install_pywebpush(monkeypatch, webpush)
    storage = MemoryPushStorage([record("one")])

    result = send_push_to_user(
        storage,
        "alice",
        "Hello",
        "Body",
        vapid_private_key="private",
        vapid_subject="mailto:test@example.com",
    )

    assert result["sent"] == 0
    assert result["removed"] == 0
    assert result["errors"] == ["server error"]
    assert storage.deleted == []
