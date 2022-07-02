from codecs import getincrementalencoder
from datetime import datetime, timedelta
from hashlib import md5, sha1
import json
import logging as log
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from ics import Calendar, Event, Todo
from ics.grammar.parse import ContentLine

from utils import best_match, hex2rgb

log.basicConfig(level=log.INFO)

ENCODER = getincrementalencoder("utf-8")()
BASE_PATH = Path(__file__).absolute().parent

EVENTS_PATH = BASE_PATH / "www/events/"
EVENTS_PATH.mkdir(parents=True, exist_ok=True)

UTC = ZoneInfo("UTC")
NOW = datetime.now().astimezone(UTC)

CREATOR = "-//hololive.zone//NONSGML Live Calendar {}//EN"

stats = json.loads((BASE_PATH / "www/stats.json").read_text())

css_colour_name = lambda member: best_match(hex2rgb(member["bg"][1:]))[0]
uuid = lambda value: str(UUID(md5(value.encode()).hexdigest()))
cal_id = lambda video: uuid(video["id"])
yt_link = lambda video: f"https://youtu.be/{video['id']}"
format_date = lambda date: date.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def spec_conform(text):
    ENCODER.reset()
    lines = []
    for line in text.split("\n"):
        current_line = b""
        for char in map(ENCODER.encode, line):
            if len(current_line) + len(char) > 73:
                lines.append(current_line)
                current_line = b" " + char
            else:
                current_line += char
        lines.append(current_line)
    return b"\r\n".join(lines)


def add_event(calendar: Calendar, new_event: Event, old_event_id, yt_link):
    copy = calendar.events.copy()
    for event in calendar.events:
        if event.uid == old_event_id or yt_link in event.description:
            copy.remove(event)
    for event in copy.copy():
        if event.uid == new_event.uid:
            copy.remove(event)
            copy.add(new_event)
            break
    else:
        copy.add(new_event)
    calendar.events = copy


def new_calendar(member):
    calendar = Calendar(creator=CREATOR.format(member["name"]))
    name = member["name"] + " Calendar"
    calendar.extra.extend(
        [
            ContentLine("NAME", value=name),
            ContentLine("X-WR-CALNAME", value=name),
            ContentLine(
                "DESCRIPTION",
                value=f"Calendar with all new live streams for {member['name']}. New live streams will be set to 1h long and then adjusted during the live stream.",
            ),
            ContentLine("SOURCE", {"VALUE": ["URI"]}, f"https://hololive.zone/events/{member['twitter']}.ics"),
            ContentLine("REFRESH-INTERVAL", {"VALUE": ["DURATION"]}, "P4H"),
        ]
    )
    return calendar


def event_extras(member, video):
    return [
        ContentLine("COLOR", value=css_colour_name(member)),
        ContentLine("CONFERENCE", {"VALUE": ["URI"], "FEATURE": ["AUDIO", "VIDEO", "CHAT"]}, yt_link(video)),
        ContentLine("DTSTAMP", value=format_date(NOW)),
    ]


def new_event(member, calendar):
    video = member["video"]
    uid = cal_id(video)

    name = f"[{member['name']}] - {video['title']}"
    description = f"Watch {member['name']} live on YouTube https://youtu.be/{video['id']}"

    start = datetime.fromtimestamp(video["start"]).astimezone(UTC)
    if video["start"] == 0:
        known_event = next(iter([e for e in calendar.events if e.uid == uid]), None)
        if known_event:
            start = known_event.begin.datetime

    if start + timedelta(minutes=15) < NOW:
        duration = NOW - start
    else:
        duration = timedelta(hours=1)

    event = Event(
        name,
        start,
        description=description,
        duration=duration,
        last_modified=NOW,
        uid=uid,
        url=yt_link(video),
    )
    event.extra.extend(event_extras(member, video))
    return event


# Create all individual calendars
all_events = []
for group in stats.values():
    log.info("BEGIN:[%s]", group["name"])
    for member in group["members"]:
        file = EVENTS_PATH / (member["twitter"] + ".ics")
        is_new = False
        if file.is_file() and (content := file.read_text()):
            try:
                calendar = Calendar(content)
            except Exception:
                log.fatal("[%s] Got an error parsing the calendar [%s]", member["name"], str(file))
                raise
            is_new = True
        else:
            calendar = new_calendar(member)

        if member["video"]:
            log.info("[%s] new event", member["name"])
            event = new_event(member, calendar)
            old_event_id = sha1(str(member["video"]["title"]).encode()).hexdigest()
            add_event(calendar, event, old_event_id, yt_link(member["video"]))
            all_events.append((event, old_event_id, yt_link(member["video"])))
        elif is_new:
            log.warning("[%s] No events found, creating placeholder todo", member["name"])
            todo = Todo(
                dtstamp=datetime.fromtimestamp(0),
                uid=str(uuid4()),
                completed=datetime.fromtimestamp(0),
                description="This only acts as a placeholder for a valid ics calendar file",
            )

        file.write_bytes(spec_conform(calendar.serialize()))
    log.info("END:[%s]\n", group["name"])

# Create one calendar containing all events
file = EVENTS_PATH / "all.ics"
if file.is_file() and (content := file.read_text()):
    calendar = Calendar(content)
else:
    calendar = new_calendar({"name": "All", "twitter": "all"})

for event, old_event_id, yt_link in all_events:
    add_event(calendar, event, old_event_id, yt_link)

file.write_bytes(spec_conform(calendar.serialize()))
