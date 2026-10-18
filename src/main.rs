//! Hololive Zone: collects subscriber counts and live streams, and serves the site.

mod art;
mod collect;
mod publish;
mod util;

use std::fs::File;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use serde_json::{Map, Value, json};
use tiny_http::{Header, Method, Request, Response, Server};

use util::{Res, iso_minutes, now, par_map};

const INTERVAL: Duration = Duration::from_secs(15 * 60); // live check; full update every 2nd run

struct Config {
    www: PathBuf,
    data: PathBuf,
    talents: PathBuf,
    site: String,
    youtube_key: String,
}

fn env(key: &str, default: &str) -> String {
    std::env::var(key)
        .ok()
        .filter(|v| !v.is_empty())
        .unwrap_or_else(|| default.to_string())
}

fn main() {
    let cfg = Arc::new(Config {
        www: env("WWW_DIR", "www").into(),
        data: env("DATA_DIR", "data").into(),
        talents: env("TALENTS", "talents.json").into(),
        site: env("SITE_URL", "https://holo.naa.gg").trim_end_matches('/').to_string(),
        youtube_key: env("YOUTUBE_KEY", ""),
    });
    if cfg.youtube_key.is_empty() {
        eprintln!("YOUTUBE_KEY is required");
        std::process::exit(1);
    }
    let port = env("PORT", "8080");
    let server = Arc::new(Server::http(format!("0.0.0.0:{port}")).expect("bind"));
    log!("Serving on :{port}");

    let updater = Arc::clone(&cfg);
    std::thread::spawn(move || updater_loop(&updater));

    let workers: Vec<_> = (0..4)
        .map(|_| {
            let (server, cfg) = (Arc::clone(&server), Arc::clone(&cfg));
            std::thread::spawn(move || {
                for req in server.incoming_requests() {
                    serve(&cfg, req);
                }
            })
        })
        .collect();
    for w in workers {
        let _ = w.join();
    }
}

// --- Updating ---------------------------------------------------------------------------------------------------------

fn updater_loop(cfg: &Config) {
    let mut run = 0u64;
    loop {
        let started = std::time::Instant::now();
        let stats = std::fs::read(cfg.data.join("stats.json"))
            .ok()
            .and_then(|b| serde_json::from_slice::<Value>(&b).ok());
        let result = match stats {
            Some(s) if run % 2 == 1 => update_live(s),
            _ => update_full(cfg),
        }
        .and_then(|s| publish::publish(&cfg.data, &cfg.site, &s));
        match result {
            Ok(()) => log!("Update done in {:.1}s", started.elapsed().as_secs_f32()),
            Err(e) => log!("Update failed: {e}"),
        }
        run += 1;
        std::thread::sleep(INTERVAL);
    }
}

fn str_of<'a>(v: &'a Value, key: &str) -> &'a str {
    v[key].as_str().unwrap_or("")
}

fn update_full(cfg: &Config) -> Res<Value> {
    log!("Full update");
    let config: Value = serde_json::from_slice(&std::fs::read(&cfg.talents)?)?;
    let talents = config["talents"].as_array().cloned().unwrap_or_default();
    let ids: Vec<String> = talents
        .iter()
        .map(|t| str_of(t, "youtube").to_string())
        .filter(|s| !s.is_empty())
        .collect();
    let channels = collect::youtube_channels(&cfg.youtube_key, &ids)?;
    // Last known X numbers, kept when FxTwitter fails for an account this round
    let previous: Value = std::fs::read(cfg.data.join("stats.json"))
        .ok()
        .and_then(|b| serde_json::from_slice(&b).ok())
        .unwrap_or_default();
    let previous: Map<String, Value> = publish::members(&previous)
        .map(|m| (str_of(m, "twitter").to_string(), m.clone()))
        .collect();

    let talents = par_map(&talents, 6, |talent| {
        let mut t = talent.as_object().cloned().unwrap_or_default();
        let name = str_of(talent, "name");
        let mut avatars = Vec::new();

        let handle = str_of(talent, "twitter");
        let mut x_failed = false;
        if !handle.is_empty() {
            match collect::twitter_user(handle) {
                Ok((followers, avatar)) => {
                    t.insert("twitter_subs".into(), followers.into());
                    avatars.extend(avatar);
                }
                Err(e) => {
                    log!("[{name}] X: {e}");
                    x_failed = true;
                    if let Some(subs) = previous.get(handle).map(|p| &p["twitter_subs"]).filter(|v| v.is_u64()) {
                        t.insert("twitter_subs".into(), subs.clone());
                    }
                }
            }
        }
        if let Some(ch) = channels.get(str_of(talent, "youtube")) {
            let stats = &ch["statistics"];
            if !stats["hiddenSubscriberCount"].as_bool().unwrap_or(false)
                && let Some(subs) = stats["subscriberCount"].as_str().and_then(|s| s.parse::<u64>().ok())
            {
                t.insert("youtube_subs".into(), subs.into());
            }
            let thumbs = &ch["snippet"]["thumbnails"];
            avatars.extend(
                ["high", "medium", "default"]
                    .iter()
                    .find_map(|k| thumbs[k]["url"].as_str())
                    .map(str::to_string),
            );
        }
        let bilibili = str_of(talent, "bilibili");
        if !bilibili.is_empty() {
            match collect::bilibili_user(bilibili) {
                Ok((followers, face)) => {
                    t.insert("bilibili_subs".into(), followers.into());
                    avatars.extend(face);
                }
                Err(e) => log!("[{name}] Bilibili: {e}"),
            }
        }
        // A failed X lookup keeps last round's (X) avatar instead of flapping to the YouTube one
        let kept = previous
            .get(handle)
            .filter(|p| x_failed && p["image"].as_str().is_some_and(|i| cfg.data.join(i).is_file()));
        if let Some(p) = kept {
            for k in ["image", "background_image", "rss_image"] {
                t.insert(k.into(), p[k].clone());
            }
        } else {
            let images = avatars
                .iter()
                .find_map(|url| match art::profile_images(&cfg.data, url) {
                    Ok(i) => Some(i),
                    Err(e) => {
                        log!("[{name}] image {url}: {e}");
                        None
                    }
                });
            t.insert("image".into(), images.as_ref().map(|i| i.image.clone()).into());
            t.insert(
                "background_image".into(),
                images.as_ref().map(|i| i.background.clone()).into(),
            );
            t.insert("rss_image".into(), images.as_ref().map(|i| i.rss.clone()).into());
        }
        let mut talent = Value::Object(t);
        talent["video"] = video_for(&talent);
        talent
    });

    let mut groups: Map<String, Value> = config["groups"].as_object().cloned().unwrap_or_default();
    let mut sorted = talents;
    let key = |t: &Value| {
        ["youtube_subs", "twitter_subs", "bilibili_subs"]
            .iter()
            .find_map(|k| t[k].as_u64())
            .unwrap_or(0)
    };
    sorted.sort_by_key(|t| std::cmp::Reverse(key(t)));
    for t in sorted {
        let group = t["group"].as_str().unwrap_or("talents").to_string();
        if let Some(members) = groups.get_mut(&group).and_then(|g| g["members"].as_array_mut()) {
            members.push(t);
        }
    }
    let stamp = iso_minutes(now());
    Ok(json!({"groups": groups, "meta": {"subsLastUpdate": stamp, "liveEventsLastUpdate": stamp}}))
}

fn video_for(member: &Value) -> Value {
    let channel = str_of(member, "youtube");
    if channel.is_empty() || member["retired"].as_bool().unwrap_or(false) {
        return Value::Null;
    }
    collect::live_video(channel).unwrap_or_else(|e| {
        log!("[{}] live check: {e}", str_of(member, "name"));
        Value::Null
    })
}

fn update_live(mut stats: Value) -> Res<Value> {
    log!("Live update");
    let videos: Vec<Value> = par_map(&publish::members(&stats).cloned().collect::<Vec<_>>(), 6, video_for);
    let mut videos = videos.into_iter();
    for group in stats["groups"].as_object_mut().into_iter().flat_map(|g| g.values_mut()) {
        for m in group["members"].as_array_mut().into_iter().flatten() {
            m["video"] = videos.next().unwrap_or(Value::Null);
        }
    }
    stats["meta"]["liveEventsLastUpdate"] = iso_minutes(now()).into();
    Ok(stats)
}

// --- Serving ----------------------------------------------------------------------------------------------------------

fn content_type(path: &Path) -> &'static str {
    match path.extension().and_then(|e| e.to_str()).unwrap_or("") {
        "html" => "text/html; charset=utf-8",
        "js" => "text/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "json" => "application/json",
        "webmanifest" => "application/manifest+json",
        "ics" => "text/calendar; charset=utf-8",
        "xml" => "application/rss+xml; charset=utf-8",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "ico" => "image/x-icon",
        "woff" => "font/woff",
        "woff2" => "font/woff2",
        "zip" => "application/zip",
        _ => "application/octet-stream",
    }
}

fn header(k: &str, v: &str) -> Header {
    Header::from_bytes(k.as_bytes(), v.as_bytes()).expect("valid header")
}

/// Generated files (stats, events, rss, images, archive) from DATA_DIR, everything else from WWW_DIR.
fn resolve(cfg: &Config, url_path: &str) -> Option<PathBuf> {
    let rel: Vec<&str> = url_path.split('/').filter(|s| !s.is_empty()).collect();
    if rel.iter().any(|s| *s == ".." || s.starts_with('.') || s.contains('\\')) {
        return None;
    }
    let rel = rel.join("/");
    if rel.is_empty() {
        return Some(cfg.www.join("index.html"));
    }
    [cfg.data.join(&rel), cfg.www.join(&rel)]
        .into_iter()
        .find(|p| p.exists())
}

fn listing(dir: &Path, url_path: &str) -> String {
    let mut names: Vec<String> = std::fs::read_dir(dir)
        .map(|r| {
            r.flatten()
                .map(|e| e.file_name().to_string_lossy().into_owned() + if e.path().is_dir() { "/" } else { "" })
                .filter(|n| !n.starts_with('.') && !n.ends_with(".tmp"))
                .collect()
        })
        .unwrap_or_default();
    names.sort();
    let items: String = names
        .iter()
        .map(|n| format!("<li><a href=\"{n}\">{n}</a></li>\n"))
        .collect();
    format!(
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>Index of {url_path}</title></head>\
         <body><h1>Index of {url_path}</h1><ul>\n{items}</ul></body></html>"
    )
}

fn serve(cfg: &Config, req: Request) {
    let url_path = req.url().split(['?', '#']).next().unwrap_or("/").to_string();
    if !matches!(req.method(), Method::Get | Method::Head) {
        let _ = req.respond(Response::from_string("method not allowed").with_status_code(405));
        return;
    }
    if url_path == "/healthz" {
        let ok = cfg.data.join("stats.json").is_file();
        let _ = req.respond(
            Response::from_string(if ok { "ok" } else { "no data yet" }).with_status_code(if ok { 200 } else { 503 }),
        );
        return;
    }
    let Some(path) = resolve(cfg, &url_path) else {
        let _ = req.respond(Response::from_string("not found").with_status_code(404));
        return;
    };
    if path.is_dir() {
        if !url_path.ends_with('/') {
            let _ = req.respond(Response::empty(301).with_header(header("Location", &format!("{url_path}/"))));
            return;
        }
        let index = path.join("index.html");
        if !index.is_file() {
            let body = listing(&path, &url_path);
            let _ = req.respond(
                Response::from_string(body)
                    .with_header(header("Content-Type", "text/html; charset=utf-8"))
                    .with_header(header("Cache-Control", "no-cache")),
            );
            return;
        }
        return send_file(req, &index);
    }
    send_file(req, &path);
}

fn send_file(req: Request, path: &Path) {
    let Ok(file) = File::open(path) else {
        let _ = req.respond(Response::from_string("not found").with_status_code(404));
        return;
    };
    let ct = content_type(path);
    let cache = if ct.starts_with("image/") || ct.starts_with("font/") {
        "public, max-age=86400"
    } else {
        "no-cache"
    };
    let _ = req.respond(
        Response::from_file(file)
            .with_header(header("Content-Type", ct))
            .with_header(header("Cache-Control", cache)),
    );
}
