#!/usr/bin/env python
# -*- coding: utf-8 -*-
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import json
from json.decoder import JSONDecodeError
import logging
import os
from pathlib import Path
from subprocess import Popen
import sys
import time
from typing import Any
from zoneinfo import ZoneInfo

from bilibili_api import sync, user
from dotenv import load_dotenv
import requests
from yarl import URL

BASE_PATH = Path(__file__).absolute().parent

load_dotenv(BASE_PATH / ".env")

# Paths
IMAGES_PATH = BASE_PATH / "www/profile-images/"
IMAGES_PATH.mkdir(parents=True, exist_ok=True)

TALENTS_PATH = BASE_PATH / "talents.json"
STATS_PATH = BASE_PATH / "www/stats.json"

LOW_POLY_TOOL = BASE_PATH / "triangulate-tool/build/triangulate-tool"

TWITTER_BEARER_TOKEN = os.environ["TWITTER_BEARER_TOKEN"]

# APIs
YT_API_KEY = os.environ["YOUTUBE_KEY"]
YT_API_URL = "https://www.googleapis.com/youtube/v3/channels?part={parts}&id={channels}&key={key}"

# Logging
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("HololiveStats")

# Talents Data
TALENTS_DATA = json.loads(TALENTS_PATH.read_text())
GROUPS = TALENTS_DATA["groups"]
TALENTS = TALENTS_DATA["talents"]

NOW = datetime.now().astimezone(ZoneInfo("UTC")).isoformat(timespec="minutes")

CURRENT_STATS = {
    "groups": {},
    "meta": {"subsLastUpdate": NOW, "liveEventsLastUpdate": NOW},
}
if STATS_PATH.is_file():
    try:
        CURRENT_STATS = json.loads(STATS_PATH.read_text())
    except JSONDecodeError:
        pass


def get_youtube_data() -> dict[str, Any]:
    LOG.info("Getting YouTube stats")
    parts = ["statistics"]

    channel_ids             : list[str]= list(filter(None, map(lambda data: data["youtube"], TALENTS)))
    chunked_channel_ids = [channel_ids[:50], channel_ids[50:]]

    result = {}
    for channel_ids in chunked_channel_ids:
        yt_full_url = YT_API_URL.format(
            parts=",".join(parts),
            channels=",".join(channel_ids),
            key=YT_API_KEY,
        )
        result.update({item["id"]: item for item in requests.get(yt_full_url).json()["items"]})

    return result


def get_list_members() -> dict[str, Any]:
    url = f"https://api.twitter.com/1.1/lists/members.json"
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"},
        params={
            "list_id": os.environ["TWITTER_MEMBER_LIST"],
            "count": 1000,
        },
    )

    if response.status_code != 200:
        raise Exception(f"Request returned an error: {response.status_code} {response.text}")

    return response.json()  # type: ignore[no-any-return]


def get_twitter_data() -> dict[str, dict[str, Any]]:
    LOG.info("Getting Twitter stats")
    data = get_list_members()
    return {talent["screen_name"].lower(): talent for talent in data["users"]}


def get_bilibili_data(talent: dict) -> dict | None:
    if talent["bilibili"]:
        LOG.info("[%s]: Getting bilibili stats", talent["name"])
        try:
            return sync(user.User(talent["bilibili"]).get_relation_info())
        except Exception as error:
            LOG.warning(
                '[%s] Could not load bilibili data due to "%s"',
                talent["name"],
                str(error),
            )


def json_getattr(key, json, default=None):
    keys = key.split(".")
    current_item = json
    for key in keys:
        if key[0] == "[" and key[-1] == "]":
            key = int(key[1:-1])
        try:
            current_item = current_item[key]
        except (KeyError, IndexError):
            return default
    return current_item


def find_json(string, start_search):
    start_index = string.index(start_search) + len(start_search)
    text = string[start_index:]

    counter = 0
    final = None
    for i, char in enumerate(text, 1):
        if char == "{":
            counter += 1
        elif char == "}":
            counter -= 1
        if counter == 0:
            final = text[:i]
            break

    return final


def get_live_video_info(html):
    raw_data = find_json(html, "var ytInitialPlayerResponse = ")

    if not raw_data:
        return

    try:
        raw_json = json.loads(raw_data)
        video_id = json_getattr("videoDetails.videoId", raw_json)
        if not video_id:
            return
    except JSONDecodeError:
        return

    data = {
        "title": json_getattr("videoDetails.title", raw_json),
        "start": int(
            json_getattr(
                "playabilityStatus.liveStreamability.liveStreamabilityRenderer.offlineSlate.liveStreamOfflineSlateRenderer.scheduledStartTime",
                raw_json,
                0,  # 0 == already live
            )
        ),
        "id": video_id,
        "description": json_getattr("videoDetails.shortDescription", raw_json),
        "thumbnail": json_getattr(
            "videoDetails.thumbnail.thumbnails.[-1].url",
            raw_json,
            f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        ),
    }

    if data["start"] - time.time() > 60 * 60 * 24 * 2:
        return
    return data


def next_youtube_live_schedule(channel: dict) -> None | dict:
    LOG.info("[%s] Live on YouTube check", channel["name"])
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0"
            " Safari/537.36"
        ),
        "Cookie": (
            "CONSENT=YES+926; SOCS=CAESEwgDEgk1NjQ0NjAzMDMaAmVuIAEaBgiA1P6nBg; VISITOR_PRIVACY_METADATA=CgJDSBICGgA%3D;"
            " YSC=poeLmbJpLv0; __Secure-YEC=CgtaMmhvRHI5WTJjWSizvYOoBjIICgJDSBICGgA%3D"
        ),
    }
    try:
        res = requests.get(
            f"https://www.youtube.com/channel/{channel['youtube']}/live",
            headers=headers,
        )
        res.raise_for_status()
        return get_live_video_info(res.text)
    except Exception:
        pass


def get_images(twitter: dict[str, Any], name: str) -> tuple[str | None, str | None]:
    profile_image_url = background_image_url = None

    image_url = URL(twitter["profile_image_url_https"].replace("_normal", ""))  # type: ignore
    image_path = IMAGES_PATH / image_url.name

    if not image_path.is_file():
        LOG.info("[%s] Fetching new profile image", name)
        response = requests.get(str(image_url))
        if response.status_code == 200:
            image_path.write_bytes(response.content)
        else:
            LOG.warning("[%s] Failed to retrive image", name)

    profile_image_url = str(image_path.relative_to(BASE_PATH / "www") if image_path.is_file() else image_url)

    background_image = image_path.with_stem(image_path.stem + "_background")
    if not background_image.is_file() and LOW_POLY_TOOL.is_file():
        LOG.info("[%s] Generate background image", name)
        proc = Popen([str(LOW_POLY_TOOL), str(image_path), str(background_image), "150", "10"])
        if proc.wait() != 0:
            LOG.warning("[%s] Failed to generate background image", name)

    if background_image.is_file():
        background_image_url = str(background_image.relative_to(BASE_PATH / "www"))

    return (profile_image_url, background_image_url)


def summarize_data(channel_data: dict, twitter: dict[str, Any], youtube: dict | None):
    if not twitter:
        LOG.fatal("[%s] No twitter data", channel_data["name"])
        sys.exit(1)

    images = get_images(twitter, channel_data["name"])
    update_data = {
        "image": images[0],
        "background_image": images[1],
        "twitter_subs": twitter["followers_count"],
        "video": None,
    }

    if bilibili := get_bilibili_data(channel_data):
        update_data["bilibili_subs"] = int(bilibili["follower"])

    if youtube:
        update_data["youtube_subs"] = int(youtube["statistics"]["subscriberCount"])

        if not channel_data["retired"]:
            update_data["video"] = next_youtube_live_schedule(channel_data)

    return update_data


with ProcessPoolExecutor(5) as executor:
    if "live" in sys.argv:
        # only check whether the account is live or not
        LOG.info("Updating YouTube live status")
        for group in CURRENT_STATS["groups"].values():
            for talent, video_info in zip(
                group["members"],
                executor.map(next_youtube_live_schedule, group["members"]),
            ):
                talent["video"] = video_info

        CURRENT_STATS["meta"]["liveEventsLastUpdate"] = NOW
        result = CURRENT_STATS
    else:
        youtube_data = get_youtube_data()
        twitter_data = get_twitter_data()

        sorted_youtube_data = []
        sorted_twitter_data = []
        for talent in TALENTS:
            sorted_youtube_data.append(youtube_data.get(talent["youtube"]))
            sorted_twitter_data.append(twitter_data.get(talent["twitter"].lower()))

        map_data = executor.map(summarize_data, TALENTS, sorted_twitter_data, sorted_youtube_data)
        for talent, result in zip(TALENTS, map_data):
            talent.update(result)

        for data in sorted(
            TALENTS,
            reverse=True,
            key=lambda data: data.get("youtube_subs", data["twitter_subs"]),
        ):
            group_name = data.get("group", "talents")
            GROUPS[group_name]["members"].append(data)

        GROUPS = dict(sorted(GROUPS.items(), key=lambda item: item[1]["order"]))
        result = {
            "groups": GROUPS,
            "meta": {
                "subsLastUpdate": NOW,
                "liveEventsLastUpdate": NOW,
            },
        }


# Write stats
STATS_PATH.write_text(json.dumps(result, indent=2, sort_keys=True))
LOG.info("Done")
