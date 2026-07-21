from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components


_BUILD_DIR = Path(__file__).parent / "frontend" / "build"
_component_func = None

if _BUILD_DIR.exists():
    _component_func = components.declare_component(
        "participant_reaction_row",
        path=str(_BUILD_DIR),
    )


def participant_reaction_row(
    *,
    row_id: str,
    name: str,
    name_html: str,
    sparkline_html: str,
    dots_html: str,
    progress_label: str,
    current: int,
    target: int,
    skipped: bool,
    reaction_summary: list[tuple[str, int]],
    reaction_details: list[dict[str, str]],
    standard_emotes: list[str],
    emotes: list[str],
    can_react: bool,
    open_picker: bool,
    key: str,
) -> dict[str, Any] | None:
    if _component_func is None:
        st.error(
            "Participant reaction row component build is missing. "
            "Commit src/reaction_component/frontend/build before deployment."
        )
        return None

    return _component_func(
        row_id=row_id,
        name=name,
        name_html=name_html,
        sparkline_html=sparkline_html,
        dots_html=dots_html,
        progress_label=progress_label,
        current=max(0, int(current)),
        target=max(1, int(target)),
        skipped=bool(skipped),
        reaction_summary=[{"emote": emote, "count": int(count)} for emote, count in reaction_summary],
        reaction_details=[
            {"emote": str(detail.get("emote", "")), "name": str(detail.get("name", ""))}
            for detail in reaction_details
        ],
        standard_emotes=standard_emotes,
        emotes=emotes,
        can_react=bool(can_react),
        open_picker=bool(open_picker),
        key=key,
        default=None,
    )
