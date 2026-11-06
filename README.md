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

## v0.2: Groq-assisted Research & Write

An explicit **Research & Write with Groq** button in the private Story Radar draft dialog
calls GroqCloud from the **server**, not the Mac. The assistant is given a bounded,
source-attributed research package. For approved official GitHub URLs, the engine
reads the public release, commit or pull-request details from GitHub's official API.
For manual Reddit/X/Facebook leads it only uses the supplied title and note; it
**does not scrape social platforms** or pretend to have verified their content.

- Default model: `openai/gpt-oss-120b` through Groq's documented HTTPS chat-completions endpoint.
- Key file: `/etc/dgb-newsroom-engine/groq.key`, owned by `root:dgbnews`, mode `0640`.
  This key is never committed, sent to the browser, or put on the Mac's disk.
- Requested articles remain **editorial working drafts** and carry a publisher-blocking
  verification marker; you must verify, revise and manually publish in the existing
  separate password-protected Article Editor.
- AI requests are manual, no background AI API activity. Maximum 8 AI attempts per
  UTC day and 2 per story. Failed requests also count, to limit unexpected usage.
- On regeneration, Story Radar's own draft is replaced, but an existing saved
  Article Editor draft is never edited or published by this engine.
- Existing published articles, sitemap, public site and faucet are not touched.
- Optional privacy: enable Zero Data Retention in GroqCloud's Data Controls if available.
  Otherwise Groq may retain API inputs/outputs according to its policies.
- The initial API cannot verify all claims automatically; it is a drafting aide,
  not a fact-checking or autonomous-publication service.

See `AI_SETUP.md` for the install and test path.
