from pathlib import Path


def test_json_persistence_is_not_referenced_by_app_business_logic() -> None:
    backend_files = {"src/db/persistence.py", "src/db/json_persistence.py"}
    production_files = [path for path in Path("src").rglob("*.py") if path.as_posix() not in backend_files]

    offenders = [path.as_posix() for path in production_files if "JsonPersistence" in path.read_text(encoding="utf-8")]

    assert offenders == []


def test_streamlit_entrypoint_uses_persistence_factory_not_json_backend() -> None:
    entrypoint = Path("streamlit_app.py").read_text(encoding="utf-8")

    assert "JsonPersistence" not in entrypoint
    assert "get_persistence" in entrypoint
