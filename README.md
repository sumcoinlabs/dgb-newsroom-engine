# Crypto Newsroom Engine v0.3 — private multi-crypto research & review

Running exclusively on the existing DigiByte VM as unprivileged `dgbnews`, with GroqCloud API processing. Your Mac is a browser control surface only. No new domain, no public admin endpoint, no auto publishing.

## Installed capabilities

- Six existing DigiByte sources plus public Bitcoin Core, Ethereum Geth, Sumcoin Core/SumcoinLib GitHub sources, and selected crypto-publication RSS headline feeds (16 feeds total; the source configuration is the authority).
- Half-hourly RSS/Atom ingestion, persistent deduplication, topic classification, priority heuristics, and grouping of likely-related stories. These are **editorial signals, not proof of accuracy**.
- Automatic private Groq drafting for up to two eligible, recent, high-priority **first-party GitHub** items per UTC day; no AI calls for third-party RSS or manual social links. Always keeps the human-triggered Research & Write option.
- Hard software limits: 8 total Groq attempts/day; 2 attempts/story; 2 background attempts/day; 50,000 observed tokens/day with 10,000 token reservation before each call. The Groq Free account and project limits must also remain set; software alone cannot guarantee a zero-cost bill if you upgrade to paid billing.
- Isolated server-side generation of original abstract artwork (1600×1200 PNG), preview/download and automatic handoff to the private Article Editor. Generated art is **illustration**, not a screenshot or documentation of an event.
- Publication preflight: preliminary author/byline, publication-date policy, source timestamp, estimated word count, canonical, `NewsArticle` JSON-LD preview, and verification warnings. Actual publishing metadata remains owned by the existing article publisher.
- A private review queue, manual source intake, current daily Groq usage, topic filter, toggle for automatic research, basic live SEO check, private source links, and working-draft export.
- **No public site publication, deployment or retraction permissions** in this research engine. Article Editor still requires its password, explicit image review, manual save and publish approval.

## Editorial safety

Do **not** publish unverified AI text. Auto-generated work retains `EDITORIAL WORKING DRAFT — VERIFY BEFORE PUBLISHING`, which the Article Editor refuses to publish. Confirm the claims, status, sourcing, dates and release-specific assertions before rewriting/removing the warning. A GitHub commit or pull request is not an official shipped release. Article source dates are *not* the newsroom's publication date.

Third-party RSS feeds give discovery headlines/snippets only; this engine never scrapes those articles, social feeds or photographs for republication. Facebook, X and Reddit are manual links only until their authorized integrations are built. Neither SEO markup nor images guarantee Google News / Discover placement or monetization.

**Sumcoin disclosure:** The publisher is affiliated with Sumcoin. The AI prompt and generated Sumcoin drafts include a disclosure; preflight reminds you to preserve it on publication. No unsupported investment claims.

## Architecture and commands

- Private repository `sumcoinlabs/dgb-newsroom-engine` (GitHub).
- Source `/opt/dgb-newsroom-engine`, state SQLite & artwork `/var/lib/dgb-newsroom-engine`, Groq secret `/etc/dgb-newsroom-engine/groq.key` (root:dgbnews 0640).
- `dgb-newsroom-engine.service` listens only on `127.0.0.1:8770`; SSH to your Mac's `http://127.0.0.1:8878/`.
- Article Editor is the separate password-protected `http://127.0.0.1:8877/` service; original drafts and original images are unchanged unless explicitly saved.
- Mac app `DigiByte Newsroom.app` continues to open both local SSH tunnels.
- Server checks: `systemctl status --no-pager dgb-newsroom-engine` and `curl -s http://127.0.0.1:8770/api/health`.
- Tests: `python3 -m unittest discover -s tests -v`.

## Remaining roadmap — not shipped in v0.3

- Authorized social API monitoring, original independent reporting from multiple corroborated primary sources, fact-checking beyond source-bound warnings.
- Full article edit/correct/retract/restore in the password-protected publisher (these require reviewed GitHub-first state reconciliation, feed/sitemap changes, proper HTTP status and rollback testing).
- Verified AdSense slot configuration/analytics, Search Console data integration, richer content images and a real visual rendered-page preview.
- Optional unattended **public** publishing, only after a separate security and editorial review. It is permanently disabled in this version.
