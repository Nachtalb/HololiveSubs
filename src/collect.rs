//! Data sources: YouTube Data API, YouTube /live pages, X (via FxTwitter) and Bilibili.

use std::sync::LazyLock;
use std::time::Duration;

use serde_json::{Value, json};

use crate::util::{Res, now};

const UA: &str =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36";
const YT_COOKIE: &str = "CONSENT=YES+926; SOCS=CAESEwgDEgk1NjQ0NjAzMDMaAmVuIAEaBgiA1P6nBg";
const LIMIT: u64 = 20 << 20;

static AGENT: LazyLock<ureq::Agent> = LazyLock::new(|| {
    ureq::Agent::config_builder()
        .timeout_global(Some(Duration::from_secs(30)))
        .user_agent(UA)
        .build()
        .into()
});

pub fn get_text(url: &str, cookie: Option<&str>) -> Res<String> {
    let mut req = AGENT.get(url);
    if let Some(c) = cookie {
        req = req.header("Cookie", c);
    }
    Ok(req.call()?.body_mut().with_config().limit(LIMIT).read_to_string()?)
}

pub fn get_json(url: &str) -> Res<Value> {
    Ok(serde_json::from_str(&get_text(url, None)?)?)
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

/// channel id -> API item (snippet + statistics), 50 ids per request.
pub fn youtube_channels(key: &str, ids: &[String]) -> Res<serde_json::Map<String, Value>> {
    let mut out = serde_json::Map::new();
    for chunk in ids.chunks(50) {
        let url = format!(
            "https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&id={}&key={key}",
            chunk.join(",")
        );
        for item in get_json(&url)?["items"].as_array().cloned().unwrap_or_default() {
            if let Some(id) = item["id"].as_str() {
                out.insert(id.to_string(), item.clone());
            }
        }
    }
    Ok(out)
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

pub fn live_video(channel: &str) -> Res<Value> {
    let html = get_text(
        &format!("https://www.youtube.com/channel/{channel}/live"),
        Some(YT_COOKIE),
    )?;
    Ok(parse_live(&html, now()))
}

/// Extracts the live or upcoming stream from a channel's /live page, or `null`.
pub fn parse_live(html: &str, now: i64) -> Value {
    const MARKER: &str = "var ytInitialPlayerResponse = ";
    let Some(start) = html.find(MARKER) else {
        return Value::Null;
    };
    let mut stream = serde_json::Deserializer::from_str(&html[start + MARKER.len()..]).into_iter::<Value>();
    let Some(Ok(player)) = stream.next() else {
        return Value::Null;
    };

    let details = &player["videoDetails"];
    let Some(id) = details["videoId"].as_str() else {
        return Value::Null;
    };
    let is_live = details["isLive"].as_bool().unwrap_or(false);
    if !is_live && !details["isUpcoming"].as_bool().unwrap_or(false) {
        return Value::Null;
    }
    let scheduled = player["playabilityStatus"]["liveStreamability"]["liveStreamabilityRenderer"]["offlineSlate"]
        ["liveStreamOfflineSlateRenderer"]["scheduledStartTime"]
        .as_str()
        .and_then(|s| s.parse::<i64>().ok())
        .unwrap_or(0); // 0 == already live
    // Skip far-future streams and long-overdue "upcoming" ones (permanent free-chat waiting rooms)
    if !is_live && !(-6 * 3600 < scheduled - now && scheduled - now < 2 * 86400) {
        return Value::Null;
    }
    let thumbnail = details["thumbnail"]["thumbnails"]
        .as_array()
        .and_then(|t| t.last())
        .and_then(|t| t["url"].as_str())
        .map_or_else(
            || format!("https://i.ytimg.com/vi/{id}/maxresdefault.jpg"),
            str::to_string,
        );
    json!({
        "id": id,
        "title": details["title"].as_str().unwrap_or(""),
        "start": scheduled,
        "description": details["shortDescription"].as_str().unwrap_or(""),
        "thumbnail": thumbnail,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn page(details: Value, start: Option<i64>) -> String {
        let mut player = json!({ "videoDetails": details });
        if let Some(s) = start {
            player["playabilityStatus"] = json!({"liveStreamability": {"liveStreamabilityRenderer": {"offlineSlate":
                {"liveStreamOfflineSlateRenderer": {"scheduledStartTime": s.to_string()}}}}});
        }
        format!("<script>var ytInitialPlayerResponse = {player};var x = {{}};</script>")
    }

    #[test]
    fn live_detection() {
        let now = 1_800_000_000;
        let live = parse_live(&page(json!({"videoId": "a", "title": "t", "isLive": true}), None), now);
        assert_eq!((live["id"].as_str(), live["start"].as_i64()), (Some("a"), Some(0)));
        let soon = parse_live(
            &page(json!({"videoId": "b", "isUpcoming": true}), Some(now + 3600)),
            now,
        );
        assert_eq!(soon["start"].as_i64(), Some(now + 3600));
        assert!(
            parse_live(
                &page(json!({"videoId": "c", "isUpcoming": true}), Some(now + 5 * 86400)),
                now
            )
            .is_null()
        );
        assert!(
            parse_live(
                &page(json!({"videoId": "d", "isUpcoming": true}), Some(now - 30 * 86400)),
                now
            )
            .is_null()
        );
        assert!(parse_live(&page(json!({"videoId": "e"}), None), now).is_null());
        assert!(parse_live("<html>nothing</html>", now).is_null());
    }
}
