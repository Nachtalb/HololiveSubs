from datetime import datetime, timedelta
from hashlib import sha1
import json
from pathlib import Path

BASE_PATH = Path(__file__).absolute().parent

EVENTS_PATH = BASE_PATH / "www/events/"
EVENTS_PATH.mkdir(parents=True, exist_ok=True)

stats = json.loads((BASE_PATH / "www/stats.json").read_text())

for group in stats.values():
    for member in group["members"]:
        file = EVENTS_PATH / (member["twitter"] + ".ics")

        file_content, events = None, ""
        if file.is_file():
            file_content = file.read_text()
            events = "\n".join(file_content.split("\n")[5:-1])

        new_event = ""
        if (next_live := member["next_live"]) > 0:
            event_id = sha1(str(next_live).encode()).hexdigest()
            if event_id in events:
                continue

            event_start = datetime.fromtimestamp(next_live)
            event_end = event_start + timedelta(hours=1)
            event_name = member["name"] + " live!"
            new_event = f"""BEGIN:VEVENT
DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}
DTEND:{event_end.strftime('%Y%m%dT%H%M%SZ')}
DTSTART:{event_start.strftime('%Y%m%dT%H%M%SZ')}
SEQUENCE:0
SUMMARY:{event_name}
UID:{event_id}
PRIORITY:5
BEGIN:VALARM
ACTION:DISPLAY
DESCRIPTION:REMINDER
TRIGGER:-PT5M
END:VALARM
X-PUBLISHED-TTL:PT5M
END:VEVENT"""

        if new_event or not file_content:
            events += "\n" + new_event

            file.write_text(f"""BEGIN:VCALENDAR
NAME:{member['name']} Live Calendar
PRODID:-//github.com/rianjs/ical.net//NONSGML ical.net 4.0//EN
VERSION:2.0
X-WR-CALNAME:{member['name']} Live Calendar
{events}
END:VCALENDAR
""")
