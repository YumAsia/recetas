from pathlib import Path

from scripts.generate_recipe_catalog import collect_recipe_entries


def test_collect_recipe_entries_extracts_titles_and_paths(tmp_path: Path) -> None:
    (tmp_path / "Github").mkdir()
    (tmp_path / "Github" / "receta-uno.html").write_text(
        "<html><head><title>Receta Uno</title></head><body>Ingrediente A</body></html>",
        encoding="utf-8",
    )
    (tmp_path / "Github" / "receta-dos.html").write_text(
        "<html><head><title>Receta Dos</title></head><body>Ingrediente B</body></html>",
        encoding="utf-8",
    )

    entries = collect_recipe_entries(tmp_path)

    assert len(entries) == 2
    assert entries[0]["title"] == "Receta Dos" or entries[0]["title"] == "Receta Uno"
    assert all(entry["path"].endswith(".html") for entry in entries)
