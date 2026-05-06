# Severity Definitions

## Findings Table

After all scans complete, present a consolidated findings table:

```
Security Audit Findings
═══════════════════════════════════════════════════════════════════════════════════
  #   Severity   Category            Finding                         Location
  1   CRITICAL   Secret detection    AWS access key hardcoded        src/config.ts:42
  2   CRITICAL   Dependency vuln     lodash CVE-2021-23337          package.json
  3   HIGH       OWASP - SQLi        String concat in SQL query      api/users.ts:89
  4   HIGH       Auth                JWT secret hardcoded            lib/auth.ts:12
  5   MEDIUM     OWASP - XSS         dangerouslySetInnerHTML         components/Post.tsx:34
  6   MEDIUM     Env hygiene         .env not in .gitignore          .gitignore
  7   LOW        Transport           http:// URL in API call         services/external.ts:67
  8   LOW        Dependency          express 4.17.1 outdated         package.json
═══════════════════════════════════════════════════════════════════════════════════
```

## Severity Levels

- **CRITICAL** — Actively exploitable, immediate risk. Hardcoded secrets, RCE vectors, auth bypass.
- **HIGH** — Exploitable with moderate effort. SQLi, XSS, missing auth on sensitive endpoints.
- **MEDIUM** — Requires specific conditions to exploit. Missing security headers, overly broad CORS.
- **LOW** — Best practice violations, minor hygiene issues. Outdated deps without known CVEs, http:// for non-sensitive calls.
