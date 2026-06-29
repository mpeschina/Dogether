from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components


_BUILD_DIR = Path(__file__).parent / "frontend" / "build"

_component_func = components.declare_component(
    "push_subscribe",
    path=str(_BUILD_DIR),
)


def push_subscribe(
    *,
    vapid_public_key: str,
    service_worker_url: str = "/app/static/sw.js",
    key: str | None = None,
):
    return _component_func(
        vapid_public_key=vapid_public_key,
        service_worker_url=service_worker_url,
        key=key,
        default=None,
    )
