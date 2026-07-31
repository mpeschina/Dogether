import pytest

import src.app_notifications as app_notifications


class _FakeStreamlit:
    def __init__(self) -> None:
        self.session_state = {}
        self.toast_messages = []

    def toast(self, body, *, icon=None, duration="short") -> None:
        self.toast_messages.append((body, icon, duration))


def test_startup_notifications_wait_for_viewport_then_deduplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(app_notifications, "st", fake_st)

    assert app_notifications.queue_user_notification(
        "Weekly analysis ready", key="weekly:alice", duration="long"
    )
    assert not app_notifications.queue_user_notification(
        "Weekly analysis ready", key="weekly:alice", duration="long"
    )

    assert app_notifications.flush_startup_notifications(viewport_ready=False) == 0
    assert fake_st.toast_messages == []

    assert app_notifications.flush_startup_notifications(viewport_ready=True) == 1
    assert fake_st.toast_messages == [("Weekly analysis ready", None, "long")]
    assert not app_notifications.queue_user_notification("Weekly analysis ready", key="weekly:alice")


def test_unkeyed_startup_notifications_repeat_and_clearing_key_allows_requeue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(app_notifications, "st", fake_st)

    assert app_notifications.queue_user_notification("Saved")
    assert app_notifications.queue_user_notification("Saved")
    assert app_notifications.flush_startup_notifications(viewport_ready=True) == 2
    assert fake_st.toast_messages == [("Saved", None, "short"), ("Saved", None, "short")]

    assert app_notifications.queue_user_notification("Warning", key="repair")
    assert app_notifications.flush_startup_notifications(viewport_ready=True) == 1
    app_notifications.clear_user_notification("repair")
    assert app_notifications.queue_user_notification("Warning", key="repair")
