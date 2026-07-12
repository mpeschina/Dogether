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


def viewport_info(*, key: str | None = None) -> dict[str, Any] | None:
    if _component_func is None:
        st.error(
            "Viewport info component build is missing. "
            "Commit src/viewport_component/frontend/build or rebuild the component before deployment."
        )
        return None

    return _component_func(
        key=key,
        default=None,
    )
