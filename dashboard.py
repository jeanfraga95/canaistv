"""dashboard.py — Render the HTML dashboard for TVProxy."""

from channels import CHANNELS

_CATEGORY_LABELS = {
    "esportes": "Esportes",
    "tv-aberta": "TV Aberta",
    "filmes-e-series": "Filmes e Séries",
    "variedades": "Variedades",
    "noticias": "Notícias",
    "infantil": "Infantil",
}

_QUALITY_COLORS = {
    "FHD": "#22c55e",
    "HD": "#3b82f6",
    "SD": "#f59e0b",
}


def render_dashboard() -> str:
    categories = list(_CATEGORY_LABELS.keys())

    # Build channel cards HTML
    cards_html = ""
    for ch in CHANNELS:
        cat_label = _CATEGORY_LABELS.get(ch["category"], ch["category"])
        has_direct = "✓" if ch.get("direct_m3u8") else ""
        cards_html += f"""
        <div class="card" data-id="{ch['id']}" data-cat="{ch['category']}" data-name="{ch['name'].lower()}">
            <div class="card-logo">
                <img src="{ch['logo']}" onerror="this.src='/static/placeholder.png'" alt="{ch['name']}">
            </div>
            <div class="card-body">
                <div class="card-name">{ch['name']}</div>
                <div class="card-cat">{cat_label}</div>
                <div class="card-links" id="links-{ch['id']}">
                    <span class="badge-loading">Carregando...</span>
                </div>
            </div>
            <div class="card-actions">
                <button class="btn-refresh" onclick="refreshChannel('{ch['id']}')" title="Reextract m3u8">↻</button>
                <button class="btn-vlc" onclick="copyVlc('{ch['id']}','hd')" title="Copiar link HD para VLC">📋 HD</button>
            </div>
        </div>"""

    # Build tab buttons
    tabs_html = '<button class="tab active" data-cat="all" onclick="filterCat(this,\'all\')">Todos</button>'
    for cat, label in _CATEGORY_LABELS.items():
        tabs_html += f'<button class="tab" data-cat="{cat}" onclick="filterCat(this,\'{cat}\')">{label}</button>'

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>TVProxy — Dashboard</title>
<style>
:root {{
    --bg: #0f172a;
    --surface: #1e293b;
    --card: #1f2937;
    --accent: #ef4444;
    --accent2: #3b82f6;
    --text: #f1f5f9;
    --muted: #94a3b8;
    --border: #334155;
    --green: #22c55e;
    --yellow: #f59e0b;
    --radius: 12px;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: 'Segoe UI', Arial, sans-serif; background:var(--bg); color:var(--text); min-height:100vh; }}

/* HEADER */
header {{
    background: linear-gradient(135deg,#0b1220,#1e293b);
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--border);
    position: sticky; top:0; z-index:100;
}}
.logo {{ display:flex; align-items:center; gap:12px; }}
.logo h1 {{ font-size:1.3rem; color:var(--accent); letter-spacing:1px; }}
.logo span {{ font-size:.75rem; color:var(--muted); }}
.header-links a {{
    color:var(--accent2); text-decoration:none; margin-left:16px;
    font-size:.85rem; border:1px solid var(--accent2);
    padding:6px 12px; border-radius:8px;
    transition:.2s;
}}
.header-links a:hover {{ background:var(--accent2); color:#fff; }}

/* CONTROLS */
.controls {{
    padding: 16px 24px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
}}
.search-row {{ display:flex; gap:10px; align-items:center; }}
.search-row input {{
    flex:1; padding:10px 16px; border-radius:10px;
    border:1px solid var(--border); background:var(--card);
    color:var(--text); font-size:.95rem; outline:none;
}}
.search-row input:focus {{ border-color:var(--accent2); }}
.btn-playlist {{
    padding:10px 16px; border-radius:10px; border:none;
    background:var(--accent); color:#fff; cursor:pointer;
    font-size:.85rem; white-space:nowrap;
    transition:.2s;
}}
.btn-playlist:hover {{ background:#dc2626; }}

/* TABS */
.tabs {{
    display:flex; gap:8px; overflow-x:auto; padding-bottom:2px;
}}
.tabs::-webkit-scrollbar {{ display:none; }}
.tab {{
    padding:7px 16px; border-radius:20px; border:none;
    background:var(--card); color:var(--muted); cursor:pointer;
    white-space:nowrap; font-size:.82rem; transition:.2s;
}}
.tab:hover {{ color:var(--text); }}
.tab.active {{ background:var(--accent); color:#fff; }}

/* STATS */
.stats {{
    padding:12px 24px;
    display:flex; gap:20px; flex-wrap:wrap;
    font-size:.8rem; color:var(--muted);
    border-bottom:1px solid var(--border);
}}
.stat {{ display:flex; align-items:center; gap:6px; }}
.stat b {{ color:var(--text); }}

/* GRID */
.grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
    padding: 20px 24px;
}}

/* CARD */
.card {{
    background:var(--card);
    border-radius:var(--radius);
    overflow:hidden;
    border:1px solid var(--border);
    transition: transform .2s, box-shadow .2s;
    display:flex; flex-direction:column;
}}
.card:hover {{ transform:translateY(-3px); box-shadow:0 8px 24px rgba(0,0,0,.4); }}
.card-logo {{
    background:#111827;
    height:80px;
    display:flex; align-items:center; justify-content:center;
    padding:12px;
}}
.card-logo img {{ max-height:60px; max-width:100%; object-fit:contain; }}
.card-body {{ padding:12px 14px; flex:1; }}
.card-name {{ font-size:.95rem; font-weight:600; margin-bottom:4px; }}
.card-cat {{ font-size:.72rem; color:var(--muted); margin-bottom:10px; text-transform:uppercase; letter-spacing:.5px; }}
.card-links {{ display:flex; flex-wrap:wrap; gap:6px; }}

/* QUALITY BADGES */
.badge {{
    display:inline-flex; align-items:center; gap:4px;
    padding:4px 10px; border-radius:20px; font-size:.72rem; font-weight:600;
    cursor:pointer; transition:.15s; text-decoration:none; color:#fff;
    border:none;
}}
.badge:hover {{ opacity:.8; filter:brightness(1.2); }}
.badge-fhd {{ background:#22c55e; }}
.badge-hd  {{ background:#3b82f6; }}
.badge-sd  {{ background:#f59e0b; color:#000; }}
.badge-none {{ background:#374151; color:var(--muted); cursor:default; font-size:.7rem; }}
.badge-loading {{ color:var(--muted); font-size:.72rem; font-style:italic; }}

/* CARD ACTIONS */
.card-actions {{
    display:flex; gap:6px; padding:10px 14px;
    border-top:1px solid var(--border);
}}
.btn-refresh {{
    padding:5px 10px; border-radius:8px; border:1px solid var(--border);
    background:transparent; color:var(--muted); cursor:pointer; font-size:.85rem;
    transition:.2s;
}}
.btn-refresh:hover {{ color:var(--text); border-color:var(--text); }}
.btn-vlc {{
    flex:1; padding:5px 10px; border-radius:8px; border:none;
    background:var(--accent2); color:#fff; cursor:pointer; font-size:.8rem;
    transition:.2s;
}}
.btn-vlc:hover {{ background:#2563eb; }}

/* TOAST */
#toast {{
    position:fixed; bottom:24px; right:24px;
    background:#1e293b; border:1px solid var(--accent2);
    color:var(--text); padding:12px 20px; border-radius:10px;
    font-size:.85rem; opacity:0; transition:.3s; z-index:9999;
    pointer-events:none;
}}
#toast.show {{ opacity:1; }}

/* FOOTER */
footer {{
    text-align:center; padding:20px;
    font-size:.75rem; color:var(--muted);
    border-top:1px solid var(--border); margin-top:20px;
}}

/* RESPONSIVE */
@media(max-width:600px) {{
    .grid {{ padding:12px; gap:12px; }}
    header {{ padding:12px 16px; }}
}}
</style>
</head>
<body>

<header>
    <div class="logo">
        <div>
            <h1>📺 TVPROXY</h1>
            <span>Dashboard de Canais — {len(CHANNELS)} canais</span>
        </div>
    </div>
    <div class="header-links">
        <a href="/playlist.m3u" download>⬇ Playlist HD</a>
        <a href="/playlist_fhd.m3u" download>⬇ FHD</a>
        <a href="/playlist_sd.m3u" download>⬇ SD</a>
        <a href="/api/cache/clear" onclick="return confirm('Limpar cache de todos os canais?')">🗑 Cache</a>
    </div>
</header>

<div class="controls">
    <div class="search-row">
        <input type="text" id="searchInput" placeholder="🔍  Buscar canal..." oninput="applyFilter()">
        <button class="btn-playlist" onclick="copyPlaylist()">📋 Copiar Playlist</button>
    </div>
    <div class="tabs" id="tabs">
        {tabs_html}
    </div>
</div>

<div class="stats" id="stats">
    <div class="stat">Canais: <b id="stat-total">{len(CHANNELS)}</b></div>
    <div class="stat">Visíveis: <b id="stat-visible">{len(CHANNELS)}</b></div>
    <div class="stat">Com stream: <b id="stat-live">0</b></div>
</div>

<div class="grid" id="grid">
{cards_html}
</div>

<footer>TVProxy © 2026 — Links fixos para todos os canais de tvonlinehd.com.br</footer>

<div id="toast"></div>

<script>
const BASE = window.location.origin;
let currentCat = 'all';
let channelData = {{}};   // id → {{qualities:{{...}}}}

// ─── FILTER ────────────────────────────────────────────────────────────────
function applyFilter() {{
    const q = document.getElementById('searchInput').value.toLowerCase();
    let visible = 0;
    document.querySelectorAll('.card').forEach(c => {{
        const matchName = c.dataset.name.includes(q);
        const matchCat  = currentCat === 'all' || c.dataset.cat === currentCat;
        const show = matchName && matchCat;
        c.style.display = show ? '' : 'none';
        if (show) visible++;
    }});
    document.getElementById('stat-visible').textContent = visible;
}}

function filterCat(el, cat) {{
    currentCat = cat;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    applyFilter();
}}

// ─── LOAD CHANNEL INFO ─────────────────────────────────────────────────────
async function loadChannelInfo(channelId) {{
    try {{
        const r = await fetch(`${{BASE}}/api/channel/${{channelId}}`);
        const data = await r.json();
        channelData[channelId] = data;
        renderLinks(channelId, data.fixed_links || {{}});
    }} catch(e) {{
        document.getElementById(`links-${{channelId}}`).innerHTML =
            '<span class="badge-none">Erro</span>';
    }}
}}

function renderLinks(id, links) {{
    const el = document.getElementById(`links-${{id}}`);
    if (!el) return;
    if (!links || Object.keys(links).length === 0) {{
        el.innerHTML = '<span class="badge badge-none">Sem stream</span>';
        return;
    }}
    const order = ['FHD','HD','SD'];
    let html = '';
    order.forEach(q => {{
        if (links[q]) {{
            const cls = `badge-${{q.toLowerCase()}}`;
            html += `<button class="badge ${{cls}}" onclick="copyLink('${{links[q]}}','${{q}}')" title="${{links[q]}}">${{q}}</button>`;
        }}
    }});
    el.innerHTML = html;

    // update live counter
    updateLiveCount();
}}

function updateLiveCount() {{
    const live = Object.values(channelData).filter(d =>
        d.fixed_links && Object.keys(d.fixed_links).length > 0
    ).length;
    document.getElementById('stat-live').textContent = live;
}}

// ─── COPY ──────────────────────────────────────────────────────────────────
function copyLink(url, quality) {{
    navigator.clipboard.writeText(url).then(() => {{
        toast(`📋 Link ${{quality}} copiado!`);
    }});
}}

function copyVlc(id, quality) {{
    const url = `${{BASE}}/stream/${{id}}/${{quality}}.m3u8`;
    navigator.clipboard.writeText(url).then(() => {{
        toast(`📋 Link VLC copiado: ${{id}}`);
    }});
}}

function copyPlaylist() {{
    navigator.clipboard.writeText(`${{BASE}}/playlist.m3u`).then(() => {{
        toast('📋 URL da playlist copiada!');
    }});
}}

// ─── REFRESH ───────────────────────────────────────────────────────────────
async function refreshChannel(id) {{
    toast(`↻ Reextraindo ${{id}}...`);
    document.getElementById(`links-${{id}}`).innerHTML =
        '<span class="badge-loading">Reextraindo...</span>';
    await fetch(`${{BASE}}/api/channel/${{id}}/refresh`);
    await loadChannelInfo(id);
    toast(`✓ ${{id}} atualizado!`);
}}

// ─── TOAST ─────────────────────────────────────────────────────────────────
let _toastTimer;
function toast(msg) {{
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => el.classList.remove('show'), 2800);
}}

// ─── INIT ──────────────────────────────────────────────────────────────────
// Load channel info in batches to avoid hammering the server
async function initDashboard() {{
    const cards = [...document.querySelectorAll('.card')];
    const BATCH = 5;
    for (let i = 0; i < cards.length; i += BATCH) {{
        const batch = cards.slice(i, i + BATCH);
        await Promise.all(batch.map(c => loadChannelInfo(c.dataset.id)));
        // small delay between batches
        await new Promise(r => setTimeout(r, 300));
    }}
}}

initDashboard();
</script>
</body>
</html>"""
