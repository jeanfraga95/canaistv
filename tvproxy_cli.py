#!/usr/bin/env python3
"""
tvproxy-cli — Command line interface for TVProxy
Usage:
  tvproxy list [<filter>]
  tvproxy stream <channel_id> [--quality=HD]
  tvproxy refresh <channel_id>
  tvproxy vlc <channel_id> [--quality=HD]
"""

import sys
import argparse
import requests
import subprocess

BASE_URL = "http://127.0.0.1:5000"

ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "cyan": "\033[96m",
    "gray": "\033[90m",
}

QUALITY_COLOR = {
    "FHD": ANSI["green"],
    "HD": ANSI["blue"],
    "SD": ANSI["yellow"],
}


def c(color, text):
    return f"{ANSI.get(color,'')}{text}{ANSI['reset']}"


def cmd_list(args):
    try:
        channels = requests.get(f"{BASE_URL}/api/channels", timeout=5).json()
    except Exception as e:
        print(c("red", f"Erro: {e}"))
        sys.exit(1)

    filt = args.filter.lower() if args.filter else ""
    cat_filt = args.category.lower() if args.category else ""

    print(c("bold", f"\n{'ID':<24} {'NOME':<35} {'CATEGORIA':<20}"))
    print("─" * 80)

    count = 0
    for ch in channels:
        if filt and filt not in ch["id"].lower() and filt not in ch["name"].lower():
            continue
        if cat_filt and cat_filt not in ch["category"].lower():
            continue
        direct = c("green", "●") if ch["has_direct"] else c("gray", "○")
        print(f"{direct} {c('cyan', ch['id']):<33} {ch['name']:<35} {c('gray', ch['category'])}")
        count += 1

    print(c("gray", f"\n{count} canais"))


def cmd_stream(args):
    quality = args.quality.upper()
    url = f"{BASE_URL}/stream/{args.channel_id}/{quality.lower()}.m3u8"
    print(c("green", f"🔗 Link fixo ({quality}):"))
    print(url)


def cmd_info(args):
    try:
        data = requests.get(f"{BASE_URL}/api/channel/{args.channel_id}", timeout=30).json()
    except Exception as e:
        print(c("red", f"Erro: {e}"))
        sys.exit(1)

    if "error" in data:
        print(c("red", f"Canal não encontrado: {args.channel_id}"))
        sys.exit(1)

    print(c("bold", f"\n{data['name']}"))
    print(c("gray", f"ID: {data['id']}  |  Categoria: {data['category']}"))
    print(c("gray", f"Raw streams encontrados: {data.get('raw_count', 0)}"))
    print()
    links = data.get("fixed_links", {})
    if not links:
        print(c("red", "Nenhum stream disponível"))
        return
    for q, url in sorted(links.items()):
        col = QUALITY_COLOR.get(q, "")
        print(f"  {col}{q}{ANSI['reset']}  →  {url}")
    print()


def cmd_refresh(args):
    print(c("yellow", f"Reextraindo {args.channel_id}..."))
    try:
        data = requests.get(
            f"{BASE_URL}/api/channel/{args.channel_id}/refresh", timeout=60
        ).json()
        print(c("green", f"✓ Concluído. Qualidades: {', '.join(data.get('qualities', []))}"))
    except Exception as e:
        print(c("red", f"Erro: {e}"))
        sys.exit(1)


def cmd_vlc(args):
    quality = args.quality.upper()
    url = f"{BASE_URL}/stream/{args.channel_id}/{quality.lower()}.m3u8"
    print(c("green", f"Abrindo no VLC: {url}"))
    try:
        subprocess.Popen(
            ["vlc", "--http-reconnect", "--network-caching=3000", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        print(c("red", "VLC não encontrado. Copie o link manualmente:"))
        print(url)


def cmd_playlist(args):
    quality = (args.quality or "hd").lower()
    url = f"{BASE_URL}/playlist{'_' + quality if quality != 'hd' else ''}.m3u"
    print(c("green", f"URL da playlist M3U ({quality.upper()}):"))
    print(url)


def main():
    parser = argparse.ArgumentParser(
        prog="tvproxy",
        description="TVProxy CLI — acesse canais diretamente do terminal",
    )
    sub = parser.add_subparsers(dest="command")

    # list
    p_list = sub.add_parser("list", help="Listar canais")
    p_list.add_argument("filter", nargs="?", help="Filtro por nome ou ID")
    p_list.add_argument("-c", "--category", help="Filtrar por categoria")

    # stream
    p_stream = sub.add_parser("stream", help="Mostrar link fixo do canal")
    p_stream.add_argument("channel_id")
    p_stream.add_argument("-q", "--quality", default="HD", choices=["FHD","HD","SD"])

    # info
    p_info = sub.add_parser("info", help="Info detalhada + links de qualidade")
    p_info.add_argument("channel_id")

    # refresh
    p_ref = sub.add_parser("refresh", help="Forçar reextração do m3u8")
    p_ref.add_argument("channel_id")

    # vlc
    p_vlc = sub.add_parser("vlc", help="Abrir canal no VLC")
    p_vlc.add_argument("channel_id")
    p_vlc.add_argument("-q", "--quality", default="HD", choices=["FHD","HD","SD"])

    # playlist
    p_pl = sub.add_parser("playlist", help="URL da playlist M3U completa")
    p_pl.add_argument("-q", "--quality", default="hd", choices=["fhd","hd","sd"])

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "list": cmd_list,
        "stream": cmd_stream,
        "info": cmd_info,
        "refresh": cmd_refresh,
        "vlc": cmd_vlc,
        "playlist": cmd_playlist,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
