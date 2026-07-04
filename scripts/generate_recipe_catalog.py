from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def collect_recipe_entries(repo_root: Path | None = None) -> list[dict[str, Any]]:
    base = repo_root or ROOT
    recipe_dirs = [base / "Github", base / "GithubOK"]
    entries: list[dict[str, Any]] = []

    for recipe_dir in recipe_dirs:
        if not recipe_dir.exists():
            continue
        for path in sorted(recipe_dir.rglob("*.html")):
            html_text = path.read_text(encoding="utf-8", errors="ignore")
            title = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
            title_text = re.sub(r"\s+", " ", title.group(1)).strip() if title else path.stem
            entries.append({
                "title": html.unescape(title_text),
                "path": str(path.relative_to(base)).replace('\\', '/'),
                "source": path.name,
            })

    entries.sort(key=lambda item: item["title"].lower())
    return entries


def build_catalog_html(entries: list[dict[str, Any]]) -> str:
    cards = []
    for entry in entries:
        cards.append(
            f"<article class='recipe-card'><h3>{html.escape(entry['title'])}</h3><p>{html.escape(entry['path'])}</p></article>"
        )

    return f"""<!DOCTYPE html>
<html lang=\"es\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>Catálogo de recetas</title>
  <style>
    body {{ font-family: Arial, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }}
    .wrap {{ max-width: 1200px; margin: 0 auto; }}
    h1 {{ margin-bottom: 10px; }}
    .subtitle {{ color: #94a3b8; margin-bottom: 24px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }}
    .recipe-card {{ background: #111827; border: 1px solid #334155; border-radius: 14px; padding: 16px; }}
    .recipe-card h3 {{ margin: 0 0 8px; font-size: 1rem; }}
    .recipe-card p {{ color: #cbd5e1; font-size: 0.9rem; margin: 0; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>Catálogo de recetas</h1>
    <p class=\"subtitle\">Actualizado automáticamente desde el repositorio de GitHub.</p>
    <div class=\"grid\">{''.join(cards)}</div>
  </div>
</body>
</html>
"""


def main() -> None:
    entries = collect_recipe_entries()
    output_path = ROOT / "generated_recipe_catalog.html"
    output_path.write_text(build_catalog_html(entries), encoding="utf-8")
    print(f"Generated {output_path} with {len(entries)} recipes")


if __name__ == "__main__":
    main()
