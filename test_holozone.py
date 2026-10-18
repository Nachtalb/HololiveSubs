import json
import time

from PIL import Image

import holozone


def player_page(details: dict, start: int | None = None) -> str:
    player = {"videoDetails": details}
    if start is not None:
        slate = {"liveStreamOfflineSlateRenderer": {"scheduledStartTime": str(start)}}
        player["playabilityStatus"] = {"liveStreamability": {"liveStreamabilityRenderer": {"offlineSlate": slate}}}
    return f"<script>var ytInitialPlayerResponse = {json.dumps(player)};var x = {{}};</script>"


def test_parse_live() -> None:
    now = int(time.time())
    live = holozone.parse_live(player_page({"videoId": "a", "title": "t", "isLive": True}))
    assert live and live["start"] == 0 and live["id"] == "a"
    soon = holozone.parse_live(player_page({"videoId": "b", "isUpcoming": True}, now + 3600))
    assert soon and soon["start"] == now + 3600
    assert holozone.parse_live(player_page({"videoId": "c", "isUpcoming": True}, now + 5 * 86400)) is None
    assert holozone.parse_live(player_page({"videoId": "d", "isUpcoming": True}, now - 30 * 86400)) is None
    assert holozone.parse_live(player_page({"videoId": "e"})) is None  # plain VOD
    assert holozone.parse_live("<html>no player</html>") is None


def test_ics_fold() -> None:
    folded = holozone.ics_fold("SUMMARY:" + "星" * 60)
    assert all(len(line.encode()) <= 75 for line in folded.split("\r\n"))
    assert folded.replace("\r\n ", "") == "SUMMARY:" + "星" * 60


def test_low_poly() -> None:
    out = holozone.low_poly(Image.new("RGB", (100, 100), (10, 20, 30)), seed="x")
    assert out.size == (100, 100) and out.getpixel((50, 50)) == (10, 20, 30)
