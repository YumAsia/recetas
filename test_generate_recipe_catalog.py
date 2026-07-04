from pathlib import Path

from scripts.generate_recipe_catalog import (
    build_catalog_html,
    collect_recipe_entries,
    extract_social_embed_url,
    write_recipe_viewer_page,
)


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


def test_collect_recipe_entries_infers_ingredients_and_html_contains_seo(tmp_path: Path) -> None:
    (tmp_path / "Github").mkdir()
    (tmp_path / "Github" / "receta-setas.html").write_text(
        "<html><head><title>Paella de setas y pollo</title><meta property='og:image' content='https://example.com/og.jpg'></head><body><div class='recipe-img'><img src='https://example.com/recipe.jpg' /></div><p>Pollo y setas</p></body></html>",
        encoding="utf-8",
    )

    entries = collect_recipe_entries(tmp_path)
    html_output = build_catalog_html(entries)

    assert entries[0]["ingredients"][0] == "Setas"
    assert entries[0]["ingredients"][1] == "Pollo"
    assert entries[0]["image"] == "https://example.com/og.jpg"
    assert 'meta name="description"' in html_output
    assert 'application/ld+json' in html_output
    assert 'index,follow' in html_output
    assert 'recipe.path' not in html_output
    assert 'class="card-image"' in html_output


def test_build_catalog_html_uses_clean_recipe_links(tmp_path: Path) -> None:
    (tmp_path / "Github").mkdir()
    (tmp_path / "Github" / "receta-prueba.html").write_text(
        "<html><head><title>Receta prueba</title></head><body>Prueba</body></html>",
        encoding="utf-8",
    )

    entries = collect_recipe_entries(tmp_path)
    html_output = build_catalog_html(entries)

    assert 'recipe_viewer.html?id=' in html_output
    assert 'recipe_links/' not in html_output
    assert 'Github/receta-prueba.html' not in html_output


def test_collect_recipe_entries_prefers_recipe_photo_over_generic_images(tmp_path: Path) -> None:
    (tmp_path / "Github").mkdir()
    (tmp_path / "Github" / "receta-queso.html").write_text(
        "<html><head><title>Tarta de queso japonesa</title></head><body><img src='https://example.com/logo.png' alt='Logo' /><div class='recipe-img'><img src='https://example.com/recipe-photo.jpg' alt='Tarta de queso japonesa' /></div><p>Receta de tarta de queso japonesa</p></body></html>",
        encoding="utf-8",
    )

    entries = collect_recipe_entries(tmp_path)

    assert entries[0]["image"] == "https://example.com/recipe-photo.jpg"


def test_extract_social_embed_url_finds_instagram_and_tiktok_links() -> None:
    html_text = '<html><body><blockquote class="instagram-media" data-instgrm-permalink="https://www.instagram.com/p/abc123/"></blockquote><a href="https://www.tiktok.com/@user/video/123">TikTok</a></body></html>'

    assert extract_social_embed_url(html_text) == ("instagram", "abc123")


def test_write_recipe_viewer_page_uses_auto_slug_without_repo_path(tmp_path: Path) -> None:
    page = write_recipe_viewer_page(
        title="Tortilla de patatas",
        source_path="Github/recetas/tortilla.html",
        output_dir=tmp_path,
    )

    assert page.name.endswith(".html")
    assert "Github/recetas/tortilla.html" not in page.read_text(encoding="utf-8")
    assert "Visor de recetas" in page.read_text(encoding="utf-8")
