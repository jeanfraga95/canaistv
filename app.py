#!/usr/bin/env python3
"""
tvproxy — Flask streaming proxy for tvonlinehd.com.br channels
Fixed URLs per channel that survive m3u8 source URL changes.
"""

import re
import time
import json
import logging
import threading
import requests
from urllib.parse import urljoin, urlparse, urlencode, quote
from flask import Flask, Response, request, jsonify, redirect, stream_with_context
from channels import CHANNELS, CHANNELS_BY_ID

# ─── CONFIG ──────────────────────────────────────────────────────────────────

PORT = 5000
HOST = "0.0.0.0"
CACHE_TTL = 300          # seconds before re-extracting m3u8 (5 min)
EXTRACT_TIMEOUT = 15     # seconds to wait for iframe scrape
PROXY_CHUNK = 8192       # bytes per streaming chunk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("tvproxy.log"),
    ],
)
log = logging.getLogger("tvproxy")

app = Flask(__name__)

# ─── IN-MEMORY CACHE ─────────────────────────────────────────────────────────
# { channel_id: { "streams": [...], "ts": float } }
_cache: dict = {}
_cache_lock = threading.Lock()

# ─── HEADERS USED FOR EXTRACTION ─────────────────────────────────────────────
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": "https://tvonlinehd.com.br/",
    "Origin": "https://tvonlinehd.com.br",
}

# ─── EMBEDTV PLAYER DOMAINS ──────────────────────────────────────────────────
EMBEDTV_HOSTS = [
    "joel.embedtv.live",
    "embedtv.live",
]

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _find_m3u8_in_text(text: str) -> list[str]:
    """Extract all .m3u8 URLs from a chunk of HTML/JS text."""
    pattern = r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*'
    found = re.findall(pattern, text)
    # deduplicate preserving order
    seen, result = set(), []
    for u in found:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


def _fetch_page(url: str, extra_headers: dict = None, timeout: int = 10) -> str | None:
    """Fetch a URL and return text, or None on failure."""
    hdrs = {**BROWSER_HEADERS}
    if extra_headers:
        hdrs.update(extra_headers)
    try:
        r = requests.get(url, headers=hdrs, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception as e:
        log.debug("_fetch_page(%s) → %s", url, e)
        return None


def _extract_from_embedtv(channel_url: str) -> list[str]:
    """
    Fetch joel.embedtv.live/<canal> page, find the actual m3u8 source.
    The page usually embeds an iframe or JS variable with the m3u8 URL.
    """
    html = _fetch_page(channel_url, timeout=EXTRACT_TIMEOUT)
    if not html:
        return []

    streams = _find_m3u8_in_text(html)

    # Also look for iframe src that may itself load an m3u8
    iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I)
    for iframe_url in iframes:
        if not iframe_url.startswith("http"):
            iframe_url = urljoin(channel_url, iframe_url)
        sub = _fetch_page(iframe_url, extra_headers={"Referer": channel_url}, timeout=EXTRACT_TIMEOUT)
        if sub:
            streams += _find_m3u8_in_text(sub)

    # JS: look for jwplayer / hls sources
    js_sources = re.findall(
        r'(?:file|src|source|hlsUrl|streamUrl)\s*[=:]\s*["\']?(https?://[^\s"\'<>,;]+\.m3u8[^\s"\'<>,;]*)',
        html, re.I
    )
    streams += js_sources

    # deduplicate
    seen, result = set(), []
    for u in streams:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


def _extract_from_player_page(player_url: str) -> list[str]:
    """Generic extraction: fetch page, hunt for m3u8."""
    html = _fetch_page(player_url, timeout=EXTRACT_TIMEOUT)
    if not html:
        return []
    return _find_m3u8_in_text(html)


def _probe_m3u8(url: str) -> bool:
    """Return True if the URL responds with HLS content."""
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=8, stream=True)
        if r.status_code == 200:
            chunk = next(r.iter_content(512), b"")
            return b"#EXTM3U" in chunk or b"#EXT-X" in chunk
    except Exception:
        pass
    return False


def _classify_qualities(urls: list[str]) -> dict:
    """
    Try to detect FHD/HD/SD variants inside an m3u8 master playlist.
    Returns dict like {"FHD": url, "HD": url, "SD": url} — may have fewer keys.
    """
    qualities = {}
    for url in urls:
        try:
            r = requests.get(url, headers=BROWSER_HEADERS, timeout=8)
            text = r.text
            if "#EXT-X-STREAM-INF" not in text:
                # Not a master playlist — treat as single quality
                qualities["HD"] = url
                return qualities

            base = url.rsplit("/", 1)[0] + "/"
            streams_info = []
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if line.startswith("#EXT-X-STREAM-INF"):
                    bw = re.search(r"BANDWIDTH=(\d+)", line)
                    res = re.search(r"RESOLUTION=(\d+x\d+)", line)
                    next_url = lines[i + 1].strip() if i + 1 < len(lines) else ""
                    if next_url and not next_url.startswith("http"):
                        next_url = base + next_url
                    if next_url:
                        bw_val = int(bw.group(1)) if bw else 0
                        res_str = res.group(1) if res else ""
                        streams_info.append((bw_val, res_str, next_url))

            streams_info.sort(key=lambda x: x[0])
            n = len(streams_info)
            if n == 1:
                qualities["HD"] = streams_info[0][2]
            elif n == 2:
                qualities["SD"] = streams_info[0][2]
                qualities["FHD"] = streams_info[1][2]
            elif n >= 3:
                qualities["SD"] = streams_info[0][2]
                qualities["HD"] = streams_info[n // 2][2]
                qualities["FHD"] = streams_info[-1][2]

            return qualities
        except Exception:
            continue

    return qualities


def extract_streams(channel_id: str) -> dict:
    """
    Main extraction function. Returns:
    {
      "raw": [list of m3u8 URLs found],
      "qualities": {"FHD": url, "HD": url, "SD": url}   # ≥1 key
    }
    Uses cache; re-extracts after CACHE_TTL seconds.
    """
    with _cache_lock:
        cached = _cache.get(channel_id)
        if cached and (time.time() - cached["ts"]) < CACHE_TTL:
            return cached["data"]

    ch = CHANNELS_BY_ID.get(channel_id)
    if not ch:
        return {"raw": [], "qualities": {}}

    raw_urls: list[str] = []

    # 1. Prefer hard-coded direct m3u8 if provided
    if ch.get("direct_m3u8"):
        raw_urls.append(ch["direct_m3u8"])

    # 2. Try each player source
    for player_url in ch.get("players", []):
        try:
            parsed = urlparse(player_url)
            if parsed.hostname in EMBEDTV_HOSTS or "embedtv" in parsed.hostname:
                found = _extract_from_embedtv(player_url)
            else:
                found = _extract_from_player_page(player_url)
            raw_urls += found
            if raw_urls:
                break   # stop at first source that yields results
        except Exception as e:
            log.warning("Player extraction failed (%s): %s", player_url, e)

    # deduplicate
    seen, raw_dedup = set(), []
    for u in raw_urls:
        if u not in seen:
            seen.add(u)
            raw_dedup.append(u)

    # 3. Probe and classify
    qualities = {}
    for url in raw_dedup:
        if _probe_m3u8(url):
            qualities = _classify_qualities([url])
            if qualities:
                break

    data = {"raw": raw_dedup, "qualities": qualities}

    with _cache_lock:
        _cache[channel_id] = {"ts": time.time(), "data": data}

    log.info("extract_streams(%s) → raw=%d qualities=%s", channel_id, len(raw_dedup), list(qualities.keys()))
    return data


def _get_best_m3u8(channel_id: str, quality: str = "HD") -> str | None:
    """Return the m3u8 URL for the requested quality (fallback to any available)."""
    data = extract_streams(channel_id)
    qs = data.get("qualities", {})
    if not qs:
        return None
    order = [quality, "FHD", "HD", "SD"]
    for q in order:
        if q in qs:
            return qs[q]
    return list(qs.values())[0]


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Redirect to the dashboard."""
    return redirect("/dashboard")


@app.route("/dashboard")
def dashboard():
    """Serve the HTML dashboard."""
    from dashboard import render_dashboard
    return render_dashboard()


@app.route("/api/channels")
def api_channels():
    """List all channels with metadata."""
    result = []
    for ch in CHANNELS:
        result.append({
            "id": ch["id"],
            "name": ch["name"],
            "category": ch["category"],
            "logo": ch["logo"],
            "has_direct": bool(ch.get("direct_m3u8")),
        })
    return jsonify(result)


@app.route("/api/channel/<channel_id>")
def api_channel_info(channel_id):
    """Return extracted stream info for a channel."""
    ch = CHANNELS_BY_ID.get(channel_id)
    if not ch:
        return jsonify({"error": "channel not found"}), 404

    data = extract_streams(channel_id)
    base = request.host_url.rstrip("/")

    quality_links = {}
    for q, url in data["qualities"].items():
        quality_links[q] = f"{base}/stream/{channel_id}/{q.lower()}.m3u8"

    # Always expose at least a generic fixed link
    if not quality_links:
        quality_links["HD"] = f"{base}/stream/{channel_id}/hd.m3u8"

    return jsonify({
        "id": channel_id,
        "name": ch["name"],
        "category": ch["category"],
        "logo": ch["logo"],
        "fixed_links": quality_links,
        "raw_count": len(data["raw"]),
        "cached": channel_id in _cache,
    })


@app.route("/api/channel/<channel_id>/refresh")
def api_refresh(channel_id):
    """Force cache invalidation for a channel."""
    with _cache_lock:
        _cache.pop(channel_id, None)
    data = extract_streams(channel_id)
    return jsonify({"status": "refreshed", "qualities": list(data["qualities"].keys())})


@app.route("/stream/<channel_id>/<quality>.m3u8")
def stream_fixed(channel_id, quality):
    """
    FIXED URL endpoint — this URL never changes.
    Internally resolves to the current m3u8 and proxies it.
    quality: fhd | hd | sd  (case-insensitive)
    """
    q_map = {"fhd": "FHD", "hd": "HD", "sd": "SD"}
    q_key = q_map.get(quality.lower(), "HD")

    m3u8_url = _get_best_m3u8(channel_id, q_key)
    if not m3u8_url:
        return Response("# No stream available\n", status=503, mimetype="application/vnd.apple.mpegurl")

    # Proxy the m3u8 content, rewriting segment URLs to go through /seg/
    try:
        r = requests.get(m3u8_url, headers=BROWSER_HEADERS, timeout=10)
        r.raise_for_status()
    except Exception as e:
        log.error("Failed to fetch m3u8 for %s: %s", channel_id, e)
        return Response("# Upstream error\n", status=502, mimetype="application/vnd.apple.mpegurl")

    content = _rewrite_m3u8(r.text, m3u8_url, channel_id)
    return Response(
        content,
        mimetype="application/vnd.apple.mpegurl",
        headers={
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.route("/stream/<channel_id>/direct")
def stream_direct_redirect(channel_id):
    """Redirect directly to the upstream m3u8 (for VLC use without rewriting)."""
    m3u8_url = _get_best_m3u8(channel_id, "HD")
    if not m3u8_url:
        return Response("No stream", status=503)
    return redirect(m3u8_url)


def _rewrite_m3u8(content: str, base_url: str, channel_id: str) -> str:
    """
    Rewrite relative segment paths and sub-playlist URLs
    so they point through /seg/<channel_id>/<encoded_url>.
    """
    base = base_url.rsplit("/", 1)[0] + "/"
    lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            # Rewrite URI= inside tags like #EXT-X-KEY, #EXT-X-MAP
            line = re.sub(
                r'URI="([^"]+)"',
                lambda m: f'URI="{_proxy_seg_url(m.group(1), base, channel_id)}"',
                line,
            )
            lines.append(line)
        elif stripped and not stripped.startswith("#"):
            # Segment or sub-playlist URL
            lines.append(_proxy_seg_url(stripped, base, channel_id))
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def _proxy_seg_url(url: str, base: str, channel_id: str) -> str:
    if not url.startswith("http"):
        url = urljoin(base, url)
    encoded = quote(url, safe="")
    return f"/seg/{channel_id}/{encoded}"


@app.route("/seg/<channel_id>/<path:encoded_url>")
def proxy_segment(channel_id, encoded_url):
    """Proxy a TS segment or sub-playlist, preserving upstream headers."""
    from urllib.parse import unquote
    real_url = unquote(encoded_url)

    hdrs = {**BROWSER_HEADERS, "Referer": "https://tvonlinehd.com.br/"}

    try:
        upstream = requests.get(real_url, headers=hdrs, stream=True, timeout=15)
        content_type = upstream.headers.get("Content-Type", "video/MP2T")

        def generate():
            for chunk in upstream.iter_content(PROXY_CHUNK):
                yield chunk

        return Response(
            stream_with_context(generate()),
            status=upstream.status_code,
            content_type=content_type,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache",
            },
        )
    except Exception as e:
        log.error("Segment proxy error (%s): %s", real_url, e)
        return Response("", status=502)


@app.route("/playlist.m3u")
def full_playlist():
    """
    Generate a complete M3U playlist with all channels (HD quality).
    Compatible with VLC, Kodi, TiviMate, etc.
    """
    base = request.host_url.rstrip("/")
    lines = ["#EXTM3U"]
    for ch in CHANNELS:
        lines.append(
            f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-name="{ch["name"]}" '
            f'tvg-logo="{ch["logo"]}" group-title="{ch["category"]}",{ch["name"]}'
        )
        lines.append(f'{base}/stream/{ch["id"]}/hd.m3u8')
    return Response(
        "\n".join(lines) + "\n",
        mimetype="application/x-mpegURL",
        headers={"Content-Disposition": 'attachment; filename="tvproxy.m3u"'},
    )


@app.route("/playlist_fhd.m3u")
def full_playlist_fhd():
    base = request.host_url.rstrip("/")
    lines = ["#EXTM3U"]
    for ch in CHANNELS:
        lines.append(
            f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-name="{ch["name"]}" '
            f'tvg-logo="{ch["logo"]}" group-title="{ch["category"]}",{ch["name"]}'
        )
        lines.append(f'{base}/stream/{ch["id"]}/fhd.m3u8')
    return Response("\n".join(lines) + "\n", mimetype="application/x-mpegURL")


@app.route("/playlist_sd.m3u")
def full_playlist_sd():
    base = request.host_url.rstrip("/")
    lines = ["#EXTM3U"]
    for ch in CHANNELS:
        lines.append(
            f'#EXTINF:-1 tvg-id="{ch["id"]}" tvg-name="{ch["name"]}" '
            f'tvg-logo="{ch["logo"]}" group-title="{ch["category"]}",{ch["name"]}'
        )
        lines.append(f'{base}/stream/{ch["id"]}/sd.m3u8')
    return Response("\n".join(lines) + "\n", mimetype="application/x-mpegURL")


@app.route("/api/cache")
def api_cache_status():
    """Show current cache status."""
    with _cache_lock:
        status = {
            cid: {
                "age_seconds": int(time.time() - v["ts"]),
                "qualities": list(v["data"]["qualities"].keys()),
                "raw_count": len(v["data"]["raw"]),
            }
            for cid, v in _cache.items()
        }
    return jsonify(status)


@app.route("/api/cache/clear")
def api_cache_clear():
    with _cache_lock:
        _cache.clear()
    return jsonify({"status": "cleared"})


# ─── BACKGROUND CACHE WARMER ─────────────────────────────────────────────────

def _warm_cache():
    """Pre-extract streams for all channels at startup (non-blocking)."""
    log.info("Cache warmer started — %d channels", len(CHANNELS))
    for ch in CHANNELS:
        try:
            extract_streams(ch["id"])
            time.sleep(1)   # be polite
        except Exception as e:
            log.warning("Warmer error on %s: %s", ch["id"], e)
    log.info("Cache warmer done")


# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TVProxy — Brazilian TV streaming proxy")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--no-warm", action="store_true", help="Skip cache pre-warming")
    args = parser.parse_args()

    if not args.no_warm:
        t = threading.Thread(target=_warm_cache, daemon=True)
        t.start()

    log.info("Starting TVProxy on %s:%d", args.host, args.port)
    app.run(host=args.host, port=args.port, threaded=True)
