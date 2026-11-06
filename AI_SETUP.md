# Groq research in v0.4

Groq inference runs in the cloud; the private research engine runs on the VM; the Mac is only a browser and SSH launcher.

Model: `openai/gpt-oss-120b`, chat completions API, JSON-only source-bounded drafting. Existing server-side key: `/etc/dgb-newsroom-engine/groq.key` (not stored in GitHub). Server rate limits: eight total calls/day, two automatic/day, two attempts per story and 50,000 measured tokens/day; reservation check prevents new requests near that daily limit. These do **not** guarantee $0 if an account leaves the Groq Free tier. Do not add billing to the project; remain on Free and limit usage in GroqCloud account settings.

Automatic research is restricted to recent high-priority primary-source releases or security/protocol developments. Human review and fact verification are mandatory. No public publishing is permitted by the research service. Source-fetched material is untrusted prompt data; any embedded commands are ignored. A Groq model may still make factual mistakes.

The engine does not require or insert a special Sumcoin ownership disclosure. It never makes claims of independent verification or unrelated ownership. Editors are responsible for accurate bylines and context.
