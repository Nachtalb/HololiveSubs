#!/usr/bin/env python3
"""Hololive Zone: collects subscriber counts + live streams and serves the site."""

import hashlib
import json
import logging
import os
import random
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from email.utils import format_datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent
WWW = BASE / "www"
DATA = Path(os.environ.get("DATA_DIR", BASE / "data"))
YT_KEY = os.environ.get("YOUTUBE_KEY", "")
SITE = os.environ.get("SITE_URL", "https://holo.naa.gg").rstrip("/")
PORT = int(os.environ.get("PORT", "8080"))
LIVE_INTERVAL = 15 * 60  # full stats every 2nd run
RETENTION = 7 * 24 * 3600

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
YT_COOKIE = "CONSENT=YES+926; SOCS=CAESEwgDEgk1NjQ0NjAzMDMaAmVuIAEaBgiA1P6nBg"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("holozone")


def fetch(url: str, **headers: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **headers})
    with urllib.request.urlopen(req, timeout=20) as res:
        return res.read()


def write(path: Path, data: str | bytes) -> None:
    """Atomic write so the web server never serves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data.encode() if isinstance(data, str) else data)
    tmp.replace(path)


def now() -> datetime:
    return datetime.now(UTC)


# --- Data sources ----------------------------------------------------------------------------------------------------


def youtube_channels(ids: list[str]) -> dict[str, dict]:
    result = {}
    for i in range(0, len(ids), 50):
        query = urllib.parse.urlencode({"part": "snippet,statistics", "id": ",".join(ids[i : i + 50]), "key": YT_KEY})
        result |= {
            item["id"]: item
            for item in json.loads(fetch(f"https://www.googleapis.com/youtube/v3/channels?{query}"))["items"]
        }
    return result


def bilibili_card(uid: str) -> dict | None:
    try:
        return json.loads(fetch(f"https://api.bilibili.com/x/web-interface/card?mid={uid}"))["data"]
    except Exception as error:
        log.warning("bilibili %s: %s", uid, error)


def dig(data, *keys, default=None):
    for key in keys:
        try:
            data = data[key]
        except (KeyError, IndexError, TypeError):
            return default
    return data


def parse_live(html: str) -> dict | None:
    marker = "var ytInitialPlayerResponse = "
    if (start := html.find(marker)) == -1:
        return None
    try:
        player, _ = json.JSONDecoder().raw_decode(html, start + len(marker))
    except ValueError:
        return None
    details = player.get("videoDetails") or {}
    if not details.get("videoId") or not (details.get("isLive") or details.get("isUpcoming")):
        return None
    start_time = int(
        dig(
            player,
            "playabilityStatus",
            "liveStreamability",
            "liveStreamabilityRenderer",
            "offlineSlate",
            "liveStreamOfflineSlateRenderer",
            "scheduledStartTime",
            default=0,  # 0 == already live
        )
    )
    # Skip far-future streams and long-overdue "upcoming" ones (permanent free-chat waiting rooms)
    if not -6 * 3600 < start_time - time.time() < 2 * 24 * 3600 and not details.get("isLive"):
        return None
    video_id = details["videoId"]
    return {
        "id": video_id,
        "title": details.get("title", ""),
        "start": start_time,
        "description": details.get("shortDescription", ""),
        "thumbnail": dig(
            details,
            "thumbnail",
            "thumbnails",
            -1,
            "url",
            default=f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        ),
    }


def live_video(member: dict) -> dict | None:
    if not member.get("youtube") or member.get("retired"):
        return None
    try:
        return parse_live(fetch(f"https://www.youtube.com/channel/{member['youtube']}/live", Cookie=YT_COOKIE).decode())
    except Exception as error:
        log.warning("[%s] live check failed: %s", member["name"], error)


# --- Images ----------------------------------------------------------------------------------------------------------


def low_poly(image: Image.Image, cells: int = 10, seed: str = "") -> Image.Image:
    """Jittered-grid triangulation filled with the colour under each triangle's centroid."""
    rng = random.Random(seed)
    w, h = image.size
    sx, sy = w / cells, h / cells
    jitter = lambda i, n, s: i * s + (rng.uniform(-0.4, 0.4) * s if 0 < i < n else 0)
    points = [[(jitter(x, cells, sx), jitter(y, cells, sy)) for x in range(cells + 1)] for y in range(cells + 1)]
    out = Image.new("RGB", image.size)
    draw = ImageDraw.Draw(out)
    for y in range(cells):
        for x in range(cells):
            a, b, c, d = points[y][x], points[y][x + 1], points[y + 1][x + 1], points[y + 1][x]
            for tri in ((a, b, c), (a, c, d)) if rng.random() < 0.5 else ((a, b, d), (b, c, d)):
                cx = min(w - 1, max(0, sum(p[0] for p in tri) / 3))
                cy = min(h - 1, max(0, sum(p[1] for p in tri) / 3))
                draw.polygon(tri, fill=image.getpixel((int(cx), int(cy))))
    return out


def profile_images(url: str) -> tuple[str, str | None]:
    """Cache the avatar locally and derive its low-poly background. Returns site-relative paths."""
    stem = hashlib.md5(url.encode()).hexdigest()[:16]
    image, background = DATA / "profile-images" / f"{stem}.jpg", DATA / "profile-images" / f"{stem}_background.jpg"
    try:
        if not image.is_file():
            write(image, fetch(url))
        if not background.is_file():
            src = Image.open(image).convert("RGB").resize((300, 300))
            buf = BytesIO()
            low_poly(src, seed=stem).save(buf, "JPEG", quality=85)
            write(background, buf.getvalue())
    except Exception as error:
        log.warning("image %s: %s", url, error)
        return url, None
    return f"profile-images/{image.name}", f"profile-images/{background.name}"


# --- Stats -----------------------------------------------------------------------------------------------------------


def load_stats() -> dict | None:
    try:
        return json.loads((DATA / "stats.json").read_text())
    except (OSError, ValueError):
        return None


def update_full() -> dict:
    log.info("Full update")
    config = json.loads((BASE / "talents.json").read_text())
    talents = config["talents"]
    channels = youtube_channels([t["youtube"] for t in talents if t["youtube"]])

    def collect(talent: dict) -> dict:
        talent = dict(talent, image=None, background_image=None, video=None)
        avatar = None
        if channel := channels.get(talent["youtube"]):
            if not channel["statistics"].get("hiddenSubscriberCount"):
                talent["youtube_subs"] = int(channel["statistics"]["subscriberCount"])
            thumbs = channel["snippet"]["thumbnails"]
            avatar = (thumbs.get("high") or thumbs.get("medium") or thumbs["default"])["url"]
        if talent["bilibili"] and (card := bilibili_card(talent["bilibili"])):
            talent["bilibili_subs"] = card["follower"]
            avatar = avatar or card["card"]["face"].replace("http://", "https://")
        if avatar:
            talent["image"], talent["background_image"] = profile_images(avatar)
        talent["video"] = live_video(talent)
        return talent

    with ThreadPoolExecutor(8) as pool:
        talents = list(pool.map(collect, talents))

    groups = {
        key: dict(group, members=[]) for key, group in sorted(config["groups"].items(), key=lambda g: g[1]["order"])
    }
    for talent in sorted(talents, key=lambda t: t.get("youtube_subs") or t.get("bilibili_subs") or 0, reverse=True):
        groups[talent.get("group", "talents")]["members"].append(talent)

    stamp = now().isoformat(timespec="minutes")
    return {"groups": groups, "meta": {"subsLastUpdate": stamp, "liveEventsLastUpdate": stamp}}


def update_live(stats: dict) -> dict:
    log.info("Live update")
    members = [m for group in stats["groups"].values() for m in group["members"]]
    with ThreadPoolExecutor(8) as pool:
        for member, video in zip(members, pool.map(live_video, members)):
            member["video"] = video
    stats["meta"]["liveEventsLastUpdate"] = now().isoformat(timespec="minutes")
    return stats


# --- Calendars + feeds -----------------------------------------------------------------------------------------------


def update_events(stats: dict) -> dict:
    """Merge currently live/scheduled videos into the persisted event log, drop old ones."""
    path = DATA / "events.json"
    events = json.loads(path.read_text()) if path.is_file() else {}
    ts = int(time.time())
    for group in stats["groups"].values():
        for member in group["members"]:
            if not (video := member["video"]):
                continue
            known = events.get(video["id"])
            start = video["start"] or (known["start"] if known else ts)
            events[video["id"]] = {
                "slug": member["twitter"],
                "member": member["name"],
                "bg": member["bg"],
                "title": video["title"],
                "description": video["description"],
                "thumbnail": video["thumbnail"],
                "start": start,
                "end": max(ts, start + 3600),  # 1h placeholder, grows while live
                "updated": ts,
            }
    events = {vid: e for vid, e in events.items() if e["start"] > ts - RETENTION}
    write(path, json.dumps(events, indent=1))
    return events


def ics_fold(line: str) -> str:
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode()) > 74:
            out.append(cur)
            cur = " "
        cur += ch
    return "\r\n".join(out + [cur])


def ics_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_time(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y%m%dT%H%M%SZ")


def calendar(name: str, slug: str, events: list[tuple[str, dict]]) -> str:
    title = f"{name} Calendar"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{SITE.split('//')[-1]}//Live Calendar {ics_text(name)}//EN",
        f"NAME:{ics_text(title)}",
        f"X-WR-CALNAME:{ics_text(title)}",
        f"DESCRIPTION:Live streams of {ics_text(name)}. New streams start out 1h long and are adjusted while live.",
        f"SOURCE;VALUE=URI:{SITE}/events/{slug}.ics",
        "REFRESH-INTERVAL;VALUE=DURATION:PT15M",
        "X-PUBLISHED-TTL:PT15M",
    ]
    for vid, e in events:
        link = f"https://youtu.be/{vid}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{vid}@holozone",
            f"DTSTAMP:{ics_time(e['updated'])}",
            f"LAST-MODIFIED:{ics_time(e['updated'])}",
            f"DTSTART:{ics_time(e['start'])}",
            f"DTEND:{ics_time(e['end'])}",
            f"SUMMARY:{ics_text(f'[{e["member"]}] - {e["title"]}')}",
            f"DESCRIPTION:{ics_text(f'Watch {e["member"]} live on YouTube {link}')}",
            f"URL:{link}",
            f"CONFERENCE;VALUE=URI;FEATURE=AUDIO,VIDEO,CHAT:{link}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(map(ics_fold, lines)) + "\r\n"


def feed(name: str, image: str | None, events: list[tuple[str, dict]]) -> str:
    rfc = lambda ts: format_datetime(datetime.fromtimestamp(ts, UTC))
    items = "".join(
        f"<item><title>{escape(e['title'])}</title><link>https://youtu.be/{vid}</link>"
        f"<description>{escape(e['description'])}</description>"
        f'<guid isPermaLink="false">{vid}</guid><pubDate>{rfc(e["start"])}</pubDate>'
        f'<enclosure url="{escape(e["thumbnail"])}" length="0" type="image/jpeg"/></item>'
        for vid, e in sorted(events, key=lambda ve: ve[1]["start"], reverse=True)
    )
    img = (
        f"<image><url>{SITE}/{escape(image)}</url><title>{escape(name)} Feed</title><link>{SITE}/</link></image>"
        if image and not image.startswith("http")
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        f"<title>{escape(name)} Feed</title><link>{SITE}/</link>"
        f"<description>New live streams for {escape(name)}.</description><ttl>15</ttl>"
        f"<lastBuildDate>{format_datetime(now())}</lastBuildDate>{img}{items}</channel></rss>\n"
    )


def publish(stats: dict) -> None:
    events = update_events(stats)
    members = [m for group in stats["groups"].values() for m in group["members"]]
    for member in members:
        own = [(vid, e) for vid, e in events.items() if e["slug"] == member["twitter"]]
        write(DATA / "events" / f"{member['twitter']}.ics", calendar(member["name"], member["twitter"], own))
        write(DATA / "rss" / f"{member['twitter']}.xml", feed(member["name"], member["image"], own))
    write(DATA / "events" / "all.ics", calendar("All", "all", list(events.items())))
    write(DATA / "rss" / "all.xml", feed("All", None, list(events.items())))
    body = json.dumps(stats, indent=1, sort_keys=True)
    write(DATA / "stats.json", body)
    archive = DATA / "archive" / f"stats-{now().date().isoformat()}.json"
    if not archive.is_file():
        write(archive, body)


def updater() -> None:
    run = 0
    while True:
        try:
            stats = load_stats()
            stats = update_full() if run % 2 == 0 or stats is None else update_live(stats)
            publish(stats)
            log.info("Update done")
        except Exception:
            log.exception("Update failed")
        run += 1
        time.sleep(LIVE_INTERVAL)


# --- Web -------------------------------------------------------------------------------------------------------------


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        """Static files from www/, generated files (stats, events, rss, images, archive) from DATA."""
        static = Path(super().translate_path(path))
        generated = DATA / static.relative_to(WWW)
        return str(generated if static != WWW and generated.exists() else static)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            ok = (DATA / "stats.json").is_file()
            self.send_response(200 if ok else 503)
            self.end_headers()
            self.wfile.write(b"ok" if ok else b"no data yet")
            return
        super().do_GET()

    def end_headers(self) -> None:
        if self.path.split("?")[0].endswith((".json", ".ics", ".xml", "/")):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, format, *args) -> None:
        pass


Handler.extensions_map |= {
    ".ics": "text/calendar; charset=utf-8",
    ".xml": "application/rss+xml; charset=utf-8",
    ".webmanifest": "application/manifest+json",
}


def main() -> None:
    if not YT_KEY:
        raise SystemExit("YOUTUBE_KEY is required")
    DATA.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=updater, daemon=True).start()
    log.info("Serving on :%d", PORT)
    ThreadingHTTPServer(("", PORT), partial(Handler, directory=str(WWW))).serve_forever()


if __name__ == "__main__":
    main()
