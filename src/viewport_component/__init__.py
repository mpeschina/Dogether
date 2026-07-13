from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Any

import streamlit as st
import streamlit.components.v1 as components


_BUILD_DIR = Path(__file__).parent / "frontend" / "build"
_component_func = None

if _BUILD_DIR.exists():
    _component_func = components.declare_component(
        "viewport_info",
        path=str(_BUILD_DIR),
    )


DEFAULT_VIEWPORT_COMPONENT_KEY = "viewport_info:custom_component"
DEFAULT_VIEWPORT_CACHE_KEY = f"{DEFAULT_VIEWPORT_COMPONENT_KEY}:cache"
DEFAULT_VIEWPORT_WAIT_START_KEY = f"{DEFAULT_VIEWPORT_COMPONENT_KEY}:wait_started_at"
DEFAULT_RESIZE_PIXEL_THRESHOLD = 20
DEFAULT_RESIZE_DEBOUNCE_MS = 500
DEFAULT_LOADING_MESSAGE = None # could be "Loading layout..."
DEFAULT_FALLBACK_TIMEOUT_SECONDS = 5
DEBUG_PRINTS = True
DEBUG_COUNT = 0


DEFAULT_FALLBACK_VIEWPORT: dict[str, Any] = {
    "width": 1920,
    "height": 1080,
    "iframeWidth": 1920,
    "iframeHeight": 1080,
    "viewportSource": "fallback_timeout",
    "screenWidth": 1920,
    "screenHeight": 1080,
    "devicePixelRatio": 1,
    "aspectRatio": 16 / 9,
    "orientation": "landscape",
    "renderPath": "widescreen",
    "devicePlatform": "pc",
}


def _fallback_viewport(fallback_viewport: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(fallback_viewport or DEFAULT_FALLBACK_VIEWPORT)


def _fallback_timeout_reached(
    *,
    wait_started_at: float,
    fallback_timeout_seconds: float | None,
    now: float,
) -> bool:
    if fallback_timeout_seconds is None:
        return False
    return now - wait_started_at >= max(0.0, float(fallback_timeout_seconds))


def viewport_info(
    *,
    pixel_threshold: int = DEFAULT_RESIZE_PIXEL_THRESHOLD,
    debounce_ms: int = DEFAULT_RESIZE_DEBOUNCE_MS,
    cache: bool = True,
    require_ready: bool = True,
    loading_message: str | None = DEFAULT_LOADING_MESSAGE,
    fallback_timeout_seconds: float | None = DEFAULT_FALLBACK_TIMEOUT_SECONDS,
    fallback_viewport: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return browser viewport information from a Streamlit custom component.

    Streamlit custom components report browser values after the Python page has
    already rendered once, so the first call usually returns ``None`` and then
    triggers a rerun with the real viewport. This helper caches the last valid
    payload in ``st.session_state`` by default so pages do not need to manage
    viewport session keys themselves. The defaults are tuned for normal
    viewport-dependent pages: a configured component key, 20 px resize threshold,
    500 ms resize debounce, ready-gating, a lightweight loading message, and a
    5 second desktop fallback timeout.

    Pages that need exact first-layout decisions should call this function once,
    before expensive data loading. If no cached
    payload exists yet, the helper renders ``loading_message`` when provided and
    stops the current Streamlit run. When ``fallback_timeout_seconds`` is set,
    the helper returns a desktop fallback viewport instead of stopping forever
    after that timeout. After the browser reports, the page reruns and receives
    the real dict. Pages that can tolerate approximate layout, or diagnostic
    pages that should not stop the whole page, can pass ``require_ready=False``
    and handle a possible ``None``.

    The default resize options intentionally avoid chatty reruns. Orientation
    changes and device-platform changes are still reported even when the pixel
    delta is below the threshold.

    Args:
        The Streamlit component key is intentionally not a function parameter.
        All pages use ``DEFAULT_VIEWPORT_COMPONENT_KEY`` so viewport state is
        configured in one place.
        pixel_threshold: Minimum width or height delta in CSS pixels before the
            browser reports a resize-triggered update to Python. Orientation
            changes are always reported. Defaults to ``20``.
        debounce_ms: Delay in milliseconds before reporting resize/orientation
            changes. Defaults to ``500``.
        cache: Store and return the last valid payload from ``st.session_state``
            under ``DEFAULT_VIEWPORT_CACHE_KEY``. Defaults to ``True``.
        require_ready: When ``True``, stop the current Streamlit run until a
            viewport payload is available. This keeps exact viewport-dependent
            pages to a single early call and avoids expensive first-pass work.
            Defaults to ``True``.
        loading_message: Optional message shown before ``st.stop()`` when
            ``require_ready`` is ``True`` and no cached payload exists. Defaults
            to ``DEFAULT_LOADING_MESSAGE``.
        fallback_timeout_seconds: Optional maximum seconds to wait for the
            browser payload before returning a fallback viewport. Defaults to
            ``5``.
        fallback_viewport: Optional fallback payload. When omitted, the fallback
            is a PC, widescreen, 16:9 viewport.

    Example:
        ``viewport_info()`` is the recommended call for a normal page. It
        reports only after width/height changes larger than 20 pixels, or after
        orientation changes, with a 500 ms debounce. Until the first report, it
        displays the loading message and stops the run. If no browser value
        arrives within 5 seconds, it returns a default PC 16:9 viewport.
    """
    if DEBUG_PRINTS: 
        global DEBUG_COUNT
        DEBUG_COUNT += 1
        print(f"viewport_info called ({DEBUG_COUNT})")
    cached_viewport = st.session_state.get(DEFAULT_VIEWPORT_CACHE_KEY, None) if cache else None

    if _component_func is None:
        st.error(
            "Viewport info component build is missing. "
            "Commit src/viewport_component/frontend/build or rebuild the component before deployment."
        )
        return None

    # returns from the Browser what the values are. Only after one re-run.
    viewport = _component_func(
        pixel_threshold=max(0, int(pixel_threshold)),
        debounce_ms=max(0, int(debounce_ms)),
        cached_viewport=cached_viewport if isinstance(cached_viewport, dict) else None,
        key=DEFAULT_VIEWPORT_COMPONENT_KEY,
        default=cached_viewport if isinstance(cached_viewport, dict) else None,
    )
    if DEBUG_PRINTS: 
        print(f"_component_func: {str(viewport)[:20]}")

    # cache the value into the session state
    wait_start_key = DEFAULT_VIEWPORT_WAIT_START_KEY
    if isinstance(viewport, dict):
        if cache:
            st.session_state[DEFAULT_VIEWPORT_CACHE_KEY] = viewport
        st.session_state.pop(wait_start_key, None)
        if DEBUG_PRINTS: 
            print(f"cache stored: {str(viewport)[:20]}")
        return viewport

    # logic to ensure proper waiting time and fallback timeout
    if require_ready:
        now = monotonic()
        wait_started_at = st.session_state.setdefault(wait_start_key, now)
        if _fallback_timeout_reached(
            wait_started_at=float(wait_started_at),
            fallback_timeout_seconds=fallback_timeout_seconds,
            now=now,
        ):
            viewport = _fallback_viewport(fallback_viewport)
            if cache:
                st.session_state[DEFAULT_VIEWPORT_CACHE_KEY] = viewport
            return viewport

        if loading_message:
            st.info(loading_message)

        if DEBUG_PRINTS: 
            print(f"call to st.stop")
        st.stop()

    return None
