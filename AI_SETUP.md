# GroqCloud setup — Crypto Newsroom Engine v0.3

The existing Groq key stays on the DigiByte VM at `/etc/dgb-newsroom-engine/groq.key`. **Do not enter your key again** to upgrade to v0.3. The research engine sends only bounded source evidence to GroqCloud. All inference occurs remotely; your Mac is not running a model.

**Recommended Free project limits for `openai/gpt-oss-120b`:** 2 requests/minute, 8 requests/day, 8,000 tokens/minute, 50,000 tokens/day. The Groq project account must remain on Free; rate controls are not equivalent to billing controls. No paid fallback is configured. Groq may enforce different limits; check the console if calls are refused.

Software caps are 8 total requests/day, 2/story, 2 automatic/day; 50,000 observed tokens/day with a 10,000-token headroom check. Groq's own project limits are still the final safeguard. Errors count toward attempt limits to avoid repeated API retries. Automatic drafting is enabled by default, only for very recent, high-priority **official GitHub release/development** sources. Disable it with the dashboard toggle at any time. All automatic work is private and needs your editorial approval.

Original featured art is abstract artwork only. No web photos, screenshots, logos, or other third-party images are downloaded. Verify the final image context; publishing tools create three aspect ratios from the submitted original.

Corrected or retracted public articles require a future, separate versioned publication management system; do not alter public files manually or claim the research dashboard retracts public content.
