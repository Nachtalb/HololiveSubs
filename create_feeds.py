import json
import logging as log
from datetime import datetime, timedelta
from email.utils import format_datetime
from hashlib import md5
from pathlib import Path
from typing import TypedDict
from uuid import UUID
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw
from rfeed import Enclosure, Feed, Guid
from rfeed import Image as RImage
from rfeed import Item


class Video(TypedDict):
    description: str
    id: str
    start: int
    thumbnail: str
    title: str


class Member(TypedDict):
    background_image: str
    bg: str
    bilibili: str
    bilibili_subs: int | None
    fg: str
    group: str
    id: int
    image: str
    name: str
    retired: bool
    twitter: str
    twitter_subs: int
    video: Video | None
    youtube: str
    youtube_subs: int


log.basicConfig(level=log.INFO)

BASE_PATH = Path(__file__).absolute().parent
WEB_PATH = BASE_PATH / "www"
RSS_PATH = WEB_PATH / "rss/"
RSS_PATH.mkdir(parents=True, exist_ok=True)

UTC = ZoneInfo("UTC")
NOW = datetime.now().astimezone(UTC)
RETENTION = timedelta(days=7)

RSS_IMAGE_SIZE = (144, 144)

stats: dict[str, dict[str, dict[str, list[Member]]]] = json.loads((BASE_PATH / "www/stats.json").read_text())


def uuid(value: str) -> str:
    return str(UUID(md5(value.encode()).hexdigest()))


def rss_id(video: Video) -> str:
    return uuid(video["id"])


def yt_link(video: Video) -> str:
    return f"https://youtu.be/{video['id']}"


def process_image(image_path: Path, background_path: Path) -> Path:
    new_path = image_path.with_stem(image_path.stem + "_rss")

    # If the new path already exists, return it immediately
    if new_path.exists():
        return new_path

    image1 = crop_and_border_image(image_path)
    image2 = resize_and_crop_image(background_path)
    combined_image = combine_images(image1, image2)

    # Save the final result
    combined_image.save(new_path)

    return new_path


def crop_and_border_image(image_path: Path) -> Image.Image:
    image = Image.open(image_path).convert("RGBA")
    size = image.size

    # Create circular mask
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + size, fill=255)

    # Apply mask
    image.putalpha(mask)

    # Create border
    border = Image.new("L", size, 0)
    draw = ImageDraw.Draw(border)
    draw.ellipse((1, 1) + (size[0] - 1, size[1] - 1), fill=255)
    image.putalpha(border)

    return image


def resize_and_crop_image(image_path: Path) -> Image.Image:
    image = Image.open(image_path)
    image = image.resize((400, 400), Image.LANCZOS)

    # Crop centered to 144x400
    left = (image.width - 144) / 2
    right = (image.width + 144) / 2
    return image.crop((left, 0, right, 400))  # pyright: ignore


def combine_images(image1: Image.Image, image2: Image.Image) -> Image.Image:
    image1_resized = image1.resize((120, 120), Image.LANCZOS)
    x = (image2.size[0] - image1_resized.size[0]) // 2
    y = (image2.size[1] - image1_resized.size[1]) // 2
    image2.paste(image1_resized, (x, y), image1_resized)
    return image2


def get_image_size_by_url(url: str) -> int:
    response = requests.head(url)
    return int(response.headers["Content-Length"])


def new_feed(member: Member) -> Feed:
    feed = Feed(
        title=f"{member['name']} Feed",
        description=f"RSS Feed with up to date new live streams for {member['name']}.",
        link="https://hololive.zone/",
        lastBuildDate=NOW,
        managingEditor="na@nachtalb.io (Nachtalb)",
        webMaster="na@nachtalb.io (Nachtalb)",
        ttl=15,
    )

    feed.docs = None

    if member["image"]:
        prof_image = process_image(
            WEB_PATH / member["image"],
            WEB_PATH / member["background_image"],
        )

        feed.image = RImage(
            url=f"https://hololive.zone/{prof_image.relative_to(WEB_PATH)}",
            title=feed.title,
            link=feed.link,
            height=400,
            width=144,
        )

    return feed


def new_event(member: Member, feed: Feed) -> Item:
    if not member["video"]:
        return Item(title="Placeholder")

    return Item(
        title=member["video"]["title"],
        description=member["video"]["description"],
        guid=Guid(
            rss_id(member["video"]),
            isPermaLink=False,
        ),
        pubDate=(datetime.fromtimestamp(member["video"]["start"]).astimezone(UTC) if member["video"]["start"] else NOW),
        link=yt_link(member["video"]),
        enclosure=Enclosure(
            length=get_image_size_by_url(member["video"]["thumbnail"]),
            type="image/jpg",
            url=member["video"]["thumbnail"],
        ),
    )


def clear_old_events(feed: Feed) -> None:
    pass


# Create all individual calendars
all_items = []
for group in stats["groups"].values():
    log.info("BEGIN:[%s]", group["name"])
    for member in group["members"]:
        file = RSS_PATH / (member["twitter"] + ".xml")
        is_new = False

        #  if file.is_file() and (content := file.read_text()):
        #      try:
        #          imported_feed = Calendar(content)
        #
        #          if not any([extra for extra in imported_feed.extra if extra.name == "SOURCE"]):
        #              feed = new_calendar(member)
        #              feed.events = imported_feed.events
        #          else:
        #              feed = imported_feed
        #      except Exception:
        #          log.fatal("[%s] Got an error parsing the calendar [%s]", member["name"], str(file))
        #          raise
        #      is_new = True
        #  else:
        feed: Feed = new_feed(member)

        if member["video"]:
            item: Item = new_event(member, feed)
            feed.items.append(item)
            all_items.append(item)
            feed.pubDate = item.pubDate
        else:
            feed.pubDate = NOW
        #  elif is_new:
        #      todo = Todo(
        #          dtstamp=datetime.fromtimestamp(0),
        #          uid=str(uuid4()),
        #          completed=datetime.fromtimestamp(0),
        #          description="This only acts as a placeholder for a valid ics calendar file",
        #      )

        clear_old_events(feed)
        file.write_text(feed.rss())
    log.info("END:[%s]\n", group["name"])

# Create one calendar containing all events
log.info("[ALL] Save all events to all.ics")
file = RSS_PATH / "all.xml"
#  if file.is_file() and (content := file.read_text()):
#      feed = Calendar(content)
#  else:
feed = new_feed({"name": "All", "image": ""})
feed.items.extend(all_items)
feed.pubDate = sorted(all_items, key=lambda item: item.pubDate)[0].pubDate
file.write_text(feed.rss())
