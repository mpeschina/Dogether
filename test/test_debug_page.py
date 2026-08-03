from __future__ import annotations

from src.pages import debug_page


class FakeStreamlit:
    def __init__(self) -> None:
        self.session_state: dict[str, object] = {}
        self.next_click: str | None = None
        self.confirmation = ""
        self.errors: list[str] = []
        self.successes: list[str] = []

    def divider(self) -> None:
        pass

    def subheader(self, _body: str) -> None:
        pass

    def warning(self, _body: str) -> None:
        pass

    def write(self, _body: str) -> None:
        pass

    def text_input(self, _label: str, *, key: str) -> str:
        self.session_state.setdefault(key, self.confirmation)
        return str(self.session_state[key])

    def error(self, body: str) -> None:
        self.errors.append(body)

    def success(self, body: str) -> None:
        self.successes.append(body)

    def columns(self, _count: int):
        return self, self

    def button(self, label: str, *, on_click=None, **_kwargs) -> bool:
        if label != self.next_click:
            return False
        if on_click:
            on_click()
        return True


class GuardStreamlit:
    def __init__(self) -> None:
        self.titles: list[str] = []

    def title(self, body: str) -> None:
        self.titles.append(body)


def test_render_debug_requires_profile_debug_info(monkeypatch) -> None:
    fake_st = GuardStreamlit()
    monkeypatch.setattr(debug_page, "st", fake_st)

    debug_page.render_debug(object(), current_user={"debug_info": False}, user_id="alice")
    assert fake_st.titles == []


class RecordingPersistence:
    def __init__(self) -> None:
        self.purged: list[tuple[str, object]] = []

    def purge_account(self, user_id: str, now=None) -> dict:
        self.purged.append((user_id, now))
        return {"user_id": user_id}


class RecordingPushStorage:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_subscriptions_for_user(self, user_id: str) -> None:
        self.deleted.append(user_id)


def test_account_purge_confirmation_uses_logged_in_user_and_clears_session(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.session_state.update({"debug_user_id": "alice", "assistant.destination": "assistant"})
    persistence = RecordingPersistence()
    push_storage = RecordingPushStorage()
    monkeypatch.setattr(debug_page, "st", fake_st)

    fake_st.next_click = "Full purge account"
    debug_page.render_account_purge(persistence, push_storage, "alice", now="now")
    assert fake_st.session_state["debug_account_purge_pending"] is True

    fake_st.confirmation = "clear account"
    fake_st.next_click = "Submit purge"
    debug_page.render_account_purge(persistence, push_storage, "alice", now="now")

    assert persistence.purged == [("alice", "now")]
    assert push_storage.deleted == ["alice"]
    assert fake_st.session_state == {
        "debug_user_id": "alice",
        "debug_account_purge_flash": "Account reset to standard values.",
    }


def test_account_purge_requires_exact_confirmation_and_can_be_cancelled(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    persistence = RecordingPersistence()
    push_storage = RecordingPushStorage()
    monkeypatch.setattr(debug_page, "st", fake_st)

    fake_st.next_click = "Full purge account"
    debug_page.render_account_purge(persistence, push_storage, "alice")
    fake_st.confirmation = "clear Account"
    fake_st.next_click = "Submit purge"
    debug_page.render_account_purge(persistence, push_storage, "alice")

    assert persistence.purged == []
    assert "debug_account_purge_error" in fake_st.session_state
    fake_st.next_click = "Cancel"
    debug_page.render_account_purge(persistence, push_storage, "alice")
    assert "debug_account_purge_pending" not in fake_st.session_state
