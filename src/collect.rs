//! Data sources: YouTube Data API, YouTube feeds, Twitch, X (via FxTwitter) and Bilibili.

use std::sync::LazyLock;
use std::time::Duration;

use serde_json::{Value, json};

use crate::util::{Res, parse_iso};

const UA: &str =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36";
const LIMIT: u64 = 20 << 20;
// Twitch's public web client id; the gql endpoint needs no key or registered app with it
const TWITCH_CLIENT_ID: &str = "kimne78kx3ncx6brgo4mv6wki5h1ko";

static AGENT: LazyLock<ureq::Agent> = LazyLock::new(|| {
    ureq::Agent::config_builder()
        .timeout_global(Some(Duration::from_secs(30)))
        .user_agent(UA)
        .build()
        .into()
});

pub fn get_text(url: &str) -> Res<String> {
    Ok(AGENT
        .get(url)
        .call()?
        .body_mut()
        .with_config()
        .limit(LIMIT)
        .read_to_string()?)
}

pub fn get_json(url: &str) -> Res<Value> {
    Ok(serde_json::from_str(&get_text(url)?)?)
}

/// Returns (bytes, content-type).
pub fn get_bytes(url: &str) -> Res<(Vec<u8>, String)> {
    let mut res = AGENT.get(url).call()?;
    let ct = res
        .headers()
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();
    Ok((res.body_mut().with_config().limit(LIMIT).read_to_vec()?, ct))
}

pub fn content_length(url: &str) -> Option<u64> {
    let res = AGENT.head(url).call().ok()?;
    res.headers().get("content-length")?.to_str().ok()?.parse().ok()
}

/// Data API items for `ids`, 50 per request.
fn youtube_items(key: &str, resource: &str, part: &str, ids: &[String]) -> Res<Vec<Value>> {
    let mut out = Vec::new();
    for chunk in ids.chunks(50) {
        let url = format!(
            "https://www.googleapis.com/youtube/v3/{resource}?part={part}&id={}&key={key}",
            chunk.join(",")
        );
        out.extend(get_json(&url)?["items"].as_array().cloned().unwrap_or_default());
    }
    Ok(out)
}

/// channel id -> API item (snippet + statistics).
pub fn youtube_channels(key: &str, ids: &[String]) -> Res<serde_json::Map<String, Value>> {
    Ok(youtube_items(key, "channels", "snippet,statistics", ids)?
        .into_iter()
        .filter_map(|item| Some((item["id"].as_str()?.to_string(), item)))
        .collect())
}

/// Video API items (snippet + liveStreamingDetails).
pub fn youtube_videos(key: &str, ids: &[String]) -> Res<Vec<Value>> {
    youtube_items(key, "videos", "snippet,liveStreamingDetails", ids)
}

/// Ids of videos from a channel's uploads and members-only feeds published on or after `since` (YYYY-MM-DD).
/// The feeds are fetched instead of the /live page, which YouTube hides behind a bot check for datacenter IPs
/// and which never shows members-only streams.
/// Each id comes with whether it is members-only.
pub fn recent_video_ids(channel: &str, since: &str) -> Res<Vec<(String, bool)>> {
    let rest = channel.strip_prefix("UC").ok_or("not a UC channel id")?;
    let feed = |list: &str| {
        get_text(&format!(
            "https://www.youtube.com/feeds/videos.xml?playlist_id={list}{rest}"
        ))
    };
    let mut ids: Vec<_> = parse_feed(&feed("UU")?, since)
        .into_iter()
        .map(|id| (id, false))
        .collect();
    // Channels without memberships have no members feed (404)
    let members = feed("UUMO").map(|x| parse_feed(&x, since)).unwrap_or_default();
    ids.extend(members.into_iter().map(|id| (id, true)));
    Ok(ids)
}

fn parse_feed(xml: &str, since: &str) -> Vec<String> {
    xml.split("<entry>")
        .skip(1)
        .filter_map(|entry| {
            let tag = |t: &str| Some(entry.split_once(&format!("<{t}>"))?.1.split_once('<')?.0);
            (tag("published")? >= since).then_some(tag("yt:videoId")?.to_string())
        })
        .collect()
}

/// The live stream, else the next upcoming one, from a channel's video items as `video`, or `null`.
pub fn pick_video(items: &[&Value], now: i64) -> Value {
    let start = |v: &Value| match v["snippet"]["liveBroadcastContent"].as_str()? {
        "live" => Some(0), // 0 == already live
        "upcoming" => parse_iso(v["liveStreamingDetails"]["scheduledStartTime"].as_str()?)
            // Skip far-future streams and long-overdue ones (permanent free-chat waiting rooms)
            .filter(|s| -6 * 3600 < s - now && s - now < 2 * 86400),
        _ => None,
    };
    let Some((video, start)) = items
        .iter()
        .filter_map(|v| Some((*v, start(v)?)))
        .min_by_key(|(_, s)| *s)
    else {
        return Value::Null;
    };
    let snippet = &video["snippet"];
    let id = video["id"].as_str().unwrap_or("");
    let thumbnail = ["maxres", "standard", "high", "medium", "default"]
        .iter()
        .find_map(|k| snippet["thumbnails"][k]["url"].as_str())
        .map_or_else(
            || format!("https://i.ytimg.com/vi/{id}/maxresdefault.jpg"),
            str::to_string,
        );
    json!({
        "id": id,
        "title": snippet["title"].as_str().unwrap_or(""),
        "start": start,
        "description": snippet["description"].as_str().unwrap_or(""),
        "thumbnail": thumbnail,
        "url": format!("https://youtu.be/{id}"),
    })
}

/// login -> `{"followers": n, "video": current stream as `video` or null}`.
pub fn twitch_users(logins: &[String]) -> Res<serde_json::Map<String, Value>> {
    let query = format!(
        "{{users(logins:{}){{login followers{{totalCount}} stream{{id title previewImageURL(width:1280,height:720)}}}}}}",
        serde_json::to_string(logins)?
    );
    let body = AGENT
        .post("https://gql.twitch.tv/gql")
        .header("Client-ID", TWITCH_CLIENT_ID)
        .header("Content-Type", "application/json")
        .send(json!({ "query": query }).to_string())?
        .body_mut()
        .read_to_string()?;
    Ok(parse_twitch(&serde_json::from_str(&body)?))
}

fn parse_twitch(res: &Value) -> serde_json::Map<String, Value> {
    res["data"]["users"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|u| {
            let (login, stream) = (u["login"].as_str()?, &u["stream"]);
            let video = stream["id"].as_str().map(|id| {
                json!({
                    "id": format!("twitch-{id}"),
                    "title": stream["title"].as_str().unwrap_or(""),
                    "start": 0,
                    "description": "",
                    "thumbnail": stream["previewImageURL"].as_str().unwrap_or(""),
                    "url": format!("https://www.twitch.tv/{login}"),
                })
            });
            let followers = u["followers"]["totalCount"].as_u64();
            Some((login.to_string(), json!({"followers": followers, "video": video})))
        })
        .collect()
}

/// (followers, avatar url) from FxTwitter's public API.
pub fn twitter_user(handle: &str) -> Res<(u64, Option<String>)> {
    let url = format!("https://api.fxtwitter.com/{handle}");
    // FxTwitter answers 404 now and then for accounts that exist, so retry before giving up
    let mut data = get_json(&url);
    for attempt in 1..3 {
        if data.is_ok() {
            break;
        }
        std::thread::sleep(Duration::from_secs(2 * attempt));
        data = get_json(&url);
    }
    let data = data?;
    let user = &data["user"];
    let followers = user["followers"].as_u64().ok_or("no follower count")?;
    let avatar = user["avatar_url"].as_str().map(|u| u.replace("_normal", ""));
    Ok((followers, avatar))
}

/// (followers, avatar url) from Bilibili's card API.
pub fn bilibili_user(uid: &str) -> Res<(u64, Option<String>)> {
    let data = get_json(&format!("https://api.bilibili.com/x/web-interface/card?mid={uid}"))?;
    let followers = data["data"]["follower"].as_u64().ok_or("no follower count")?;
    let face = data["data"]["card"]["face"]
        .as_str()
        .map(|u| u.replace("http://", "https://"));
    Ok((followers, face))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn video(id: &str, state: &str, scheduled: Option<&str>) -> Value {
        json!({"id": id, "snippet": {"title": id, "liveBroadcastContent": state},
               "liveStreamingDetails": {"scheduledStartTime": scheduled}})
    }

    #[test]
    fn picks_live_then_soonest_upcoming() {
        let now = 1_793_534_400; // 2026-11-01T12:00:00Z
        let soon = video("soon", "upcoming", Some("2026-11-01T13:00:00Z"));
        let later = video("later", "upcoming", Some("2026-11-02T10:00:00Z"));
        let far = video("far", "upcoming", Some("2026-11-05T12:00:00Z"));
        let stale = video("stale", "upcoming", Some("2026-10-01T12:00:00Z"));
        let live = video("live", "live", Some("2026-11-01T11:00:00Z"));
        let done = video("done", "none", None);

        let pick = pick_video(&[&later, &soon, &live, &done], now);
        assert_eq!((pick["id"].as_str(), pick["start"].as_i64()), (Some("live"), Some(0)));
        let pick = pick_video(&[&later, &soon, &far], now);
        assert_eq!(
            (pick["id"].as_str(), pick["start"].as_i64()),
            (Some("soon"), Some(now + 3600))
        );
        assert!(pick_video(&[&far, &stale, &done], now).is_null());
        assert!(pick_video(&[], now).is_null());
    }

    #[test]
    fn feed_ids_since() {
        let xml = "<feed><published>2020-01-01T00:00:00+00:00</published>\
            <entry><yt:videoId>new</yt:videoId><published>2026-10-31T11:51:36+00:00</published></entry>\
            <entry><yt:videoId>old</yt:videoId><published>2026-09-01T00:00:00+00:00</published></entry></feed>";
        assert_eq!(parse_feed(xml, "2026-10-18"), ["new"]);
    }

    #[test]
    fn twitch_users() {
        let res = json!({"data": {"users": [
            {"login": "liz", "followers": {"totalCount": 75}, "stream": {"id": "1", "title": "Karaoke", "previewImageURL": "p"}},
            {"login": "gigi", "followers": {"totalCount": 44}, "stream": null},
            null
        ]}});
        let users = parse_twitch(&res);
        assert_eq!(users.len(), 2);
        assert_eq!(users["liz"]["video"]["id"], "twitch-1");
        assert_eq!(users["liz"]["video"]["url"], "https://www.twitch.tv/liz");
        assert_eq!(
            (users["gigi"]["followers"].as_u64(), users["gigi"]["video"].is_null()),
            (Some(44), true)
        );
    }
}
