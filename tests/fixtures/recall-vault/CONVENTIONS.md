# Fleet conventions

- Prefer PKCE over implicit grant for any new OAuth flow.
- All retries are jittered exponential backoff, capped at 5 attempts.
- Rate-limit handling reads `Retry-After` before falling back to backoff.
