# Newsroom v0.6 — editorial diagnostics and opt-in Google reporting

Based strictly on engine v0.5 commit `47835f6` (Nov 6, 2026). This repository is now **public source code**. Never place Groq keys, Google OAuth tokens, editor passwords, private drafts, user information or other credentials in the public Git repository.

## New in this incremental release

- `/api/quality` reports review flags on stored drafts: legacy notices, source-link presence, ambiguous prerelease claims, promotional absolutes, length, pending human acknowledgement, and potential published-story overlaps. Warnings are **not factual verification** and do not permit automatic publishing.
- `/api/source-audit` explains the health of the 35 feeds using existing scan records, without silently changing source URLs. A stale official release feed might simply be inactive; verify upstream before removing it.
- v0.6 topic/event-informed original 1600×1200 PNG art uses Pillow and installed system fonts when available. No external copyrighted imagery or company marks. A preexisting stdlib v0.5 renderer remains fallback if Pillow is unavailable.
- Google reporting integration is **opt-in** and read-only: GA4 page views and active users, Search Console newsroom search traffic, AdSense account-wide earnings. Until OAuth is authorized, dashboard says **Not connected**; Nginx request estimates remain separate from GA4 users.
- Article Editor displays a source-vs-live published article audit, with links to public article and editable source manuscript. Corrections, scheduling, retractions and restoration are **not yet enabled**; the tool never changes published pages on its own.
- No changes to public HTML, `/faucet/`, private draft SQLite, Groq key, or human-approval publishing behavior.

## Connecting Google APIs (owner action, not automatic)

Enable the Analytics Data API, Google Search Console API, and AdSense Management API in the appropriate Google Cloud project. Create an OAuth consent/client configuration, authorize **read-only** scopes (`analytics.readonly`, `webmasters.readonly`, `adsense.readonly`) through Google's own consent flow, and grant that Google identity access to the GA4 property, Search Console property, and AdSense account. This installer cannot log you in, create an OAuth refresh token, or determine your property/account IDs.

Once you have authorized the accounts, the server-only configuration path is `/etc/dgb-newsroom-engine/google-integrations.json`, owned by `root:dgbnews` with mode `0640`. Never commit or paste the real values into chat or GitHub. Example **keys** (use actual secure values locally):

```json
{
  "client_id": "REPLACE_USING_LOCAL_GOOGLE_CONSOLE",
  "client_secret": "REPLACE_USING_LOCAL_GOOGLE_CONSOLE",
  "refresh_token": "REPLACE_USING_LOCAL_GOOGLE_CONSENT",
  "ga4_property_id": "REPLACE_NUMERIC_GA4_PROPERTY_ID",
  "gsc_site": "sc-domain:digibytewallet.org",
  "adsense_account": "accounts/pub-REPLACE_PUBLISHER_ID"
}
```

The separate `dgb-newsroom-google-v06.timer` polls every 6 hours, runs only on the server, and writes **aggregated read-only** values to `/var/lib/dgb-newsroom-engine/google-summary-v06.json` with no tokens. Any missing or unauthorized provider remains marked unconnected. GA4 and Search Console numbers differ from server request estimates; AdSense earnings are account-wide estimates, not newsroom-only revenue. Credential scopes are restricted by Google's actual grant, not by the JSON schema alone.

**Important:** The automated news publisher remains OFF. Do not enable it based on these diagnostics. Corrections/retractions require a separate reviewed, reversible lifecycle implementation; v0.6 provides read-only publication management only.

## Smoke tests

- `python3 -m unittest discover -s tests -v` (v0.5 and v0.6 tests)
- `curl http://127.0.0.1:8770/api/health` (SSH loopback only)
- `curl http://127.0.0.1:8770/api/source-audit` and `/api/google-metrics` (SSH loopback only)
- `curl http://127.0.0.1:8769/api/published-control-v06` requires the existing editor password/session and returns 401 when signed out.
