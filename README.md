# Crypto Newsroom Engine v0.6 — public source, private editorial control center

Private, server-hosted crypto research desk for the DigiByte Wallet newsroom. **This is not an unattended public publisher.** The Mac app only opens SSH tunnels to the loopback-only VM; it does not have to remain online for monitoring or approved AI draft preparation.

## New in v0.5

- **Clean new AI articles:** verification checklists and AI operation notes stay in private `verification` metadata, not the public Markdown. Historical v0.4 AI drafts are displayed cleanly without rewriting stored SQLite rows. New AI drafts require explicit human review in the Article Editor before publishing.
- **Better free-tier budgeting:** reserve 10,000 tokens per Groq attempt *before* calling the API, including uncertain failures; display conservative committed allowance separately from successfully reported model usage. Up to 8 daily requests, 2 automatic, and 2 per story. These software limits are NOT a billing guarantee: keep GroqCloud on Free and do not enable paid fallback. Responses are bounded to 2,800 completion tokens and 11,000 characters of evidence to reduce per-minute pressure.
- **Select better stories:** automatically skip prerelease, preview, beta/testnet, routine GitHub maintenance and broad unrelated Crypto-category leads. Official notable releases and security developments remain eligible; the news queue still contains other leads for manual review.
- **Original topic-aware artwork:** local 1600×1200 images contain topic and story-specific visual headlines, rather than anonymous generic circles. They remain illustrations, not event photos. The editor produces multiple image aspect ratios when manually publishing.
- **Persistent private editor sessions:** hashed sessions live in a root-only local SQLite file, invalidated when the editor password changes, expiring after 8 hours. The browser still requires an SSH tunnel and password when sessions expire.
- **Analytics and inventory:** new dashboard includes an honest read-only publication list and optional anonymous aggregate Nginx HTML-request counts by article, if site access logs are present. This is NOT a unique reader count, GA4 page_view event, Search Console impression/click, or AdSense revenue. No visitor identifiers are written to the aggregate. The one-shot report runs hourly through `dgb-newsroom-analytics.timer` when logs are found.
- **Safety:** existing public pages, saved drafts, and faucet are untouched by the installer. Public publishing is still manually approved. Corrections, scheduled release, retraction, restoration, GA4, Search Console and AdSense integrations are not yet implemented.

## Previous v0.4 foundation

- Expands the configured network from 16 to **35 feeds**, covering DigiByte, DigiDollar, Sumcoin, Bitcoin, Ethereum, Solana and Polkadot development; selected newsletters and crypto journalism. Some feeds may be empty, stale, blocked or unhealthy: the *Source health* panel exposes failures instead of implying every feed is operational.
- Checks sources concurrently with five bounded workers every 30 minutes, retains source/URL/timestamp, and records per-source scan status, last good response, last feed-entry date, counts and errors in the existing SQLite database.
- Separates newsworthy leads from older and off-topic material; adds a searchable archive, more careful topic attribution independent of publisher names, improved time-based priority, and cross-publisher grouping.
- Adds a polished private editorial dashboard: Ready for Review, fresh lead filters, topical search, 35-source health monitor, compact grouped story cards, and Groq request/token usage display.
- Keeps automatic research *enabled only if configured*: at most two fresh high-priority **official development** articles per UTC day; maximum eight Groq calls/day and 50,000 recorded tokens/day. Requests are only made from the server using its existing Groq key. No secondary paid model or silent billing fallback.
- Preserves existing private story DB, previous AI drafts, article editor draft records, article images, and public website. Removes the hard-coded Sumcoin-specific disclosure prompt; source attribution, truthful reporting, and editorial review remain required for all subjects.
- Maintains the preflight preview for publication metadata, original abstract image handoff, and GitHub-first manual publisher.

## What v0.4 does NOT do

- Does not automatically publish, edit, correct, retract or restore live articles. Those are separate high-risk publisher operations and are not represented as completed.
- Does not scrape, copy, or republish full articles or copyrighted photographs from third-party news websites.
- Does not automatically crawl social media platforms; users may still manually record allowed social links.
- Does not independently verify every AI-written claim, guarantee SEO placement, operate AdSense accounts, or provide definitive finance advice.

## Deployment

- Public source repository: `sumcoinlabs/dgb-newsroom-engine`. Credentials and drafts remain private on the VM.
- Server: `/opt/dgb-newsroom-engine`, service account `dgbnews`, persisted state `/var/lib/dgb-newsroom-engine`, secret file `/etc/dgb-newsroom-engine/groq.key`.
- Loopback-only server: `127.0.0.1:8770`, SSH-tunneled to Mac `http://127.0.0.1:8878/`.
- Original Article Editor: password-protected separate service at `127.0.0.1:8769`, tunneled to Mac `http://127.0.0.1:8877/`.
- Service: `systemctl status --no-pager dgb-newsroom-engine.service`.
- Health: `curl -s http://127.0.0.1:8770/api/health` and `/api/sources` (only locally via SSH).
- Tests: `python3 -m unittest discover -s tests -v` (26 tests in v0.5).

## Source hygiene

Feed URLs are explicit allowlisted HTTPS endpoints. The feed fetcher enforces same-publisher redirects, prohibits numeric IP hosts, caps response bytes and rejects XML DTD/entities. Only source headlines/excerpts/dates are read from public news sites. Source failures are isolated and recorded; previously collected leads remain intact. Generated content is an editorial working draft and must be reviewed before public publishing.

## Next safe milestones

1. Validate each source's real-world health and freshness on the live VM. Drop or replace those that fail consistently.
2. Complete the full manual editorial review of an automatically generated story and its art handoff to the editor.
3. Implement GitHub-first post-publication correction/retraction/restoration in a separately permissioned, tested root-owned publishing service, with explicit user confirmation and robust feed/sitemap updates.
4. Add authorized market/social trend integrations and official regulator data where permission/feeds allow, plus an integrated Search Console and AdSense reporting view.
5. Consider optional auto-publication only after reliable evidence verification, full rollback testing and user consent.
