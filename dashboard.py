"""dashboard.py — Render the HTML dashboard for TVProxy."""

from channels import CHANNELS

_CATEGORY_LABELS = {
    "esportes": "Esportes",
    "tv-aberta": "TV Aberta",
    "filmes-e-series": "Filmes e Series",
    "variedades": "Variedades",
    "noticias": "Noticias",
    "infantil": "Infantil",
}


def _build_cards():
    parts = []
    for ch in CHANNELS:
        cat_label = _CATEGORY_LABELS.get(ch["category"], ch["category"])
        logo = ch["logo"].replace('"', "&quot;")
        name = ch["name"].replace('"', "&quot;").replace("'", "&#39;")
        card = (
            '<div class="card" data-id="' + ch["id"] + '" data-cat="' + ch["category"] + '" data-name="' + ch["name"].lower() + '">'
            '<div class="card-logo"><img src="' + logo + '" onerror="this.style.display=\'none\'" alt="' + name + '"></div>'
            '<div class="card-body">'
            '<div class="card-name">' + name + '</div>'
            '<div class="card-cat">' + cat_label + '</div>'
            '<div class="card-links" id="links-' + ch["id"] + '"><span class="badge-loading">...</span></div>'
            '</div>'
            '<div class="card-actions">'
            '<button class="btn-refresh" onclick="refreshChannel(\'' + ch["id"] + '\')" title="Reextrair">&#8635;</button>'
            '<button class="btn-vlc" onclick="copyVlc(\'' + ch["id"] + '\',\'hd\')">&#128203; HD</button>'
            '</div>'
            '</div>'
        )
        parts.append(card)
    return "\n".join(parts)


def _build_tabs():
    parts = ['<button class="tab active" data-cat="all" onclick="filterCat(this,\'all\')">Todos</button>']
    for cat, label in _CATEGORY_LABELS.items():
        parts.append(
            '<button class="tab" data-cat="' + cat + '" onclick="filterCat(this,\'' + cat + '\')">' + label + '</button>'
        )
    return "\n".join(parts)


CSS = (
    ":root {"
    "--bg:#0f172a;--surface:#1e293b;--card:#1f2937;--accent:#ef4444;"
    "--accent2:#3b82f6;--text:#f1f5f9;--muted:#94a3b8;--border:#334155;--radius:12px;"
    "}"
    "*{margin:0;padding:0;box-sizing:border-box}"
    "body{font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}"
    "header{background:linear-gradient(135deg,#0b1220,#1e293b);padding:16px 24px;display:flex;"
    "align-items:center;justify-content:space-between;border-bottom:1px solid var(--border);"
    "position:sticky;top:0;z-index:100}"
    ".logo h1{font-size:1.3rem;color:var(--accent);letter-spacing:1px}"
    ".logo span{font-size:.75rem;color:var(--muted);display:block}"
    ".header-links a{color:var(--accent2);text-decoration:none;margin-left:12px;font-size:.82rem;"
    "border:1px solid var(--accent2);padding:6px 12px;border-radius:8px;transition:.2s}"
    ".header-links a:hover{background:var(--accent2);color:#fff}"
    ".controls{padding:14px 24px;display:flex;flex-direction:column;gap:10px;"
    "background:var(--surface);border-bottom:1px solid var(--border)}"
    ".search-row{display:flex;gap:10px;align-items:center}"
    ".search-row input{flex:1;padding:10px 16px;border-radius:10px;border:1px solid var(--border);"
    "background:var(--card);color:var(--text);font-size:.95rem;outline:none}"
    ".search-row input:focus{border-color:var(--accent2)}"
    ".btn-playlist{padding:10px 16px;border-radius:10px;border:none;background:var(--accent);"
    "color:#fff;cursor:pointer;font-size:.82rem;white-space:nowrap;transition:.2s}"
    ".btn-playlist:hover{background:#dc2626}"
    ".tabs{display:flex;gap:8px;overflow-x:auto;padding-bottom:2px}"
    ".tabs::-webkit-scrollbar{display:none}"
    ".tab{padding:7px 16px;border-radius:20px;border:none;background:var(--card);color:var(--muted);"
    "cursor:pointer;white-space:nowrap;font-size:.82rem;transition:.2s}"
    ".tab:hover{color:var(--text)}"
    ".tab.active{background:var(--accent);color:#fff}"
    ".stats{padding:10px 24px;display:flex;gap:20px;flex-wrap:wrap;font-size:.8rem;"
    "color:var(--muted);border-bottom:1px solid var(--border)}"
    ".stat b{color:var(--text)}"
    ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:14px;padding:18px 24px}"
    ".card{background:var(--card);border-radius:var(--radius);overflow:hidden;"
    "border:1px solid var(--border);transition:transform .2s,box-shadow .2s;display:flex;flex-direction:column}"
    ".card:hover{transform:translateY(-3px);box-shadow:0 8px 24px rgba(0,0,0,.4)}"
    ".card-logo{background:#111827;height:72px;display:flex;align-items:center;justify-content:center;padding:10px}"
    ".card-logo img{max-height:52px;max-width:100%;object-fit:contain}"
    ".card-body{padding:10px 14px;flex:1}"
    ".card-name{font-size:.92rem;font-weight:600;margin-bottom:3px}"
    ".card-cat{font-size:.7rem;color:var(--muted);margin-bottom:9px;text-transform:uppercase;letter-spacing:.5px}"
    ".card-links{display:flex;flex-wrap:wrap;gap:5px}"
    ".badge{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:20px;"
    "font-size:.7rem;font-weight:600;cursor:pointer;transition:.15s;color:#fff;border:none}"
    ".badge:hover{opacity:.8}"
    ".badge-fhd{background:#22c55e}"
    ".badge-hd{background:#3b82f6}"
    ".badge-sd{background:#f59e0b;color:#000}"
    ".badge-none{background:#374151;color:var(--muted);cursor:default;font-size:.68rem}"
    ".badge-loading{color:var(--muted);font-size:.7rem;font-style:italic}"
    ".card-actions{display:flex;gap:6px;padding:8px 14px;border-top:1px solid var(--border)}"
    ".btn-refresh{padding:5px 10px;border-radius:8px;border:1px solid var(--border);"
    "background:transparent;color:var(--muted);cursor:pointer;font-size:.9rem;transition:.2s}"
    ".btn-refresh:hover{color:var(--text);border-color:var(--text)}"
    ".btn-vlc{flex:1;padding:5px 10px;border-radius:8px;border:none;background:var(--accent2);"
    "color:#fff;cursor:pointer;font-size:.78rem;transition:.2s}"
    ".btn-vlc:hover{background:#2563eb}"
    "#toast{position:fixed;bottom:24px;right:24px;background:#1e293b;border:1px solid var(--accent2);"
    "color:var(--text);padding:12px 20px;border-radius:10px;font-size:.85rem;opacity:0;"
    "transition:.3s;z-index:9999;pointer-events:none}"
    "#toast.show{opacity:1}"
    "footer{text-align:center;padding:20px;font-size:.75rem;color:var(--muted);"
    "border-top:1px solid var(--border);margin-top:20px}"
    "@media(max-width:600px){.grid{padding:10px;gap:10px}header{padding:10px 14px}"
    ".controls{padding:10px 14px}}"
)

JS = (
    "const BASE=window.location.origin;"
    "let currentCat='all';"
    "let channelData={};"
    "function applyFilter(){"
    "const q=document.getElementById('searchInput').value.toLowerCase();"
    "let visible=0;"
    "document.querySelectorAll('.card').forEach(c=>{"
    "const matchName=c.dataset.name.includes(q);"
    "const matchCat=currentCat==='all'||c.dataset.cat===currentCat;"
    "const show=matchName&&matchCat;"
    "c.style.display=show?'':'none';"
    "if(show)visible++;"
    "});"
    "document.getElementById('stat-visible').textContent=visible;"
    "}"
    "function filterCat(el,cat){"
    "currentCat=cat;"
    "document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));"
    "el.classList.add('active');"
    "applyFilter();"
    "}"
    "async function loadChannelInfo(channelId){"
    "try{"
    "const r=await fetch(BASE+'/api/channel/'+channelId);"
    "const data=await r.json();"
    "channelData[channelId]=data;"
    "renderLinks(channelId,data.fixed_links||{});"
    "}catch(e){"
    "const el=document.getElementById('links-'+channelId);"
    "if(el)el.innerHTML='<span class=\"badge badge-none\">Erro</span>';"
    "}"
    "}"
    "function renderLinks(id,links){"
    "const el=document.getElementById('links-'+id);"
    "if(!el)return;"
    "if(!links||Object.keys(links).length===0){"
    "el.innerHTML='<span class=\"badge badge-none\">Sem stream</span>';"
    "return;"
    "}"
    "const order=['FHD','HD','SD'];"
    "let html='';"
    "order.forEach(q=>{"
    "if(links[q]){"
    "html+='<button class=\"badge badge-'+q.toLowerCase()+'\" '"
    "+'onclick=\"copyLink(\\''+links[q]+'\\',\\''+q+'\\')\" '"
    "+'title=\"'+links[q]+'\">'+q+'</button>';"
    "}"
    "});"
    "el.innerHTML=html;"
    "updateLiveCount();"
    "}"
    "function updateLiveCount(){"
    "const live=Object.values(channelData).filter(d=>d.fixed_links&&Object.keys(d.fixed_links).length>0).length;"
    "document.getElementById('stat-live').textContent=live;"
    "}"
    "function copyLink(url,quality){"
    "navigator.clipboard.writeText(url).then(()=>toast('Copiado '+quality+': '+url));"
    "}"
    "function copyVlc(id,quality){"
    "const url=BASE+'/stream/'+id+'/'+quality+'.m3u8';"
    "navigator.clipboard.writeText(url).then(()=>toast('Link VLC copiado: '+id));"
    "}"
    "function copyPlaylist(){"
    "navigator.clipboard.writeText(BASE+'/playlist.m3u').then(()=>toast('Playlist copiada!'));"
    "}"
    "async function refreshChannel(id){"
    "toast('Reextraindo '+id+'...');"
    "const el=document.getElementById('links-'+id);"
    "if(el)el.innerHTML='<span class=\"badge-loading\">Reextraindo...</span>';"
    "try{"
    "await fetch(BASE+'/api/channel/'+id+'/refresh');"
    "await loadChannelInfo(id);"
    "toast('Atualizado: '+id);"
    "}catch(e){toast('Erro ao atualizar '+id);}"
    "}"
    "let _toastTimer;"
    "function toast(msg){"
    "const el=document.getElementById('toast');"
    "el.textContent=msg;"
    "el.classList.add('show');"
    "clearTimeout(_toastTimer);"
    "_toastTimer=setTimeout(()=>el.classList.remove('show'),3000);"
    "}"
    "async function initDashboard(){"
    "const cards=[...document.querySelectorAll('.card')];"
    "const BATCH=6;"
    "for(let i=0;i<cards.length;i+=BATCH){"
    "const batch=cards.slice(i,i+BATCH);"
    "await Promise.all(batch.map(c=>loadChannelInfo(c.dataset.id)));"
    "await new Promise(r=>setTimeout(r,200));"
    "}"
    "}"
    "initDashboard();"
)


def render_dashboard():
    total = len(CHANNELS)
    cards = _build_cards()
    tabs = _build_tabs()

    return (
        "<!DOCTYPE html>\n"
        "<html lang='pt-BR'>\n"
        "<head>\n"
        "<meta charset='UTF-8'>\n"
        "<meta name='viewport' content='width=device-width,initial-scale=1.0'>\n"
        "<title>TVProxy Dashboard</title>\n"
        "<style>" + CSS + "</style>\n"
        "</head>\n"
        "<body>\n"
        "<header>\n"
        "  <div class='logo'><h1>&#128250; TVPROXY</h1><span>" + str(total) + " canais</span></div>\n"
        "  <div class='header-links'>\n"
        "    <a href='/playlist.m3u' download>&#11015; Playlist HD</a>\n"
        "    <a href='/playlist_fhd.m3u' download>&#11015; FHD</a>\n"
        "    <a href='/playlist_sd.m3u' download>&#11015; SD</a>\n"
        "    <a href='/api/cache/clear' onclick=\"return confirm('Limpar cache?')\">&#128465; Cache</a>\n"
        "  </div>\n"
        "</header>\n"
        "<div class='controls'>\n"
        "  <div class='search-row'>\n"
        "    <input type='text' id='searchInput' placeholder='Buscar canal...' oninput='applyFilter()'>\n"
        "    <button class='btn-playlist' onclick='copyPlaylist()'>Copiar Playlist</button>\n"
        "  </div>\n"
        "  <div class='tabs'>" + tabs + "</div>\n"
        "</div>\n"
        "<div class='stats'>\n"
        "  <div class='stat'>Canais: <b id='stat-total'>" + str(total) + "</b></div>\n"
        "  <div class='stat'>Visiveis: <b id='stat-visible'>" + str(total) + "</b></div>\n"
        "  <div class='stat'>Com stream: <b id='stat-live'>0</b></div>\n"
        "</div>\n"
        "<div class='grid'>" + cards + "</div>\n"
        "<footer>TVProxy &copy; 2026</footer>\n"
        "<div id='toast'></div>\n"
        "<script>" + JS + "</script>\n"
        "</body></html>"
    )
