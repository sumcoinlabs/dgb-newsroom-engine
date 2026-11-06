# Groq Research & Write — DigiByte Newsroom Engine v0.2

Your Mac opens the dashboard with the existing SSH tunnel. The service runs on the
DigiByte VM as the unprivileged user `dgbnews`. AI inference is performed by
GroqCloud's remote API.

## Security

- Enter your Groq API key into the **Mac installer prompt**, not a chat, command
  argument or GitHub file. The installer sends it once through your existing SSH
  connection to the server. The script does not save the key on the Mac.
- The key is stored at `/etc/dgb-newsroom-engine/groq.key`, `root:dgbnews 0640`.
  Rotate it in GroqCloud if exposed. Protect server root and SSH accounts.
- Groq may retain inputs and outputs for up to 30 days, unless Zero Data Retention
  has been enabled for your organization. Review https://console.groq.com/settings/data-controls
- Nothing in this engine can publish publicly: no write permissions to the webroot.
- The editor must still verify the original sources and add authorized original images.

## Use

1. Open `DigiByte Newsroom.app` and Story Radar at http://127.0.0.1:8878.
2. Choose a GitHub release or commit, and click **Create/Open working draft**.
3. Click **Research & Write with Groq**. This invokes the API once (subject to
   a daily maximum of 8 requests, 2 per story).
4. Review the new draft, including evidence and verification checklist.
5. Click **Send to Article Editor**, inspect it, and **Save draft**. Do **not**
   publish until it has been independently checked and an appropriate image added.

No API key or API usage comes from your Mac after setup. Public publication remains disabled.

## Check service on VM

```
systemctl status --no-pager dgb-newsroom-engine
curl --fail --silent http://127.0.0.1:8770/api/health
sudo -u dgbnews python3 /opt/dgb-newsroom-engine/engine.py status
```

The public GitHub source includes no secrets. The private story database stays
under `/var/lib/dgb-newsroom-engine/` and is preserved on upgrades.
