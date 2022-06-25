#!/usr/bin/env python
# -*- coding: utf-8 -*-
from concurrent.futures import ProcessPoolExecutor
import json
from json.decoder import JSONDecodeError
import logging
import os
from pathlib import Path
from subprocess import Popen
import sys
import time

from bilibili_api.user import UserInfo as BilibiliUser
from dotenv import load_dotenv
import requests
from twitter import Api, User
from yarl import URL

BASE_PATH = Path(__file__).absolute().parent

load_dotenv(BASE_PATH / ".env")

# Paths
IMAGES_PATH = BASE_PATH / "www/profile-images/"
IMAGES_PATH.mkdir(parents=True, exist_ok=True)

TALENTS_PATH = BASE_PATH / "talents.json"
STATS_PATH = BASE_PATH / "www/stats.json"

LOW_POLY_TOOL = BASE_PATH / "triangulate-tool/build/triangulate-tool"

# APIs
YT_API_KEY = os.environ["YOUTUBE_KEY"]
YT_API_URL = "https://www.googleapis.com/youtube/v3/channels?part={parts}&id={channels}&key={key}"

TWITTER_API_CLIENT = Api(
    consumer_key=os.environ["TWITTER_CONSUMER_KEY"],
    consumer_secret=os.environ["TWITTER_CONSUMER_SECRET"],
    access_token_key=os.environ["TWITTER_ACCESS_TOKEN"],
    access_token_secret=os.environ["TWITTER_ACCESS_SECRET"],
)

# Logging
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("HololiveStats")

# Talents Data
TALENTS_DATA = json.loads(TALENTS_PATH.read_text())
GROUPS = TALENTS_DATA["groups"]
TALENTS = TALENTS_DATA["talents"]

CURRENT_STATS = {}
if STATS_PATH.is_file():
    try:
        CURRENT_STATS = json.loads(STATS_PATH.read_text())
    except JSONDecodeError:
        pass


def get_youtube_data() -> dict:
    LOG.info("Getting YouTube stats")
    parts = ["statistics"]

    channel_ids = list(filter(None, map(lambda data: data["youtube"], TALENTS)))
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


def get_twitter_data() -> dict[str, User]:
    LOG.info("Getting Twitter stats")
    data = TWITTER_API_CLIENT.GetListMembersPaged(os.environ["TWITTER_MEMBER_LIST"])[2]
    return {talent.screen_name.lower(): talent for talent in data}


def get_bilibili_data(talent: dict) -> dict | None:
    if talent["bilibili"]:
        LOG.info("[%s]: Getting bilibili stats", talent["name"])
        try:
            return BilibiliUser(talent["bilibili"]).get_info()
        except Exception as error:
            LOG.warning('[%s] Could not load bilibili data due to "%s"', talent["name"], str(error))


def json_getattr(key, json, default=None):
    keys = key.split('.')
    current_item = json
    for key in keys:
        if key[0] == '[' and key[-1] == ']':
            key = int(key[1:-1])
        try:
            current_item = current_item[key]
        except (KeyError, IndexError):
            return default
    return current_item


def get_live_vide_info(html):
    start = "var ytInitialPlayerResponse = "
    start_index = html.index(start) + len(start)
    text = html[start_index:]

    counter = 0
    final = None
    for i, char in enumerate(text, 1):
        if char == '{':
            counter += 1
        elif char == '}':
            counter -= 1
        if counter == 0:
            final = text[:i]
            break

    if not final:
        return

    try:
        raw_data = json.loads(final)
    except JSONDecodeError:
        return

    data = {
        "title": json_getattr("videoDetails.title", raw_data),
        "start": int(json_getattr("playabilityStatus.liveStreamability.liveStreamabilityRenderer.offlineSlate.liveStreamOfflineSlateRenderer.scheduledStartTime", raw_data, 0)),
        "id": json_getattr("videoDetails.videoId", raw_data),
        "description": json_getattr("videoDetails.shortDescription", raw_data),
        "alreadyLive": json_getattr("microformat.liveBroadcastDetails.isLiveNow", raw_data, False)
    }
    data["thumbnail"] = f"https://i.ytimg.com/vi/{data['id']}/maxresdefault.jpg"

    if data["start"] - time.time() > 60 * 60 * 24 * 2:
        return
    return data


def next_youtube_live_schedule(channel: dict) -> None | dict:
    LOG.info('[%s] Live on YouTube check', channel["name"])
    try:
        res = requests.get(
            f"https://www.youtube.com/channel/{channel['youtube']}/live",
            headers={
                "Cookie": "CONSENT=YES+cb.20210328-17-p0.en-GB+FX+634; VISITOR_INFO1_LIVE=9Ovd7YuEQbw; YSC=Tnb5Btx3xik"
            },
        )
        res.raise_for_status()
        return get_live_vide_info(res.text)
    except Exception:
        pass


def get_images(twitter: User, name: str) -> tuple[str | None, str | None]:
    profile_image_url = background_image_url = None

    image_url = URL(twitter.profile_image_url_https.replace("_normal", ""))  # type: ignore
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


def summarize_data(channel_data: dict, twitter: User, youtube: dict | None):
    if not twitter:
        LOG.fatal("[%s] No twitter data", channel_data["name"])
        sys.exit(1)

    images = get_images(twitter, channel_data["name"])
    update_data = {
        "image": images[0],
        "background_image": images[1],
        "twitter_subs": int(twitter.followers_count),  # type: ignore
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
        # only check wheter the account is live or not
        LOG.info("Updating YouTube live status")
        for group in CURRENT_STATS.values():
            for talent, video_info in zip(group["members"], executor.map(next_youtube_live_schedule, group["members"])):
                talent["video"] = video_info

        GROUPS = CURRENT_STATS
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

        for data in sorted(TALENTS, reverse=True, key=lambda data: data.get("youtube_subs", data["twitter_subs"])):
            group_name = data.get("group", "talents")
            GROUPS[group_name]["members"].append(data)

        result = dict(sorted(GROUPS.items(), key=lambda item: item[1]["order"]))


# Write stats
STATS_PATH.write_text(json.dumps(GROUPS, indent=2, sort_keys=True))
LOG.info("Done")
