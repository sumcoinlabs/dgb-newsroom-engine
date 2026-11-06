# DigiByte Newsroom Engine — v0.1

Private, source-linked story discovery for [DigiByte Wallet News](https://www.digibytewallet.org/news/).

## Shipped functionality

- Automatically checks **six official GitHub Atom feeds every 30 minutes**, while the server is running (no GitHub token required).
- Deduplicates leads into a local SQLite database, stores original URLs and timestamps, and shows a private browser dashboard.
- Accepts manually supplied URLs for Reddit, X, Facebook and selected DigiByte sources; **does not scrape these services**.
- Creates a conservative, attributed **working draft** with source and verification checklist. The copy is deliberately not represented as independently verified reporting.
- Can send a working draft to the existing private article editor, which prompts before importing; the existing editor still requires the user's password and final manual publication decision.
- Allows dismissing leads and basic public-page SEO checks. Research data stays outside GitHub.

## Deliberately not enabled yet

**No automatic publishing, generative AI account, image downloads, social-media scraping, automatic retractions, or direct access to the production webroot.** Do not market v0.1 as a completely automated news publisher.

## Architecture

- Private source repository: `sumcoinlabs/dgb-newsroom-engine` (GitHub).
- Server runtime: `/opt/dgb-newsroom-engine` (read-only files), service user `dgbnews`, state `/var/lib/dgb-newsroom-engine`.
- Systemd service: `dgb-newsroom-engine.service` on **127.0.0.1:8770 only**, and only while accessed through authenticated SSH tunneling on the user's Mac (`127.0.0.1:8878`).
- Public DigiByte site: **unchanged** by this component; no website write permissions.
- Article editor: existing root-owned service and password on 127.0.0.1:8769, tunneled to Mac port 8877. Engine handoff passes only editable draft fields via restricted browser postMessage; editor still requires password and explicit Save/Publish.

## Commands on server

```sh
systemctl status --no-pager dgb-newsroom-engine
journalctl -u dgb-newsroom-engine -n 40 --no-pager
sudo -u dgbnews DGB_ENGINE_STATE=/var/lib/dgb-newsroom-engine python3 /opt/dgb-newsroom-engine/engine.py scan
```

## Next engineering phases

1. Verified sources and an evidence scoring model (first-party announcements, commits, cross-checks), explicit editorial approval and deduplication across sources.
2. Authorized social integrations (X/Reddit/Facebook only where access permitted), periodic AI drafting with explicit credentials, controlled original artwork and citations.
3. Article update, correction, retraction and restoration with versioned GitHub-first deployment; SEO and AdSense reporting integrated with approved APIs.
4. End-to-end tests and a narrowly scoped optional auto-publish policy, disabled by default.

## Limits and safety notes

- RSS is source *discovery*, not proof that the claims in an entry are correct. A GitHub commit is not a release.
- Entries can be incomplete, stale or absent if GitHub serves an unavailable feed or rate-limits requests.
- Do not copy user-owned social photographs without a license or authorization.
- The monitor performs no write to public webroot and does not retain third-party images. Private story data is stored only under server state directory.
- `v0.1` source is intentionally not an API server available to the internet; tunnel access and origin/CSRF rules limit browser requests. Authorized server administrators can still access local services.
