from codecs import getincrementalencoder
from datetime import datetime, timedelta
from hashlib import sha1
import json
from pathlib import Path
from uuid import uuid4

encoder = getincrementalencoder("utf-8")()

BASE_PATH = Path(__file__).absolute().parent

EVENTS_PATH = BASE_PATH / "www/events/"
EVENTS_PATH.mkdir(parents=True, exist_ok=True)

stats = json.loads((BASE_PATH / "www/stats.json").read_text())


def spec_conform(text):
    encoder.reset()
    lines = []
    for line in text.split('\n'):
        current_line = b""
        for char in map(encoder.encode, line):
            if len(current_line) + len(char) > 73:
                lines.append(current_line)
                current_line = b" " + char
            else:
                current_line += char
        lines.append(current_line)
    return b"\r\n".join(lines)


all_events = []
for group in stats.values():
    for member in group["members"]:
        file = EVENTS_PATH / (member["twitter"] + ".ics")

        file_content, events = None, ""
        if file.is_file():
            file_content = file.read_text()
            events = "\n".join(file_content.split("\n")[5:-2]).strip()

        new_event = ""
        if (video := member["video"]) and video["start"] > 0:
            event_id = sha1(str(video["title"]).encode()).hexdigest()
            if event_id in events:
                continue

            event_start = datetime.fromtimestamp(video["start"])
            event_end = event_start + timedelta(hours=1)
            event_name = f"[{member['name']}] - {video['title']}"
            event_description = f"Watch {member['name']} live on YouTube https://youtu.be/{video['id']}"

            new_event = f"""BEGIN:VEVENT
DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}
DTEND:{event_end.strftime('%Y%m%dT%H%M%SZ')}
DTSTART:{event_start.strftime('%Y%m%dT%H%M%SZ')}
SEQUENCE:0
SUMMARY:{event_name}
DESCRIPTION:{event_description}
UID:{event_id}
PRIORITY:5
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:REMINDER
TRIGGER:-PT5M
END:VALARM
X-PUBLISHED-TTL:PT5M
END:VEVENT"""
            all_events.append((event_id, new_event))

        if not new_event and not file_content:
            new_event = f"""BEGIN:VTODO
COMMENT:Placeholder to ensure valid calendar import
UID:{str(uuid4())}
DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}
END:VTODO"""

        if events and new_event:
            events += "\n" + new_event
        elif new_event:
            events = new_event

        new_content = f"""BEGIN:VCALENDAR
NAME:{member['name']} Live Calendar
PRODID:-//github.com/rianjs/ical.net//NONSGML ical.net 4.0//EN
VERSION:2.0
X-WR-CALNAME:{member['name']} Live Calendar
{events}
END:VCALENDAR
"""
        file.write_bytes(spec_conform(new_content))


file = EVENTS_PATH / "all.ics"
file_content, events = None, ""
if file.is_file():
    file_content = file.read_text()
    events = "\n".join(file_content.split("\n")[5:-2]).strip()

for event_id, event in all_events:
    if event_id not in events:
        events += "\n" + event

new_content = f"""BEGIN:VCALENDAR
NAME:Hololive Live Calendar
PRODID:-//github.com/rianjs/ical.net//NONSGML ical.net 4.0//EN
VERSION:2.0
X-WR-CALNAME:Hololive Live Calendar
{events.strip()}
END:VCALENDAR
"""
file.write_bytes(spec_conform(new_content))
