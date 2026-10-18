============
HololiveSubs
============

Website which tracks the YouTube, X and Bilibili follower counts of all Hololive talents, orders them by
YouTube subscribers and shows who is live or about to go live.

https://holo.naa.gg/

.. image:: www/website-screenshot.jpg
  :alt: Website Screenshot

How it works
============

One Rust binary serves the site and refreshes the data in a background thread:

- Every 30 min: subscriber counts and avatars from the YouTube Data API, X (through the public
  `FxTwitter <https://github.com/FixTweet/FxTwitter>`_ API) and Bilibili, plus a low-poly background per talent.
- Every 15 min: live and upcoming streams, read from each channel's ``/live`` page.
- After each run it writes ``stats.json``, per-talent calendars (``/events/<handle>.ics``), RSS feeds
  (``/rss/<handle>.xml``) and a daily snapshot (``/archive/stats-YYYY-MM-DD.json``) into ``DATA_DIR``.

The talent list lives in ``talents.json``; the frontend in ``www/``.

Running
=======

.. code-block:: sh

  YOUTUBE_KEY=... cargo run --release   # http://localhost:8080

Or with Docker (``ghcr.io/nachtalb/hololivesubs``), see ``docker-compose.yml``.

Environment: ``YOUTUBE_KEY`` (required), ``DATA_DIR`` (default ``data``), ``WWW_DIR`` (default ``www``),
``TALENTS`` (default ``talents.json``), ``PORT`` (default ``8080``), ``SITE_URL`` (used in feeds and calendars,
default ``https://holo.naa.gg``).

Tests: ``cargo test``.
