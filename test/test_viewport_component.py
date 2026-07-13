from pathlib import Path

import pytest

import src.viewport_component as viewport_component


def test_viewport_component_build_exists_with_streamlit_hooks() -> None:
    component_html = Path("src/viewport_component/frontend/build/index.html")

    assert component_html.exists()

    content = component_html.read_text(encoding="utf-8")
    assert "streamlit:componentReady" in content
    assert "streamlit:render" in content
    assert "streamlit:setComponentValue" in content
    assert "streamlit:setFrameHeight" in content
    assert "resize" in content
    assert "orientationchange" in content
    assert "parent_window" in content
    assert "iframeHeight" in content
    assert "mobile_portrait" in content
    assert "widescreen" in content
    assert "function detectedDevicePlatform()" in content
    assert "function devicePlatform()" in content
    assert "devicePlatform: devicePlatform()" in content
    assert 'return "ios"' in content
    assert 'return "android"' in content
    assert 'return "pc"' in content
    assert 'return "all"' in content
    assert "DEFAULT_RESIZE_PIXEL_THRESHOLD = 10" in content
    assert "DEFAULT_RESIZE_DEBOUNCE_MS = 300" in content
    assert "widthDelta > threshold" in content
    assert "heightDelta > threshold" in content
    assert "payload.orientation !== lastReportedPayload.orientation" in content
    assert "payload.devicePlatform !== lastReportedPayload.devicePlatform" in content
    assert "cached_viewport" in content
    assert "function seedLastReportedPayload()" in content
    assert "lastReportedPayload = cached" in content
    assert "hasRendered = true" in content
    assert "if (!hasRendered)" in content
    assert "sendMessage(COMPONENT_READY, { apiVersion: 1 });" in content
    assert "sendMessage(COMPONENT_READY, { apiVersion: 1 });\n      reportViewport();" not in content


def test_debug_page_renders_viewport_diagnostics() -> None:
    content = Path("src/pages/debug_page.py").read_text(encoding="utf-8")

    assert "from src.viewport_component import viewport_info" in content
    assert "def render_viewport_diagnostics()" in content
    assert "render_viewport_diagnostics()" in content
    assert "viewport_info(require_ready=False)" in content
    assert "debug_viewport_info" not in content


def test_viewport_component_wrapper_exposes_resize_options() -> None:
    content = Path("src/viewport_component/__init__.py").read_text(encoding="utf-8")

    assert "DEFAULT_VIEWPORT_COMPONENT_KEY = \"viewport_info:custom_component\"" in content
    assert 'DEFAULT_VIEWPORT_CACHE_KEY = f"{DEFAULT_VIEWPORT_COMPONENT_KEY}:cache"' in content
    assert 'DEFAULT_VIEWPORT_WAIT_START_KEY = f"{DEFAULT_VIEWPORT_COMPONENT_KEY}:wait_started_at"' in content
    assert "DEFAULT_RESIZE_PIXEL_THRESHOLD = 20" in content
    assert "DEFAULT_RESIZE_DEBOUNCE_MS = 500" in content
    assert "DEFAULT_LOADING_MESSAGE" in content
    assert "DEFAULT_FALLBACK_TIMEOUT_SECONDS = 5" in content
    assert "key: str | None = DEFAULT_VIEWPORT_COMPONENT_KEY" not in content
    assert "key=DEFAULT_VIEWPORT_COMPONENT_KEY" in content
    assert "pixel_threshold: int = DEFAULT_RESIZE_PIXEL_THRESHOLD" in content
    assert "debounce_ms: int = DEFAULT_RESIZE_DEBOUNCE_MS" in content
    assert "cache: bool = True" in content
    assert "require_ready: bool = True" in content
    assert "loading_message: str | None = DEFAULT_LOADING_MESSAGE" in content
    assert "fallback_timeout_seconds: float | None = DEFAULT_FALLBACK_TIMEOUT_SECONDS" in content
    assert "fallback_viewport: dict[str, Any] | None = None" in content
    assert "pixel_threshold=max(0, int(pixel_threshold))" in content
    assert "debounce_ms=max(0, int(debounce_ms))" in content
    assert "st.session_state[DEFAULT_VIEWPORT_CACHE_KEY] = viewport" in content
    assert "st.session_state[DEFAULT_VIEWPORT_COMPONENT_KEY] = viewport" not in content
    assert "st.stop()" in content
    assert "DEFAULT_FALLBACK_VIEWPORT" in content
    assert "_fallback_timeout_reached" in content
    assert "first call usually returns ``None``" in content
    assert "session keys themselves" in content
    assert "single early call" in content


class _StopCalled(Exception):
    pass


class _FakeStreamlit:
    def __init__(self) -> None:
        self.session_state = {}
        self.info_messages = []

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def stop(self) -> None:
        raise _StopCalled


def test_default_fallback_viewport_is_pc_widescreen() -> None:
    fallback = viewport_component._fallback_viewport()

    assert fallback["width"] == 1920
    assert fallback["height"] == 1080
    assert fallback["aspectRatio"] == 16 / 9
    assert fallback["orientation"] == "landscape"
    assert fallback["renderPath"] == "widescreen"
    assert fallback["devicePlatform"] == "pc"
    assert fallback["viewportSource"] == "fallback_timeout"


def test_fallback_timeout_reached_checks_elapsed_time() -> None:
    assert viewport_component._fallback_timeout_reached(
        wait_started_at=10.0,
        fallback_timeout_seconds=5,
        now=14.9,
    ) is False
    assert viewport_component._fallback_timeout_reached(
        wait_started_at=10.0,
        fallback_timeout_seconds=5,
        now=15.0,
    ) is True
    assert viewport_component._fallback_timeout_reached(
        wait_started_at=10.0,
        fallback_timeout_seconds=None,
        now=99.0,
    ) is False


def test_viewport_info_uses_default_component_options(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = _FakeStreamlit()
    component_calls = []

    def fake_component(**kwargs):
        component_calls.append(kwargs)
        return {"renderPath": "widescreen"}

    monkeypatch.setattr(viewport_component, "st", fake_st)
    monkeypatch.setattr(viewport_component, "_component_func", fake_component)

    viewport = viewport_component.viewport_info()

    assert viewport == {"renderPath": "widescreen"}
    assert component_calls == [
        {
            "pixel_threshold": 20,
            "debounce_ms": 500,
            "cached_viewport": None,
            "key": "viewport_info:custom_component",
            "default": None,
        }
    ]
    assert fake_st.session_state["viewport_info:custom_component:cache"] == viewport
    assert "viewport_info:custom_component" not in fake_st.session_state


def test_viewport_info_renders_component_with_cached_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached_viewport = {"renderPath": "widescreen", "width": 1920}
    fake_st = _FakeStreamlit()
    fake_st.session_state["viewport_info:custom_component:cache"] = cached_viewport
    component_calls = []

    def fake_component(**kwargs):
        component_calls.append(kwargs)
        return kwargs["default"]

    monkeypatch.setattr(viewport_component, "st", fake_st)
    monkeypatch.setattr(viewport_component, "_component_func", fake_component)

    viewport = viewport_component.viewport_info()

    assert viewport == cached_viewport
    assert component_calls == [
        {
            "pixel_threshold": 20,
            "debounce_ms": 500,
            "cached_viewport": cached_viewport,
            "key": "viewport_info:custom_component",
            "default": cached_viewport,
        }
    ]


def test_viewport_info_stops_before_fallback_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(viewport_component, "st", fake_st)
    monkeypatch.setattr(viewport_component, "_component_func", lambda **kwargs: None)
    monkeypatch.setattr(viewport_component, "monotonic", lambda: 100.0)

    with pytest.raises(_StopCalled):
        viewport_component.viewport_info(
            require_ready=True,
            loading_message="Loading layout...",
            fallback_timeout_seconds=5,
        )

    assert fake_st.info_messages == ["Loading layout..."]
    assert fake_st.session_state["viewport_info:custom_component:wait_started_at"] == 100.0
    assert "viewport_info:custom_component:cache" not in fake_st.session_state


def test_viewport_info_returns_and_caches_fallback_after_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state["viewport_info:custom_component:wait_started_at"] = 100.0
    monkeypatch.setattr(viewport_component, "st", fake_st)
    monkeypatch.setattr(viewport_component, "_component_func", lambda **kwargs: None)
    monkeypatch.setattr(viewport_component, "monotonic", lambda: 105.0)

    viewport = viewport_component.viewport_info(
        require_ready=True,
        loading_message="Loading layout...",
        fallback_timeout_seconds=5,
    )

    assert viewport is not None
    assert viewport["viewportSource"] == "fallback_timeout"
    assert viewport["devicePlatform"] == "pc"
    assert fake_st.session_state["viewport_info:custom_component:cache"] == viewport
    assert "viewport_info:custom_component" not in fake_st.session_state
    assert fake_st.info_messages == []


def test_viewport_info_real_payload_overwrites_fallback_and_resets_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state["viewport_info:custom_component:cache"] = viewport_component._fallback_viewport()
    fake_st.session_state["viewport_info:custom_component:wait_started_at"] = 100.0
    real_viewport = {"width": 390, "height": 844, "renderPath": "mobile_portrait"}
    monkeypatch.setattr(viewport_component, "st", fake_st)
    monkeypatch.setattr(viewport_component, "_component_func", lambda **kwargs: real_viewport)

    viewport = viewport_component.viewport_info(require_ready=True)

    assert viewport == real_viewport
    assert fake_st.session_state["viewport_info:custom_component:cache"] == real_viewport
    assert "viewport_info:custom_component:wait_started_at" not in fake_st.session_state
