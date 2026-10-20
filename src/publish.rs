//! Turning collected stats into the published files: stats.json, calendars, RSS feeds, archive.

use std::collections::BTreeMap;
use std::path::Path;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::collect;
use crate::util::{Res, css_colour_name, date, ics_time, md5_uuid, now, rfc2822, write_atomic};

const RETENTION: i64 = 7 * 86400;

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Event {
    pub slug: String,
    pub member: String,
    pub bg: String,
    pub title: String,
    pub description: String,
    pub thumbnail: String,
    #[serde(default)]
    pub thumbnail_size: u64,
    pub start: i64,
    pub end: i64,
    pub updated: i64,
}

pub fn members(stats: &Value) -> impl Iterator<Item = &Value> {
    stats["groups"]
        .as_object()
        .into_iter()
        .flat_map(|g| g.values())
        .flat_map(|g| g["members"].as_array())
        .flatten()
}

/// Merges the currently live / scheduled videos into the persisted event log and drops old ones.
pub fn merge_events(events: &mut BTreeMap<String, Event>, stats: &Value, ts: i64) {
    for m in members(stats) {
        let video = &m["video"];
        let Some(id) = video["id"].as_str() else { continue };
        let known = events.get(id);
        let start = match video["start"].as_i64().unwrap_or(0) {
            0 => known.map_or(ts, |e| e.start),
            s => s,
        };
        // New streams get 1h; once a stream runs past 15 min its end follows the live check.
        let end = if start + 900 < ts { ts } else { start + 3600 };
        let thumbnail = video["thumbnail"].as_str().unwrap_or("").to_string();
        let thumbnail_size = match known {
            Some(e) if e.thumbnail == thumbnail && e.thumbnail_size > 0 => e.thumbnail_size,
            _ => 0,
        };
        events.insert(
            id.to_string(),
            Event {
                slug: str_of(m, "slug"),
                member: str_of(m, "name"),
                bg: str_of(m, "bg"),
                title: str_of(video, "title"),
                description: str_of(video, "description"),
                thumbnail,
                thumbnail_size,
                start,
                end,
                updated: ts,
            },
        );
    }
    events.retain(|_, e| e.start > ts - RETENTION);
}

fn str_of(v: &Value, key: &str) -> String {
    v[key].as_str().unwrap_or("").to_string()
}

fn ics_text(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace(';', "\\;")
        .replace(',', "\\,")
        .replace('\n', "\\n")
        .replace('\r', "")
}

/// RFC 5545 line folding: at most 75 octets per line, never splitting a UTF-8 character.
fn ics_fold(line: &str) -> String {
    let mut out = String::new();
    let mut len = 0;
    for ch in line.chars() {
        if len + ch.len_utf8() > 74 {
            out.push_str("\r\n ");
            len = 1;
        }
        out.push(ch);
        len += ch.len_utf8();
    }
    out
}

pub fn calendar(site: &str, name: &str, slug: &str, events: &[(&String, &Event)], ts: i64) -> String {
    let host = site.split("//").last().unwrap_or(site);
    let title = format!("{name} Calendar");
    let mut lines = vec![
        "BEGIN:VCALENDAR".to_string(),
        "VERSION:2.0".to_string(),
        format!("PRODID:-//{host}//NONSGML Live Calendar {}//EN", ics_text(name)),
        format!("NAME:{}", ics_text(&title)),
        format!("X-WR-CALNAME:{}", ics_text(&title)),
        format!(
            "DESCRIPTION:{}",
            ics_text(&format!(
                "Calendar with all new live streams for {name}. New live streams will be set to 1h long and then adjusted during the live stream."
            ))
        ),
        format!("SOURCE;VALUE=URI:{site}/events/{slug}.ics"),
        "REFRESH-INTERVAL;VALUE=DURATION:PT4H".to_string(),
    ];
    for (id, e) in events {
        let link = format!("https://youtu.be/{id}");
        lines.extend([
            "BEGIN:VEVENT".to_string(),
            format!("UID:{}", md5_uuid(id)),
            format!("DTSTAMP:{}", ics_time(ts)),
            format!("LAST-MODIFIED:{}", ics_time(e.updated)),
            format!("DTSTART:{}", ics_time(e.start)),
            format!("DTEND:{}", ics_time(e.end)),
            format!("SUMMARY:{}", ics_text(&format!("[{}] - {}", e.member, e.title))),
            format!(
                "DESCRIPTION:{}",
                ics_text(&format!("Watch {} live on YouTube {link}", e.member))
            ),
            format!("URL:{link}"),
            format!("COLOR:{}", css_colour_name(&e.bg)),
            format!("CONFERENCE;VALUE=URI;FEATURE=AUDIO,VIDEO,CHAT:{link}"),
            "END:VEVENT".to_string(),
        ]);
    }
    lines.push("END:VCALENDAR".to_string());
    lines.iter().map(|l| ics_fold(l)).collect::<Vec<_>>().join("\r\n") + "\r\n"
}

fn xml(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

pub fn feed(site: &str, name: &str, image: Option<&str>, events: &[(&String, &Event)], ts: i64) -> String {
    let title = format!("{name} Feed");
    let mut sorted = events.to_vec();
    sorted.sort_by_key(|(_, e)| std::cmp::Reverse(e.start));
    let pub_date = sorted.first().map_or(ts, |(_, e)| e.start);
    let mut out = format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<rss version=\"2.0\"><channel><title>{}</title><link>{site}/</link>\
         <description>RSS Feed with up to date new live streams for {}.</description><language>en</language>\
         <managingEditor>na@nachtalb.io (Nachtalb)</managingEditor><webMaster>na@nachtalb.io (Nachtalb)</webMaster>\
         <pubDate>{}</pubDate><lastBuildDate>{}</lastBuildDate><ttl>15</ttl>",
        xml(&title),
        xml(name),
        rfc2822(pub_date),
        rfc2822(ts)
    );
    if let Some(img) = image {
        out += &format!(
            "<image><url>{site}/{}</url><title>{}</title><link>{site}/</link><width>144</width><height>400</height></image>",
            xml(img),
            xml(&title)
        );
    }
    for (id, e) in sorted {
        out += &format!(
            "<item><title>{}</title><link>https://youtu.be/{id}</link><description>{}</description>\
             <guid isPermaLink=\"false\">{}</guid><pubDate>{}</pubDate>\
             <enclosure url=\"{}\" length=\"{}\" type=\"image/jpeg\"/></item>",
            xml(&e.title),
            xml(&e.description),
            md5_uuid(id),
            rfc2822(e.start),
            xml(&e.thumbnail),
            e.thumbnail_size
        );
    }
    out + "</channel></rss>\n"
}

/// Writes every derived file. `stats` must already carry the latest data.
pub fn publish(data: &Path, site: &str, stats: &Value) -> Res<()> {
    let ts = now();
    let path = data.join("events.json");
    let mut events: BTreeMap<String, Event> = std::fs::read(&path)
        .ok()
        .and_then(|b| serde_json::from_slice(&b).ok())
        .unwrap_or_default();
    merge_events(&mut events, stats, ts);
    for e in events
        .values_mut()
        .filter(|e| e.thumbnail_size == 0 && !e.thumbnail.is_empty())
    {
        e.thumbnail_size = collect::content_length(&e.thumbnail).unwrap_or(0);
    }
    write_atomic(&path, &serde_json::to_vec_pretty(&events)?)?;

    for m in members(stats) {
        let slug = str_of(m, "slug");
        let name = str_of(m, "name");
        let own: Vec<_> = events.iter().filter(|(_, e)| e.slug == slug).collect();
        write_atomic(
            &data.join(format!("events/{slug}.ics")),
            calendar(site, &name, &slug, &own, ts).as_bytes(),
        )?;
        let image = m["rss_image"].as_str();
        write_atomic(
            &data.join(format!("rss/{slug}.xml")),
            feed(site, &name, image, &own, ts).as_bytes(),
        )?;
    }
    let all: Vec<_> = events.iter().collect();
    write_atomic(
        &data.join("events/all.ics"),
        calendar(site, "All", "all", &all, ts).as_bytes(),
    )?;
    write_atomic(&data.join("rss/all.xml"), feed(site, "All", None, &all, ts).as_bytes())?;

    let body = serde_json::to_vec_pretty(stats)?;
    write_atomic(&data.join("stats.json"), &body)?;
    let archive = data.join(format!("archive/stats-{}.json", date(ts)));
    if !archive.is_file() {
        write_atomic(&archive, &body)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn stats(video: Value) -> Value {
        json!({"groups": {"talents": {"members": [{"name": "Suisei", "slug": "suisei", "bg": "#799acb", "video": video}]}}})
    }

    #[test]
    fn event_lifecycle() {
        let mut ev = BTreeMap::new();
        let t0 = 1_800_000_000;
        merge_events(
            &mut ev,
            &stats(json!({"id": "v", "title": "t", "start": t0 + 600, "thumbnail": "x"})),
            t0,
        );
        assert_eq!((ev["v"].start, ev["v"].end), (t0 + 600, t0 + 4200));
        // live now: start stays, end follows the clock once past 15 min
        merge_events(
            &mut ev,
            &stats(json!({"id": "v", "title": "t", "start": 0, "thumbnail": "x"})),
            t0 + 7200,
        );
        assert_eq!((ev["v"].start, ev["v"].end), (t0 + 600, t0 + 7200));
        merge_events(&mut ev, &stats(Value::Null), t0 + 8 * 86400);
        assert!(ev.is_empty());
    }

    #[test]
    fn ics_is_folded_and_escaped() {
        let e = Event {
            slug: "s".into(),
            member: "M".into(),
            bg: "#fff".into(),
            title: "星".repeat(40) + ", ok; yes",
            description: String::new(),
            thumbnail: String::new(),
            thumbnail_size: 0,
            start: 0,
            end: 3600,
            updated: 0,
        };
        let id = "abc".to_string();
        let cal = calendar("https://holo.naa.gg", "M", "s", &[(&id, &e)], 0);
        assert!(cal.split("\r\n").all(|l| l.len() <= 75));
        assert!(cal.replace("\r\n ", "").contains("\\, ok\\; yes"));
        assert!(cal.contains("UID:90015098-3cd2-4fb0-d696-3f7d28e17f72"));
        assert!(cal.contains("COLOR:white"));
    }
}
