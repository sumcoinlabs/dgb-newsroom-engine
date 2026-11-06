# Crypto Newsroom Engine v0.4 — editorial intelligence and source health

Private, server-hosted crypto research desk for the DigiByte Wallet newsroom. **This is not an unattended public publisher.** The Mac app only opens SSH tunnels to the loopback-only VM; it does not have to remain online for monitoring or approved AI draft preparation.

## What v0.4 changes

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

- Private repository: `sumcoinlabs/dgb-newsroom-engine`.
- Server: `/opt/dgb-newsroom-engine`, service account `dgbnews`, persisted state `/var/lib/dgb-newsroom-engine`, secret file `/etc/dgb-newsroom-engine/groq.key`.
- Loopback-only server: `127.0.0.1:8770`, SSH-tunneled to Mac `http://127.0.0.1:8878/`.
- Original Article Editor: password-protected separate service at `127.0.0.1:8769`, tunneled to Mac `http://127.0.0.1:8877/`.
- Service: `systemctl status --no-pager dgb-newsroom-engine.service`.
- Health: `curl -s http://127.0.0.1:8770/api/health` and `/api/sources` (only locally via SSH).
- Tests: `python3 -m unittest discover -s tests -v` (20 tests in v0.4).

## Source hygiene

Feed URLs are explicit allowlisted HTTPS endpoints. The feed fetcher enforces same-publisher redirects, prohibits numeric IP hosts, caps response bytes and rejects XML DTD/entities. Only source headlines/excerpts/dates are read from public news sites. Source failures are isolated and recorded; previously collected leads remain intact. Generated content is an editorial working draft and must be reviewed before public publishing.

## Next safe milestones

1. Validate each source's real-world health and freshness on the live VM. Drop or replace those that fail consistently.
2. Complete the full manual editorial review of an automatically generated story and its art handoff to the editor.
3. Implement GitHub-first post-publication correction/retraction/restoration in a separately permissioned, tested root-owned publishing service, with explicit user confirmation and robust feed/sitemap updates.
4. Add authorized market/social trend integrations and official regulator data where permission/feeds allow, plus an integrated Search Console and AdSense reporting view.
5. Consider optional auto-publication only after reliable evidence verification, full rollback testing and user consent.
