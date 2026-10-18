//! Profile image cache, low-poly backgrounds (Delaunay) and the RSS feed artwork.

use std::io::Cursor;
use std::path::Path;

use image::codecs::jpeg::JpegEncoder;
use image::imageops::{self, FilterType};
use image::{ImageFormat, Rgb, RgbImage, Rgba, RgbaImage};

use crate::collect;
use crate::util::{Res, short_hash, write_atomic};

/// Site-relative paths of the cached avatar, its low-poly background and the RSS artwork.
pub struct Images {
    pub image: String,
    pub background: String,
    pub rss: String,
}

/// Downloads the avatar once per URL and derives the other images from it.
pub fn profile_images(data: &Path, url: &str) -> Res<Images> {
    let stem = short_hash(url);
    let dir = data.join("profile-images");
    let existing = std::fs::read_dir(&dir).ok().and_then(|entries| {
        entries
            .flatten()
            .map(|e| e.file_name().to_string_lossy().into_owned())
            .find(|n| n.starts_with(&stem) && !n.contains('_') && !n.ends_with(".tmp"))
    });
    let name = match existing {
        Some(n) => n,
        None => {
            let (bytes, ct) = collect::get_bytes(url)?;
            let ext = match image::guess_format(&bytes) {
                Ok(ImageFormat::Png) => "png",
                Ok(ImageFormat::WebP) => "webp",
                Ok(ImageFormat::Jpeg) => "jpg",
                _ => return Err(format!("not an image ({ct})").into()),
            };
            let name = format!("{stem}.{ext}");
            write_atomic(&dir.join(&name), &bytes)?;
            name
        }
    };
    let background = format!("{stem}_lowpoly.jpg");
    let rss = format!("{stem}_feed.png");
    if !dir.join(&background).is_file() || !dir.join(&rss).is_file() {
        let avatar = image::open(dir.join(&name))?.to_rgb8();
        let bg = low_poly(
            &imageops::resize(&avatar, 400, 400, FilterType::Triangle),
            150,
            10,
            &stem,
        );
        let mut jpg = Vec::new();
        JpegEncoder::new_with_quality(&mut jpg, 85).encode_image(&bg)?;
        write_atomic(&dir.join(&background), &jpg)?;
        let mut png = Vec::new();
        rss_artwork(&avatar, &bg).write_to(&mut Cursor::new(&mut png), ImageFormat::Png)?;
        write_atomic(&dir.join(&rss), &png)?;
    }
    Ok(Images {
        image: format!("profile-images/{name}"),
        background: format!("profile-images/{background}"),
        rss: format!("profile-images/{rss}"),
    })
}

/// Same idea as triangulate-tool: `points` random points plus `per_side` on every edge,
/// Delaunay-triangulated, each triangle filled with the average colour underneath it.
pub fn low_poly(src: &RgbImage, points: usize, per_side: usize, seed: &str) -> RgbImage {
    let pts = sample_points(
        f64::from(src.width() - 1),
        f64::from(src.height() - 1),
        points,
        per_side,
        seed,
    );

    let mut out = RgbImage::new(src.width(), src.height());
    for [a, b, c] in delaunay(&pts) {
        let tri = [pts[a], pts[b], pts[c]];
        let inside = |x: u32, y: u32| {
            let p = (f64::from(x), f64::from(y));
            let e = |(ax, ay): (f64, f64), (bx, by): (f64, f64)| (bx - ax) * (p.1 - ay) - (by - ay) * (p.0 - ax);
            let (d0, d1, d2) = (e(tri[0], tri[1]), e(tri[1], tri[2]), e(tri[2], tri[0]));
            (d0 >= 0.0 && d1 >= 0.0 && d2 >= 0.0) || (d0 <= 0.0 && d1 <= 0.0 && d2 <= 0.0)
        };
        let x0 = tri.iter().map(|p| p.0).fold(f64::MAX, f64::min).floor().max(0.0) as u32;
        let x1 = (tri.iter().map(|p| p.0).fold(0.0, f64::max).ceil() as u32).min(src.width() - 1);
        let y0 = tri.iter().map(|p| p.1).fold(f64::MAX, f64::min).floor().max(0.0) as u32;
        let y1 = (tri.iter().map(|p| p.1).fold(0.0, f64::max).ceil() as u32).min(src.height() - 1);
        let (mut sum, mut n) = ([0u64; 3], 0u64);
        for y in y0..=y1 {
            for x in x0..=x1 {
                if inside(x, y) {
                    let Rgb(px) = src.get_pixel(x, y);
                    (0..3).for_each(|i| sum[i] += u64::from(px[i]));
                    n += 1;
                }
            }
        }
        if n == 0 {
            continue;
        }
        let colour = Rgb(sum.map(|s| (s / n) as u8));
        for y in y0..=y1 {
            for x in x0..=x1 {
                if inside(x, y) {
                    out.put_pixel(x, y, colour);
                }
            }
        }
    }
    out
}

/// The 4 corners, `per_side` evenly spaced points on every edge and `points` random ones inside.
fn sample_points(mx: f64, my: f64, points: usize, per_side: usize, seed: &str) -> Vec<(f64, f64)> {
    let mut rng = seed.bytes().fold(0x9E37_79B9_7F4A_7C15u64, |a, b| {
        (a ^ u64::from(b)).wrapping_mul(0x100_0000_01B3)
    });
    let mut rand = move || {
        rng ^= rng << 13;
        rng ^= rng >> 7;
        rng ^= rng << 17;
        (rng >> 11) as f64 / (1u64 << 53) as f64
    };
    let mut pts = vec![(0.0, 0.0), (mx, 0.0), (0.0, my), (mx, my)];
    for i in 1..=per_side {
        let t = i as f64 / (per_side + 1) as f64;
        pts.extend([(t * mx, 0.0), (t * mx, my), (0.0, t * my), (mx, t * my)]);
    }
    pts.extend((0..points).map(|_| (rand() * mx, rand() * my)));
    pts
}

/// Bowyer-Watson. Returns triangles as index triples into `pts`.
fn delaunay(pts: &[(f64, f64)]) -> Vec<[usize; 3]> {
    let n = pts.len();
    let span = pts.iter().fold(1.0f64, |m, p| m.max(p.0.abs()).max(p.1.abs())) * 20.0;
    let mut all = pts.to_vec();
    all.extend([(-span, -span), (span, -span), (0.0, span)]);
    let circum = |t: &[usize; 3]| {
        let (a, b, c) = (all[t[0]], all[t[1]], all[t[2]]);
        let d = 2.0 * (a.0 * (b.1 - c.1) + b.0 * (c.1 - a.1) + c.0 * (a.1 - b.1));
        let sq = |p: (f64, f64)| p.0 * p.0 + p.1 * p.1;
        let ux = (sq(a) * (b.1 - c.1) + sq(b) * (c.1 - a.1) + sq(c) * (a.1 - b.1)) / d;
        let uy = (sq(a) * (c.0 - b.0) + sq(b) * (a.0 - c.0) + sq(c) * (b.0 - a.0)) / d;
        if d.abs() < 1e-9 {
            return (0.0, 0.0, f64::INFINITY); // degenerate (collinear) triangle: always replace it
        }
        (ux, uy, (a.0 - ux).powi(2) + (a.1 - uy).powi(2))
    };
    // Strictly-inside test: corner and edge points are co-circular, and treating "on the circle" as bad
    // makes the cavity non-star-shaped, which produces overlapping triangles.
    let mut tris: Vec<([usize; 3], (f64, f64, f64))> = vec![([n, n + 1, n + 2], circum(&[n, n + 1, n + 2]))];
    for (i, &p) in all.iter().enumerate().take(n) {
        let (bad, good): (Vec<_>, Vec<_>) = tris
            .into_iter()
            .partition(|(_, (x, y, r2))| (p.0 - x).powi(2) + (p.1 - y).powi(2) < r2 * (1.0 - 1e-12));
        tris = good;
        let edges: Vec<(usize, usize)> = bad
            .iter()
            .flat_map(|(t, _)| [(t[0], t[1]), (t[1], t[2]), (t[2], t[0])])
            .collect();
        let same = |a: &(usize, usize), b: &(usize, usize)| (a.0 == b.0 && a.1 == b.1) || (a.0 == b.1 && a.1 == b.0);
        for e in &edges {
            if edges.iter().filter(|o| same(e, o)).count() == 1 {
                let t = [e.0, e.1, i];
                tris.push((t, circum(&t)));
            }
        }
    }
    tris.into_iter()
        .map(|(t, _)| t)
        .filter(|t| t.iter().all(|&v| v < n))
        .collect()
}

/// 144x400 strip of the background with the round avatar in the middle (RSS channel image).
pub fn rss_artwork(avatar: &RgbImage, background: &RgbImage) -> RgbaImage {
    let bg = imageops::resize(background, 400, 400, FilterType::Lanczos3);
    let mut out = RgbaImage::from_fn(144, 400, |x, y| {
        let Rgb([r, g, b]) = *bg.get_pixel(x + 128, y);
        Rgba([r, g, b, 255])
    });
    let size = 120u32;
    let face = imageops::resize(avatar, size, size, FilterType::Lanczos3);
    let (ox, oy) = ((144 - size) / 2, (400 - size) / 2);
    let r = f64::from(size) / 2.0;
    for (x, y, Rgb([pr, pg, pb])) in face.enumerate_pixels() {
        let d = ((f64::from(x) + 0.5 - r).powi(2) + (f64::from(y) + 0.5 - r).powi(2)).sqrt();
        let alpha = (r - 1.0 - d).clamp(0.0, 1.0); // 1px anti-aliased edge
        let dst = out.get_pixel_mut(ox + x, oy + y);
        let mix = |a: u8, b: u8| (f64::from(a) * alpha + f64::from(b) * (1.0 - alpha)).round() as u8;
        *dst = Rgba([mix(*pr, dst[0]), mix(*pg, dst[1]), mix(*pb, dst[2]), 255]);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn low_poly_covers_everything() {
        let src = RgbImage::from_pixel(100, 100, Rgb([10, 20, 30]));
        let out = low_poly(&src, 150, 10, "seed");
        assert!(
            out.pixels().all(|p| *p == Rgb([10, 20, 30])),
            "every pixel belongs to a triangle"
        );
    }

    #[test]
    fn delaunay_square() {
        let tris = delaunay(&[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]);
        assert_eq!(tris.len(), 2);
    }

    /// The triangles must tile the rectangle exactly: no overlaps (area sum) and no holes (count).
    #[test]
    fn delaunay_tiles_the_rectangle() {
        for seed in ["e031604b264c7c0f", "seed", "x"] {
            let pts = sample_points(399.0, 399.0, 150, 10, seed);
            let tris = delaunay(&pts);
            let area: f64 = tris
                .iter()
                .map(|t| {
                    let (a, b, c) = (pts[t[0]], pts[t[1]], pts[t[2]]);
                    ((b.0 - a.0) * (c.1 - a.1) - (c.0 - a.0) * (b.1 - a.1)).abs() / 2.0
                })
                .sum();
            assert!((area - 399.0 * 399.0).abs() < 1e-3, "{seed}: area {area}");
            let hull = 4 + 4 * 10; // every corner and edge point is on the hull
            assert_eq!(tris.len(), 2 * pts.len() - hull - 2, "{seed}: Euler count");
        }
    }

    #[test]
    fn low_poly_triangles_are_flat_and_distinct() {
        // gradient source: overlapping triangles would show up as more distinct colours than triangles
        let src = RgbImage::from_fn(400, 400, |x, y| {
            Rgb([(x * 255 / 399) as u8, (y * 255 / 399) as u8, 128])
        });
        let out = low_poly(&src, 150, 10, "seed");
        let mut colours: Vec<_> = out.pixels().map(|p| p.0).collect();
        colours.sort_unstable();
        colours.dedup();
        assert!(colours.len() <= 342, "{} colours for 342 triangles", colours.len());
        assert!(colours.len() > 250);
        assert!(!colours.contains(&[0, 0, 0]), "no uncovered (black) pixels");
    }

    #[test]
    fn rss_artwork_shape() {
        let out = rss_artwork(
            &RgbImage::from_pixel(50, 50, Rgb([255, 0, 0])),
            &RgbImage::new(400, 400),
        );
        assert_eq!(out.dimensions(), (144, 400));
        assert_eq!(*out.get_pixel(72, 200), Rgba([255, 0, 0, 255]));
        assert_eq!(*out.get_pixel(0, 0), Rgba([0, 0, 0, 255]));
    }
}
