from __future__ import annotations

import base64
import html
import json
import re
from pathlib import Path
from typing import Any
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parent.parent
INGREDIENT_HINTS = [
    "pollo",
    "carne",
    "pescado",
    "gamba",
    "arroz",
    "pasta",
    "lentejas",
    "garbanzos",
    "verdura",
    "queso",
    "chocolate",
    "fruta",
    "huevo",
    "tofu",
    "patata",
    "tomate",
    "curry",
    "setas",
    "sopa",
    "ensalada",
    "tortilla",
    "bizcocho",
    "bacalao",
    "salmón",
    "cerdo",
    "atún",
    "calamares",
    "alubias",
    "espinacas",
    "cebolla",
    "ajo",
    "pimiento",
    "zanahoria",
    "almeja",
    "merluza",
    "cordero",
    "conejo",
    "jamón",
    "paella",
]


def decode_unicode_escapes(text: str) -> str:
    if not text:
        return ""
    try:
        text = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), text)
    except Exception:
        pass
    return html.unescape(text)


def normalize_recipe_title(title: str) -> str:
    t = title
    for word in ["· sakuraymas", "- sakuraymas", "sakuraymas", "ofuscado", "widget", "revisión", "revision", "final"]:
        t = re.sub(re.escape(word), "", t, flags=re.IGNORECASE)
    t = re.sub(r'^\d+[\s\-_.]*', '', t)
    t = re.sub(r'\s+', ' ', t).strip().lower()
    return t


def collect_recipe_entries(repo_root: Path | None = None) -> list[dict[str, Any]]:
    base = repo_root or ROOT
    recipe_dirs = [base / "GithubOK", base / "Github"]
    entries: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    seen_titles: set[str] = set()

    for recipe_dir in recipe_dirs:
        if not recipe_dir.exists():
            continue
        for path in sorted(recipe_dir.rglob("*.html"), reverse=True):
            if path.name.lower() in seen_paths:
                continue
            html_text = path.read_text(encoding="utf-8", errors="ignore")
            title = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
            title_text = re.sub(r"\s+", " ", title.group(1)).strip() if title else path.stem
            decoded_title = decode_unicode_escapes(title_text)
            norm_title = normalize_recipe_title(decoded_title)
            if norm_title in seen_titles:
                continue

            seen_paths.add(path.name.lower())
            seen_titles.add(norm_title)

            entry = {
                "title": decoded_title,
                "path": path.name,
                "source": path.name,
                "html_text": html_text,
            }
            entry["ingredients"] = infer_recipe_ingredients(entry)
            entry["ingredient"] = entry["ingredients"][0]
            entry["image"] = infer_recipe_image(html_text)
            entries.append(entry)

    entries.sort(key=lambda item: item["title"].lower())
    return entries


def infer_recipe_ingredients(entry: dict[str, Any]) -> list[str]:
    text_parts = [entry["title"], entry["source"]]
    if entry.get("html_text"):
        text_parts.append(re.sub(r"<[^>]+>", " ", entry["html_text"]))
    combined_text = " ".join(text_parts).lower()
    normalized_text = re.sub(r"[^a-záéíóúñüç0-9]+", " ", combined_text).strip()

    ranked_matches: list[tuple[int, str]] = []
    for hint in INGREDIENT_HINTS:
        if hint in normalized_text:
            if hint in {"paella", "sopa", "tortilla", "ensalada", "bizcocho"}:
                continue
            position = normalized_text.find(hint)
            ranked_matches.append((position, hint))

    if not ranked_matches:
        return ["General"]

    ranked_matches.sort(key=lambda item: item[0])
    unique_matches: list[str] = []
    for _, hint in ranked_matches:
        if hint not in unique_matches:
            unique_matches.append(hint)

    return [hint.capitalize() for hint in unique_matches[:4]]


def extract_social_embed_url(html_text: str) -> tuple[str, str] | None:
    instagram_match = re.search(r'https://www\.instagram\.com/(?:p|reel|tv)/([^/?"\']+)', html_text, re.IGNORECASE)
    if instagram_match:
        shortcode = instagram_match.group(1)
        return "instagram", shortcode

    tiktok_match = re.search(r'https://www\.tiktok\.com/[^\s"\']+', html_text, re.IGNORECASE)
    if tiktok_match:
        return "tiktok", tiktok_match.group(0)

    return None


def fetch_social_media_preview(platform: str, identifier: str) -> str | None:
    try:
        if platform == "instagram":
            url = f"https://www.instagram.com/p/{identifier}/?__a=1"
            with request.urlopen(url, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
            media = payload.get("items", [{}])[0].get("image_versions2", {}).get("candidates", [{}])[0].get("url")
            return media or None
        if platform == "tiktok":
            url = f"https://www.tiktok.com/oembed?url={parse.quote(identifier, safe='')}"
            with request.urlopen(url, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload.get("thumbnail_url") or None
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, UnicodeDecodeError, IndexError):
        return None


def infer_recipe_image(html_text: str) -> str | None:
    social_embed = extract_social_embed_url(html_text)
    if social_embed:
        preview = fetch_social_media_preview(*social_embed)
        if preview:
            return preview

    og_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.IGNORECASE)
    if og_match:
        src = og_match.group(1).strip()
        if src:
            return src

    recipe_img_match = re.search(r'<div[^>]*class=["\'][^"\']*recipe-img[^"\']*["\'][^>]*>\s*<img[^>]+src=["\']([^"\']+)["\']', html_text, re.IGNORECASE | re.DOTALL)
    if recipe_img_match:
        src = recipe_img_match.group(1).strip()
        if src:
            return src

    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html_text, re.IGNORECASE)
    if img_match:
        src = img_match.group(1).strip()
        if src.startswith(("http://", "https://", "data:")):
            return src

    return None


def encode_recipe_path(path: str) -> str:
    return base64.urlsafe_b64encode(path.encode("utf-8")).decode("ascii").rstrip("=")


def decode_recipe_path(token: str) -> str | None:
    try:
        padding = "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(token + padding).decode("utf-8")
        return decoded or None
    except (ValueError, UnicodeDecodeError):
        return None


def build_recipe_viewer_link(entry: dict[str, Any]) -> str:
    return entry["source"]


def build_catalog_html(entries: list[dict[str, Any]]) -> str:
    recipes = []
    for entry in entries:
        relative_path = entry["path"].replace("\\", "/")
        recipes.append(
            {
                "title": entry["title"],
                "ingredient": entry["ingredient"],
                "ingredients": entry.get("ingredients", [entry["ingredient"]]),
                "image": entry.get("image"),
                "link": build_recipe_viewer_link(entry),
            }
        )
    recipes_json = json.dumps(recipes, ensure_ascii=False)
    ingredient_keywords = ", ".join(
        sorted({item["ingredient"] for item in recipes if item["ingredient"] != "General"})[:8]
    )
    seo_title = "Catálogo de recetas | Recetas fáciles, rápidas y originales"
    seo_description = (
        f"Descubre {len(recipes)} recetas variadas organizadas por ingredientes y categorías, con búsquedas rápidas y contenido pensado para Google."
    )
    seo_keywords = ingredient_keywords or "recetas, cocina, blog de recetas"
    schema_json = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": seo_title,
            "description": seo_description,
            "numberOfItems": len(recipes),
            "keywords": seo_keywords,
        },
        ensure_ascii=False,
    )

    template = """<!DOCTYPE html>
<html lang=\"es\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>__SEO_TITLE__</title>
  <meta name=\"description\" content=\"__SEO_DESCRIPTION__\" />
  <meta name=\"keywords\" content=\"__SEO_KEYWORDS__\" />
  <meta name=\"robots\" content=\"index,follow\" />
  <meta property=\"og:title\" content=\"__SEO_TITLE__\" />
  <meta property=\"og:description\" content=\"__SEO_DESCRIPTION__\" />
  <meta property=\"og:type\" content=\"website\" />
  <meta property=\"og:site_name\" content=\"Catálogo de recetas\" />
  <link rel=\"canonical\" href=\"https://example.com/recetas\" />
  <script type=\"application/ld+json\">__SCHEMA_JSON__</script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@700;800&display=swap');
    :root {
      --bg: #060b12;
      --panel: rgba(17, 24, 39, 0.95);
      --text: #f8fafc;
      --muted: #9aa8b8;
      --accent: #ff7a18;
      --accent-2: #2dd4bf;
      --border: rgba(255,255,255,0.10);
      --shadow: 0 16px 45px rgba(0,0,0,0.28);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: 'Inter', 'Segoe UI', Roboto, Arial, sans-serif;
      color: var(--text);
      background: radial-gradient(circle at top left, rgba(45,212,191,0.18), transparent 24%), radial-gradient(circle at top right, rgba(255,122,24,0.16), transparent 28%), linear-gradient(135deg, #060b12, #0b1420 70%, #111827);
      min-height: 100vh;
    }
    .wrap { max-width: 1250px; margin: 0 auto; padding: 26px; }
    .hero {
      border: 1px solid var(--border);
      border-radius: 28px;
      padding: 28px;
      background: linear-gradient(135deg, rgba(255,122,24,0.18), rgba(45,212,191,0.13));
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }
    .eyebrow {
      display: inline-block;
      padding: 7px 12px;
      border-radius: 999px;
      background: rgba(255,255,255,0.10);
      color: #fff;
      font-size: 0.82rem;
      margin-bottom: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    h1 {
      font-family: 'Playfair Display', Georgia, serif;
      font-size: clamp(1.8rem, 3.1vw, 2.7rem);
      margin: 0 0 10px;
      line-height: 1.1;
    }
    .hero p { color: var(--muted); max-width: 860px; line-height: 1.6; font-size: 1rem; }
    .toolbar { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 12px; margin-top: 18px; }
    input, select { width: 100%; padding: 13px 14px; border-radius: 14px; border: 1px solid var(--border); background: rgba(4, 10, 17, 0.82); color: var(--text); font-size: 0.95rem; }
    .stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 18px 0; }
    .stat { background: var(--panel); border: 1px solid var(--border); border-radius: 18px; padding: 16px; box-shadow: var(--shadow); }
    .stat b { display: block; font-size: 1.24rem; margin-bottom: 4px; }
    .featured { background: linear-gradient(135deg, rgba(255,122,24,0.16), rgba(45,212,191,0.15)); border: 1px solid var(--border); border-radius: 22px; padding: 18px 20px; margin-bottom: 18px; box-shadow: var(--shadow); }
    .featured h2 { margin: 0 0 8px; font-size: 1.08rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
    .card { background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.015)); border: 1px solid var(--border); border-radius: 20px; padding: 16px; display: flex; flex-direction: column; gap: 10px; box-shadow: var(--shadow); transition: transform 0.2s ease, border-color 0.2s ease; }
    .card:hover { transform: translateY(-2px); border-color: rgba(45,212,191,0.45); }
    .meta-row { display: flex; flex-wrap: wrap; gap: 8px; }
    .badge { display: inline-block; width: fit-content; padding: 5px 10px; border-radius: 999px; background: rgba(45,212,191,0.16); color: #9ef5ea; font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.04em; }
    .card h3 { margin: 0; font-size: 1rem; line-height: 1.35; }
    .card-image { width: 100%; height: 140px; object-fit: cover; border-radius: 14px; border: 1px solid var(--border); background: rgba(255,255,255,0.04); }
    .path { color: var(--muted); font-size: 0.9rem; margin: 0; }
    .card a { margin-top: auto; color: var(--accent-2); text-decoration: none; font-weight: 700; display: inline-block; }
    .card a:hover { text-decoration: underline; }
    .empty { background: var(--panel); border: 1px solid var(--border); border-radius: 16px; padding: 24px; color: var(--muted); text-align: center; box-shadow: var(--shadow); }
    .pagination {
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 16px;
      margin: 36px 0 20px;
      flex-wrap: wrap;
    }
    .page-btn {
      background: var(--panel);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 10px 20px;
      border-radius: 999px;
      cursor: pointer;
      font-weight: 600;
      transition: all 0.2s ease;
      box-shadow: var(--shadow);
    }
    .page-btn:hover:not(:disabled) {
      border-color: var(--accent);
      color: var(--accent);
      transform: translateY(-2px);
    }
    .page-btn:disabled {
      opacity: 0.35;
      cursor: not-allowed;
    }
    .page-info {
      color: var(--muted);
      font-weight: 600;
      font-size: 0.95rem;
    }
    @media (max-width: 760px) { .toolbar, .stats { grid-template-columns: 1fr; } .wrap { padding: 16px; } .hero { padding: 20px; } }
    .modal-overlay {
      display: none;
      width: 100%;
      min-height: 100vh;
      background: #060b12;
      flex-direction: column;
      animation: fadeIn 0.3s ease;
    }
    .modal-overlay.active {
      display: flex;
    }
    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    .modal-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 24px;
      background: rgba(17, 24, 39, 0.96);
      border-bottom: 1px solid var(--border);
      backdrop-filter: blur(14px);
      box-shadow: 0 4px 25px rgba(0,0,0,0.45);
      z-index: 2;
    }
    .modal-back-btn {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: linear-gradient(135deg, #ff7a18, #ff5200);
      color: #fff;
      border: none;
      padding: 10px 22px;
      border-radius: 999px;
      font-family: 'Inter', sans-serif;
      font-weight: 600;
      font-size: 0.95rem;
      cursor: pointer;
      box-shadow: 0 4px 15px rgba(255, 122, 24, 0.35);
      transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .modal-back-btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(255, 122, 24, 0.55);
    }
    .modal-title {
      font-weight: 600;
      color: var(--text);
      font-size: 1.05rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 60%;
    }
    .modal-iframe {
      flex: 1;
      width: 100%;
      border: none;
      background: #0f172a;
    }
  </style>
</head>
<body>
  <main class=\"wrap\">
    <header class=\"hero\">
      <h1>Catálogo de recetas</h1>
      <p>Explora recetas fáciles, rápidas y originales para cada ocasión: platos principales, arroces, ensaladas, postres y propuestas creativas que te ayudarán a cocinar con inspiración. Un catálogo claro, ordenado y pensado para que encuentres ideas deliciosas en segundos.</p>
      <div class=\"toolbar\">
        <input id=\"searchInput\" type=\"text\" placeholder=\"Buscar por nombre, ingrediente o ruta\" />
        <select id=\"ingredientFilter\">
          <option value=\"all\">Todos los ingredientes</option>
        </select>
        <select id=\"sortSelect\">
          <option value=\"alpha\">Orden alfabético</option>
          <option value=\"ingredient\">Por ingrediente</option>
        </select>
      </div>
    </header>

    <section class=\"stats\" aria-label=\"Estadísticas del catálogo\">
      <div class=\"stat\"><b id=\"countTotal\">0</b><span>Recetas</span></div>
      <div class=\"stat\"><b id=\"countIngredients\">0</b><span>Ingredientes principales</span></div>
      <div class=\"stat\"><b id=\"countFeatured\">0</b><span>Receta destacada</span></div>
    </section>

    <section class=\"featured\" id=\"featuredCard\" aria-label=\"Receta destacada\"></section>
    <section id=\"recipeGrid\" class=\"grid\" aria-label=\"Listado de recetas\"></section>
    <div id=\"pagination\" class=\"pagination\" aria-label=\"Paginación\"></div>
  </main>

  <div id=\"recipeModal\" class=\"modal-overlay\" aria-hidden=\"true\">
    <header class=\"modal-header\">
      <button class=\"modal-back-btn\" onclick=\"closeRecipe()\">
        <span>⬅</span> Volver al catálogo
      </button>
      <div id=\"modalTitle\" class=\"modal-title\"></div>
    </header>
    <iframe id=\"recipeFrame\" class=\"modal-iframe\" title=\"Visor de receta\" allowfullscreen></iframe>
  </div>

  <script>
    const recipes = __RECIPES_JSON__;
    const searchInput = document.getElementById('searchInput');
    const ingredientFilter = document.getElementById('ingredientFilter');
    const sortSelect = document.getElementById('sortSelect');
    const recipeGrid = document.getElementById('recipeGrid');
    const featuredCard = document.getElementById('featuredCard');
    const countTotal = document.getElementById('countTotal');
    const countIngredients = document.getElementById('countIngredients');
    const countFeatured = document.getElementById('countFeatured');
    
    let currentPage = 1;
    const pageSize = 30;

    function escapeHtml(value) {
      return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }

    function buildIngredientsOptions() {
      const allIngredients = recipes.flatMap((item) => Array.isArray(item.ingredients) && item.ingredients.length ? item.ingredients : [item.ingredient || 'General']);
      const values = [...new Set(allIngredients)].sort((a, b) => a.localeCompare(b, 'es'));
      ingredientFilter.innerHTML = '<option value="all">Todos los ingredientes</option>' + values.map((value) => '<option value="' + escapeHtml(value) + '">' + escapeHtml(value) + '</option>').join('');
    }

    function getFilteredRecipes() {
      const query = searchInput.value.trim().toLowerCase();
      const ingredient = ingredientFilter.value;
      const sort = sortSelect.value;
      let list = recipes.filter((recipe) => {
        const ingList = Array.isArray(recipe.ingredients) && recipe.ingredients.length ? recipe.ingredients : [recipe.ingredient || 'General'];
        const haystack = recipe.title + ' ' + ingList.join(' ');
        const matchesQuery = !query || haystack.toLowerCase().includes(query);
        const matchesIngredient = ingredient === 'all' || ingList.includes(ingredient);
        return matchesQuery && matchesIngredient;
      });

      if (sort === 'alpha') {
        list.sort((a, b) => a.title.localeCompare(b.title, 'es'));
      } else if (sort === 'ingredient') {
        list.sort((a, b) => a.ingredient.localeCompare(b.ingredient, 'es') || a.title.localeCompare(b.title, 'es'));
      }
      return list;
    }

    function sendHeightToParent(scrollToTop) {
      if (window.parent && window.parent !== window) {
        const height = document.documentElement.scrollHeight || document.body.scrollHeight;
        window.parent.postMessage({ type: 'resize-iframe', height: height, scrollToTop: !!scrollToTop }, '*');
      }
    }

    function openRecipeByIndex(idx) {
      const recipe = recipes[idx];
      if (!recipe) return;
      const overlay = document.getElementById('recipeModal');
      const iframe = document.getElementById('recipeFrame');
      const titleEl = document.getElementById('modalTitle');
      const mainEl = document.querySelector('main');
      
      titleEl.textContent = recipe.title || 'Receta';
      mainEl.style.display = 'none';
      overlay.classList.add('active');
      overlay.setAttribute('aria-hidden', 'false');
      
      iframe.onload = function() {
        try {
          const frameHeight = iframe.contentWindow.document.documentElement.scrollHeight || iframe.contentWindow.document.body.scrollHeight;
          if (frameHeight && frameHeight > 400) {
            iframe.style.height = frameHeight + 'px';
          } else {
            iframe.style.height = '3200px';
          }
        } catch (e) {
          iframe.style.height = '3200px';
        }
        sendHeightToParent(true);
      };
      
      iframe.src = recipe.link;
      iframe.style.height = '3200px';
      sendHeightToParent(true);
    }

    function closeRecipe() {
      const overlay = document.getElementById('recipeModal');
      const iframe = document.getElementById('recipeFrame');
      const mainEl = document.querySelector('main');
      
      overlay.classList.remove('active');
      overlay.setAttribute('aria-hidden', 'true');
      iframe.src = '';
      mainEl.style.display = 'block';
      setTimeout(() => sendHeightToParent(true), 100);
    }

    function renderRecipes() {
      const list = getFilteredRecipes();
      countTotal.textContent = list.length;
      const allIngs = list.flatMap((item) => Array.isArray(item.ingredients) && item.ingredients.length ? item.ingredients : [item.ingredient || 'General']);
      countIngredients.textContent = [...new Set(allIngs)].length;
      const pagEl = document.getElementById('pagination');
      
      if (!list.length) {
        recipeGrid.innerHTML = '<div class="empty">No hay recetas que coincidan con los filtros.</div>';
        if (pagEl) pagEl.innerHTML = '';
        return;
      }

      const totalPages = Math.ceil(list.length / pageSize);
      if (currentPage > totalPages) currentPage = 1;
      
      const startIdx = (currentPage - 1) * pageSize;
      const paginatedList = list.slice(startIdx, startIdx + pageSize);

      recipeGrid.innerHTML = paginatedList.map((recipe) => {
        const idx = recipes.indexOf(recipe);
        const ingredients = Array.isArray(recipe.ingredients) && recipe.ingredients.length ? recipe.ingredients.slice(0, 4) : [recipe.ingredient || 'General'];
        const ingredientMarkup = ingredients.map((item) => '<span class="badge">' + escapeHtml(item) + '</span>').join('');
        const imageMarkup = recipe.image ? '<img class="card-image" src="' + escapeHtml(recipe.image) + '" alt="' + escapeHtml(recipe.title) + '" />' : '';
        return '<article class="card" onclick="openRecipeByIndex(' + idx + ')" style="cursor:pointer;" aria-label="' + escapeHtml(recipe.title) + '">' +
          '<div class="meta-row">' + ingredientMarkup + '</div>' +
          '<h3>' + escapeHtml(recipe.title) + '</h3>' +
          (imageMarkup ? imageMarkup : '') +
          '<a href="javascript:void(0)" onclick="openRecipeByIndex(' + idx + '); return false;">Abrir receta →</a>' +
          '</article>';
      }).join('');
      
      renderPagination(totalPages);
      setTimeout(() => sendHeightToParent(false), 100);
    }

    function renderPagination(totalPages) {
      const pagEl = document.getElementById('pagination');
      if (!pagEl) return;
      if (totalPages <= 1) {
        pagEl.innerHTML = '';
        return;
      }
      pagEl.innerHTML = '<button class="page-btn" onclick="changePage(-1)" ' + (currentPage === 1 ? 'disabled' : '') + '>⬅ Anterior</button>' +
        '<span class="page-info">Página ' + currentPage + ' de ' + totalPages + '</span>' +
        '<button class="page-btn" onclick="changePage(1)" ' + (currentPage === totalPages ? 'disabled' : '') + '>Siguiente ➡</button>';
    }

    function changePage(delta) {
      currentPage += delta;
      renderRecipes();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function renderFeatured() {
      const list = getFilteredRecipes();
      if (!list.length) {
        featuredCard.innerHTML = '<div class="empty">Sin resultados en este momento.</div>';
        countFeatured.textContent = 0;
        return;
      }
      const today = new Date();
      const index = Math.abs(Math.sin((today.getDate() + 1) * (today.getMonth() + 1) * 17)) % list.length;
      const featured = list[Math.floor(index)];
      const idx = recipes.indexOf(featured);
      featuredCard.innerHTML = '<h2>⭐ Receta destacada de hoy</h2><div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center;"><div><strong>' + escapeHtml(featured.title) + '</strong><br /><span style="color:#8ba0b3;">' + escapeHtml(featured.ingredient || 'General') + '</span></div><a href="javascript:void(0)" onclick="openRecipeByIndex(' + idx + '); return false;" style="color:#fff; background:#ff7a18; padding:8px 12px; border-radius:999px; text-decoration:none; font-weight:600;">Ver receta</a></div>';
      countFeatured.textContent = 1;
    }

    [searchInput, ingredientFilter, sortSelect].forEach((element) => {
      element.addEventListener('input', () => { currentPage = 1; renderRecipes(); renderFeatured(); });
      element.addEventListener('change', () => { currentPage = 1; renderRecipes(); renderFeatured(); });
    });

    buildIngredientsOptions();
    renderRecipes();
    renderFeatured();
    setTimeout(() => sendHeightToParent(false), 300);
    window.addEventListener('resize', () => sendHeightToParent(false));
  </script>
</body>
</html>
"""
    return (
        template.replace("__RECIPES_JSON__", recipes_json)
        .replace("__SEO_TITLE__", seo_title)
        .replace("__SEO_DESCRIPTION__", seo_description)
        .replace("__SEO_KEYWORDS__", seo_keywords)
        .replace("__SCHEMA_JSON__", schema_json)
    )


def write_recipe_viewer_page(
    entries: list[dict[str, Any]] | None = None,
    output_dir: Path | None = None,
    title: str | None = None,
    source_path: str | None = None,
) -> Path:
    base = output_dir or ROOT
    page_path = base / "recipe_viewer.html"

    page_title = html.escape(title or "Visor de recetas")
    page_html = f"""<!DOCTYPE html>
<html lang=\"es\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>{page_title}</title>
  <meta name=\"robots\" content=\"noindex,follow\" />
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; padding: 2rem; background: #0f172a; color: #f8fafc; }}
    .card {{ max-width: 900px; margin: 0 auto; background: #111827; padding: 2rem; border-radius: 20px; }}
    a {{ color: #2dd4bf; }}
  </style>
</head>
<body>
  <div class=\"card\">
    <h1>Visor de recetas</h1>
    <p>Abriendo receta…</p>
    <p>Se está redirigiendo a la receta original.</p>
    <p><a id=\"fallbackLink\" href=\"#\">Abrir receta</a></p>
  </div>
  <script>
    const params = new URLSearchParams(window.location.search);
    const encodedPath = params.get('id') || '';
    const fallbackLink = document.getElementById('fallbackLink');

    try {{
      const padding = '='.repeat((4 - (encodedPath.length % 4)) % 4);
      const decoded = atob(encodedPath + padding);
      const targetUrl = new URL(decoded, window.location.href);
      fallbackLink.href = targetUrl.href;
      window.location.replace(targetUrl.href);
    }} catch (error) {{
      fallbackLink.textContent = 'Receta no encontrada';
      fallbackLink.removeAttribute('href');
    }}
  </script>
</body>
</html>
"""
    page_path.write_text(page_html, encoding="utf-8")
    return page_path


def write_recipe_link_pages(entries: list[dict[str, Any]], repo_root: Path | None = None) -> Path:
    return write_recipe_viewer_page(entries=entries, output_dir=repo_root or ROOT)


def main() -> None:
    entries = collect_recipe_entries()
    output_path = ROOT / "generated_recipe_catalog.html"
    output_path.write_text(build_catalog_html(entries), encoding="utf-8")
    write_recipe_viewer_page(entries)
    print(f"Generated {output_path} with {len(entries)} recipes")


if __name__ == "__main__":
    main()
