from pathlib import Path


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


def test_debug_page_renders_viewport_diagnostics() -> None:
    content = Path("src/pages/debug_page.py").read_text(encoding="utf-8")

    assert "from src.viewport_component import viewport_info" in content
    assert "def render_viewport_diagnostics()" in content
    assert "render_viewport_diagnostics()" in content
    assert "viewport_info(key=\"debug_viewport_info\")" in content
