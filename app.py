#!/usr/bin/env python3
"""
tvproxy - Flask streaming proxy for tvonlinehd.com.br
Compatible with Python 3.8+
"""
from __future__ import annotations

import re
import time
import logging
import threading
import requests
from urllib.parse import urljoin, urlparse, quote, unquote
from flask import Flask, Response, request, jsonify, redirect, stream_with_context
from channels import CHANNELS, CHANNELS_BY_ID

PORT = 5000
HOST = "0.0.0.0"
CACHE_TTL = 300        # 5 minutes
EXTRACT_TIMEOUT = 12
PROXY_CHUNK = 8192

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

_cache = {}
_cache_lock = threading.Lock()

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


# ─── EXTRACTION HELPERS ──────────────────────────────────────────────────────

def _find_m3u8_in_text(text):
    """Find all .m3u8 URLs in a block of text."""
    pattern = r'https?://[^\s"\'<>\{\}\\]+\.m3u8[^\s"\'<>\{\}\\]*'
    found = re.findall(pattern, text)
    seen = set()
    result = []
    for u in found:
        u = u.strip(".,;)")
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


def _fetch(url, extra_headers=None, timeout=10, referer=None):
    """Fetch URL, return text or None."""
    hdrs = dict(BROWSER_HEADERS)
    if referer:
        hdrs["Referer"] = referer
    if extra_headers:
        hdrs.update(extra_headers)
    try:
        r = requests.get(url, headers=hdrs, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception as e:
        log.debug("fetch(%s) -> %s", url, e)
        return None


def _extract_m3u8_from_page(page_url):
    """
    Generic extraction: fetch a page and look for m3u8 URLs.
    Also follows iframes one level deep.
    """
    html = _fetch(page_url, timeout=EXTRACT_TIMEOUT)
    if not html:
        return []

    streams = _find_m3u8_in_text(html)

    # Also look inside JS variables for common patterns
    js_patterns = [
        r'["\']?(https?://[^\s"\'<>,;]+\.m3u8[^\s"\'<>,;]*)["\']?',
        r'source["\s]*:["\s]*(https?://[^\s"\'<>,;]+\.m3u8[^\s"\'<>,;]*)',
        r'file["\s]*:["\s]*(https?://[^\s"\'<>,;]+\.m3u8[^\s"\'<>,;]*)',
        r'hls["\s]*:["\s]*(https?://[^\s"\'<>,;]+\.m3u8[^\s"\'<>,;]*)',
        r'stream["\s]*:["\s]*(https?://[^\s"\'<>,;]+\.m3u8[^\s"\'<>,;]*)',
    ]
    for pat in js_patterns:
        for m in re.finditer(pat, html, re.I):
            u = m.group(1).strip()
            if u not in streams:
                streams.append(u)

    # Follow iframes (one level)
    iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I)
    for iframe_src in iframes[:4]:  # max 4 iframes
        if not iframe_src.startswith("http"):
            iframe_src = urljoin(page_url, iframe_src)
        sub = _fetch(iframe_src, referer=page_url, timeout=EXTRACT_TIMEOUT)
        if sub:
            streams += _find_m3u8_in_text(sub)
            for pat in js_patterns:
                for m in re.finditer(pat, sub, re.I):
                    u = m.group(1).strip()
                    if u not in streams:
                        streams.append(u)

    # Deduplicate
    seen = set()
    result = []
    for u in streams:
        if "m3u8" in u.lower() and u not in seen:
            seen.add(u)
            result.append(u)
    return result


def _extract_from_sinalpublico(channel_id_param):
    """
    sinalpublicoetv.vercel.app returns a JSON/JS config with the stream URL.
    Try to get it from the API endpoint pattern.
    """
    base_url = "https://sinalpublicoetv.vercel.app/?id=" + channel_id_param
    html = _fetch(base_url, timeout=EXTRACT_TIMEOUT)
    if not html:
        return []
    return _find_m3u8_in_text(html)


def _extract_from_rdcanais(channel_slug):
    """rdcanais.com/<slug> - fetch and look for m3u8."""
    url = "https://rdcanais.com/" + channel_slug
    return _extract_m3u8_from_page(url)


def _extract_from_redecanaistv(canal_param):
    """redecanaistv.be player."""
    url = "https://redecanaistv.be/player3/ch.php?canal=" + canal_param
    return _extract_m3u8_from_page(url)


def _extract_from_megacanais(inner_m3u8_url):
    """
    megacanaisonline.space/tv2.php?canal=<url> just wraps a direct m3u8.
    Extract the canal= param and return it directly.
    """
    m = re.search(r'[?&]canal=([^&]+)', inner_m3u8_url)
    if m:
        candidate = unquote(m.group(1))
        if ".m3u8" in candidate:
            return [candidate]
    return _extract_m3u8_from_page(inner_m3u8_url)


def _smart_extract(player_url):
    """
    Route extraction to the best method based on the player URL.
    Returns list of m3u8 URLs.
    """
    parsed = urlparse(player_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    query = parsed.query

    # Direct m3u8 URL
    if player_url.endswith(".m3u8") or ".m3u8?" in player_url:
        return [player_url]

    # megacanaisonline wrapper — extract canal= param
    if "megacanaisonline" in hostname:
        return _extract_from_megacanais(player_url)

    # sinalpublicoetv
    if "sinalpublico" in hostname:
        m = re.search(r'[?&]id=([^&]+)', query)
        if m:
            return _extract_from_sinalpublico(m.group(1))
        return _extract_m3u8_from_page(player_url)

    # rdcanais
    if "rdcanais" in hostname:
        slug = path.strip("/")
        if slug:
            return _extract_from_rdcanais(slug)
        return _extract_m3u8_from_page(player_url)

    # redecanaistv
    if "redecanaistv" in hostname:
        m = re.search(r'canal=([^&]+)', query)
        if m:
            return _extract_from_redecanaistv(m.group(1))
        return _extract_m3u8_from_page(player_url)

    # joel.embedtv.live and other embedtv hosts
    if "embedtv" in hostname or "joel" in hostname:
        return _extract_m3u8_from_page(player_url)

    # Generic fallback
    return _extract_m3u8_from_page(player_url)


def _probe_m3u8(url):
    """Return True if URL is a valid HLS stream."""
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=8, stream=True)
        if r.status_code == 200:
            chunk = next(r.iter_content(512), b"")
            return b"#EXTM3U" in chunk or b"#EXT-X" in chunk
    except Exception:
        pass
    return False


def _classify_qualities(url):
    """
    Fetch a master playlist and return dict of quality -> URL.
    If not a master playlist, returns {"HD": url}.
    """
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=8)
        text = r.text
        if "#EXT-X-STREAM-INF" not in text:
            return {"HD": url}

        base = url.rsplit("/", 1)[0] + "/"
        streams_info = []
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF"):
                bw = re.search(r"BANDWIDTH=(\d+)", line)
                next_url = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if next_url and not next_url.startswith("http"):
                    next_url = base + next_url
                if next_url:
                    bw_val = int(bw.group(1)) if bw else 0
                    streams_info.append((bw_val, next_url))

        streams_info.sort(key=lambda x: x[0])
        n = len(streams_info)
        if n == 0:
            return {"HD": url}
        if n == 1:
            return {"HD": streams_info[0][1]}
        if n == 2:
            return {"SD": streams_info[0][1], "FHD": streams_info[1][1]}
        return {
            "SD": streams_info[0][1],
            "HD": streams_info[n // 2][1],
            "FHD": streams_info[-1][1],
        }
    except Exception:
        return {"HD": url}


# ─── MAIN EXTRACTION ─────────────────────────────────────────────────────────

def extract_streams(channel_id):
    """
    Try all player sources for a channel, aggregate m3u8 URLs found,
    probe them, classify qualities.
    Returns: {"raw": [...], "qualities": {"HD": url, ...}}
    """
    with _cache_lock:
        cached = _cache.get(channel_id)
        if cached and (time.time() - cached["ts"]) < CACHE_TTL:
            return cached["data"]

    ch = CHANNELS_BY_ID.get(channel_id)
    if not ch:
        return {"raw": [], "qualities": {}}

    all_raw = []

    # 1. Direct m3u8 has highest priority
    if ch.get("direct_m3u8"):
        all_raw.append(ch["direct_m3u8"])

    # 2. Try ALL player sources (not just the first)
    for player_url in ch.get("players", []):
        try:
            found = _smart_extract(player_url)
            for u in found:
                if u not in all_raw:
                    all_raw.append(u)
        except Exception as e:
            log.debug("player(%s) error: %s", player_url, e)

    # 3. Probe each URL and pick the first valid one
    qualities = {}
    for url in all_raw:
        if _probe_m3u8(url):
            qualities = _classify_qualities(url)
            if qualities:
                break

    data = {"raw": all_raw, "qualities": qualities}

    with _cache_lock:
        _cache[channel_id] = {"ts": time.time(), "data": data}

    log.info(
        "extract_streams(%s) -> raw=%d qualities=%s",
        channel_id, len(all_raw), list(qualities.keys()),
    )
    return data


def _get_best_m3u8(channel_id, quality="HD"):
    data = extract_streams(channel_id)
    qs = data.get("qualities", {})
    if not qs:
        return None
    for q in [quality, "FHD", "HD", "SD"]:
        if q in qs:
            return qs[q]
    return list(qs.values())[0]


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect("/dashboard")


@app.route("/dashboard")
def dashboard():
    from dashboard import render_dashboard
    return render_dashboard()


@app.route("/api/channels")
def api_channels():
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
    ch = CHANNELS_BY_ID.get(channel_id)
    if not ch:
        return jsonify({"error": "channel not found"}), 404

    data = extract_streams(channel_id)
    base = request.host_url.rstrip("/")

    quality_links = {}
    for q in data["qualities"]:
        quality_links[q] = "{}/stream/{}/{}.m3u8".format(base, channel_id, q.lower())

    if not quality_links:
        quality_links["HD"] = "{}/stream/{}/hd.m3u8".format(base, channel_id)

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
    with _cache_lock:
        _cache.pop(channel_id, None)
    data = extract_streams(channel_id)
    return jsonify({"status": "refreshed", "qualities": list(data["qualities"].keys())})


@app.route("/stream/<channel_id>/<quality>.m3u8")
def stream_fixed(channel_id, quality):
    """Fixed URL — resolves to current m3u8 and proxies content."""
    q_map = {"fhd": "FHD", "hd": "HD", "sd": "SD"}
    q_key = q_map.get(quality.lower(), "HD")

    m3u8_url = _get_best_m3u8(channel_id, q_key)
    if not m3u8_url:
        return Response(
            "# No stream available for: " + channel_id + "\n",
            status=503,
            mimetype="application/vnd.apple.mpegurl",
        )

    try:
        r = requests.get(m3u8_url, headers=BROWSER_HEADERS, timeout=10)
        r.raise_for_status()
    except Exception as e:
        log.error("Failed to fetch m3u8 for %s: %s", channel_id, e)
        # Invalidate cache so next request tries fresh
        with _cache_lock:
            _cache.pop(channel_id, None)
        return Response("# Upstream error\n", status=502, mimetype="application/vnd.apple.mpegurl")

    content = _rewrite_m3u8(r.text, m3u8_url, channel_id)
    return Response(
        content,
        mimetype="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-cache", "Access-Control-Allow-Origin": "*"},
    )


@app.route("/stream/<channel_id>/direct")
def stream_direct(channel_id):
    """Redirect directly to upstream m3u8 (no segment proxying)."""
    url = _get_best_m3u8(channel_id, "HD")
    if not url:
        return Response("No stream", status=503)
    return redirect(url)


def _rewrite_m3u8(content, base_url, channel_id):
    base = base_url.rsplit("/", 1)[0] + "/"
    lines = []
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("#"):
            # Rewrite URI= attributes inside tags (e.g. EXT-X-KEY)
            line = re.sub(
                r'URI="([^"]+)"',
                lambda m: 'URI="' + _seg_url(m.group(1), base, channel_id) + '"',
                line,
            )
            lines.append(line)
        elif s and not s.startswith("#"):
            lines.append(_seg_url(s, base, channel_id))
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def _seg_url(url, base, channel_id):
    if not url.startswith("http"):
        url = urljoin(base, url)
    return "/seg/{}/{}".format(channel_id, quote(url, safe=""))


@app.route("/seg/<channel_id>/<path:encoded_url>")
def proxy_segment(channel_id, encoded_url):
    """Proxy a TS segment or sub-playlist."""
    real_url = unquote(encoded_url)
    hdrs = dict(BROWSER_HEADERS)
    hdrs["Referer"] = "https://tvonlinehd.com.br/"

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
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"},
        )
    except Exception as e:
        log.error("Segment proxy error (%s): %s", real_url, e)
        return Response("", status=502)


@app.route("/playlist.m3u")
def full_playlist():
    base = request.host_url.rstrip("/")
    lines = ["#EXTM3U"]
    for ch in CHANNELS:
        lines.append(
            '#EXTINF:-1 tvg-id="{}" tvg-name="{}" tvg-logo="{}" group-title="{}",{}'.format(
                ch["id"], ch["name"], ch["logo"], ch["category"], ch["name"]
            )
        )
        lines.append("{}/stream/{}/hd.m3u8".format(base, ch["id"]))
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
            '#EXTINF:-1 tvg-id="{}" tvg-name="{}" tvg-logo="{}" group-title="{}",{}'.format(
                ch["id"], ch["name"], ch["logo"], ch["category"], ch["name"]
            )
        )
        lines.append("{}/stream/{}/fhd.m3u8".format(base, ch["id"]))
    return Response("\n".join(lines) + "\n", mimetype="application/x-mpegURL")


@app.route("/playlist_sd.m3u")
def full_playlist_sd():
    base = request.host_url.rstrip("/")
    lines = ["#EXTM3U"]
    for ch in CHANNELS:
        lines.append(
            '#EXTINF:-1 tvg-id="{}" tvg-name="{}" tvg-logo="{}" group-title="{}",{}'.format(
                ch["id"], ch["name"], ch["logo"], ch["category"], ch["name"]
            )
        )
        lines.append("{}/stream/{}/sd.m3u8".format(base, ch["id"]))
    return Response("\n".join(lines) + "\n", mimetype="application/x-mpegURL")


@app.route("/api/cache")
def api_cache_status():
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


# ─── CACHE WARMER ────────────────────────────────────────────────────────────

def _warm_cache():
    log.info("Cache warmer started -- %d channels", len(CHANNELS))
    for ch in CHANNELS:
        try:
            extract_streams(ch["id"])
            time.sleep(0.8)
        except Exception as e:
            log.warning("Warmer error on %s: %s", ch["id"], e)
    log.info("Cache warmer done")


# ─── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TVProxy")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--no-warm", action="store_true")
    args = parser.parse_args()

    if not args.no_warm:
        threading.Thread(target=_warm_cache, daemon=True).start()

    log.info("Starting TVProxy on %s:%d", args.host, args.port)
    app.run(host=args.host, port=args.port, threaded=True)
