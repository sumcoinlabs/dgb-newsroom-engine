# Changelog

## v0.4.0 — editorial intelligence and dashboard polish

- Add 19 feeds, for 35 configured sources with per-source health recording.
- Add bounded five-worker source fetching and same-publisher redirect enforcement.
- Correct topic classification independent of a news publisher's name.
- Separate archival/off-topic stories from the fresh prioritized queue.
- Improve grouping, priority, and automatic primary-source draft selection.
- Build a redesigned responsive dashboard with search, source health, AI draft review cards, and clearer metadata.
- Reuse existing Groq credential, database, draft handoff, artwork generation and manual publishing requirements.
- Remove mandatory Sumcoin-specific ownership-disclosure injection, preserving universal source attribution and truthful claims.
- Add seven regression tests; 20 tests total.

No automatic publication, source scraping, retraction or live-site modifications.
