# Severity Definitions

## Findings Table

After all scans complete, present a consolidated findings table:

```
Security Audit Findings
═══════════════════════════════════════════════════════════════════════════════════
  #   Severity   Category            Finding                         Location
  1   CRITICAL   Secret detection    AWS access key hardcoded        src/config.ts:42
  2   CRITICAL   Dependency vuln     lodash CVE-2021-23337          package.json
  3   CRITICAL   CI trigger          PR head runs with secrets       .github/workflows/pr.yml:14
  4   HIGH       OWASP - SQLi        String concat in SQL query      api/users.ts:89
  5   HIGH       Auth                JWT secret hardcoded            lib/auth.ts:12
  6   MEDIUM     OWASP - XSS         dangerouslySetInnerHTML         components/Post.tsx:34
  7   MEDIUM     Env hygiene         .env not in .gitignore          .gitignore
  8   LOW        Transport           http:// URL in API call         services/external.ts:67
  9   LOW        Dependency          express 4.17.1 outdated         package.json
═══════════════════════════════════════════════════════════════════════════════════
```

## Severity Levels

- **CRITICAL** — Actively exploitable, immediate risk. Hardcoded secrets, RCE vectors, auth bypass.
- **HIGH** — Exploitable with moderate effort. SQLi, XSS, missing auth on sensitive endpoints.
- **MEDIUM** — Requires specific conditions to exploit. Missing security headers, overly broad CORS.
- **LOW** — Best practice violations, minor hygiene issues. Outdated deps without known CVEs, http:// for non-sensitive calls.

## CI Triggers (Category I)

Grade by what the outsider's code or text gets, following each chain to its end: an artifact or cache a privileged job uses, a runner a later job reuses.

- **CRITICAL** — a secret, a token with any write permission (`id-token: write` included), or a self-hosted runner that other jobs reuse.
- **HIGH** — code execution on a self-hosted runner that no other job reuses: the machine and its network, with no path to a secret.
- **MEDIUM** — outsider content reaches a privileged job that does not execute it yet: a pull request head checked out but only read, an artifact downloaded but only displayed.
- **LOW** — hardening with no outsider path: no `permissions:` under a read-and-write default, write scopes a job does not use, `persist-credentials` left on in a job that runs only the repository's own code.
