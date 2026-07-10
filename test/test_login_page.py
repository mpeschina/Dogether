from __future__ import annotations

from typing import Any

from src.pages import login_page


class FakeForm:
    def __enter__(self) -> "FakeForm":
        return self

    def __exit__(self, *args: Any) -> None:
        return None


class FakeStreamlit:
    def __init__(self) -> None:
        self.markdowns: list[tuple[str, bool]] = []
        self.buttons: list[dict[str, Any]] = []
        self.headers: list[str] = []
        self.subheaders: list[str] = []
        self.captions: list[str] = []
        self.login = object()

    def markdown(self, body: str, unsafe_allow_html: bool = False) -> None:
        self.markdowns.append((body, unsafe_allow_html))

    def header(self, body: str) -> None:
        self.headers.append(body)

    def button(self, label: str, **kwargs: Any) -> bool:
        self.buttons.append({"label": label, **kwargs})
        return False

    def divider(self) -> None:
        pass

    def subheader(self, body: str) -> None:
        self.subheaders.append(body)

    def form(self, key: str) -> FakeForm:
        return FakeForm()

    def text_input(self, label: str) -> str:
        return ""

    def form_submit_button(self, label: str) -> bool:
        return False

    def caption(self, body: str) -> None:
        self.captions.append(body)

    def error(self, body: str) -> None:
        raise AssertionError(body)


class EmptyPersistence:
    def list_users(self) -> list[dict[str, Any]]:
        return []


def test_login_screen_hides_sidebar_when_debug_login_is_enabled(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(login_page, "st", fake_st)

    login_page.login_screen(EmptyPersistence(), debug_enabled=True)

    rendered_css = "\n".join(body for body, _ in fake_st.markdowns)
    assert '[data-testid="stSidebar"]' in rendered_css
    assert '[data-testid="collapsedControl"]' in rendered_css
    assert "display: none" in rendered_css
    assert all(unsafe for _, unsafe in fake_st.markdowns)
    assert "Debug login" in fake_st.subheaders[0]
    assert {button["label"] for button in fake_st.buttons} == {"Log in with Google"}


def test_login_screen_centers_only_normal_google_login(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(login_page, "st", fake_st)

    login_page.login_screen(debug_enabled=False)

    rendered_css = "\n".join(body for body, _ in fake_st.markdowns)
    assert '[data-testid="stSidebar"]' in rendered_css
    assert ".block-container" in rendered_css
    assert fake_st.subheaders == []
    assert fake_st.buttons == [
        {
            "label": "Log in with Google",
            "on_click": fake_st.login,
            "use_container_width": True,
        }
    ]
