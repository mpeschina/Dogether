from __future__ import annotations

from pathlib import Path
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


def viewport_info(
    *,
    key: str | None = None,
    pixel_threshold: int = 10,
    debounce_ms: int = 300,
) -> dict[str, Any] | None:
    """Return browser viewport information from a Streamlit custom component.

    Args:
        key: Stable Streamlit component key. Use a unique key for each place the
            component is rendered, for example ``viewport_info(key="main_viewport")``.
        pixel_threshold: Minimum width or height delta in CSS pixels before the
            browser reports a resize-triggered update to Python. Orientation
            changes are always reported. Defaults to ``10``.
        debounce_ms: Delay in milliseconds before reporting resize/orientation
            changes. Defaults to ``300``.

    Example:
        ``viewport_info(key="main_viewport", pixel_threshold=20, debounce_ms=500)``
        reports only after width/height changes larger than 20 pixels, or after
        orientation changes, with a 500 ms debounce.
    """
    if _component_func is None:
        st.error(
            "Viewport info component build is missing. "
            "Commit src/viewport_component/frontend/build or rebuild the component before deployment."
        )
        return None

    return _component_func(
        pixel_threshold=max(0, int(pixel_threshold)),
        debounce_ms=max(0, int(debounce_ms)),
        key=key,
        default=None,
    )
