# Scan Categories

Run all 8 categories. If a scan tool isn't installed, skip it with a note — don't fail the whole audit.

Do NOT read CLAUDE.md or MEMORY.md directly — Claude already has both in its system prompt. Use the system prompt context for project understanding; focus scan effort on code and configuration.

## A. Dependency Vulnerabilities

Run each scanner as a **separate Bash call** (never chain with `||`). Try whichever package managers are present:

**Node.js:**
```bash
npm audit --json
```

**Python** (try `pip-audit` first; if it fails, try `pip audit` as a separate call):
```bash
pip-audit --format=json
```
If that fails:
```bash
pip audit
```

**Rust:**
```bash
cargo audit --json
```

If none of these tools are installed, note: "No dependency scanner available. Install `npm`, `pip-audit`, or `cargo audit` for dependency vulnerability scanning."

## B. Secret Detection

Search for hardcoded secrets in the codebase. **Never print the actual secret value — show file:line but mask the value.**

Use the Grep tool for each pattern below. For each match:
- Report the file and line number
- Show the variable/key name
- Mask the value: `API_KEY=sk-****` (never the full value)
- Note whether the file is gitignored

## C. OWASP Top 10 Patterns

Search for common vulnerability patterns using Grep:

**SQL Injection:**
- String concatenation in SQL queries: `"SELECT.*" + ` or f-strings with SQL
- Missing parameterized queries

**XSS (Cross-Site Scripting):**
- `innerHTML`, `dangerouslySetInnerHTML`, `v-html`
- Template literals inserted into HTML without escaping
- `document.write()`

**Command Injection:**
- `exec()`, `eval()`, `child_process.exec()`, `subprocess.call(shell=True)`
- Template strings in shell commands
- `os.system()` with user input

**Path Traversal:**
- File operations with user-controlled paths without sanitization
- `../` not stripped from file path inputs

**Insecure Deserialization:**
- `pickle.loads()`, `yaml.load()` (without `Loader=SafeLoader`), `eval()` on user data

## D. Environment Variable Hygiene

- Use the Glob tool with pattern `**/.env*` to find `.env` files (filter out `.git/` paths from results)
- Use the Grep tool with pattern `\.env` in `.gitignore` to check if `.env` is gitignored
- Use the Glob tool with pattern `.env.example` or `.env.sample` to check for example files
- Use the Grep tool with pattern `process\.env\.|os\.environ|os\.getenv|ENV\[`, glob `*.{js,ts,py,rb}`, `output_mode: content`, `head_limit: 30`

Flag:
- `.env` files not in `.gitignore`
- Secrets in `.env.example` (should be placeholders only)
- Environment variables used in code but not documented

## E. Authentication & Authorization

Search for auth-related patterns:

- JWT verification: is the secret hardcoded? Is expiry checked? Is the algorithm pinned?
- Session management: secure cookie flags (`httpOnly`, `secure`, `sameSite`)
- Password handling: is bcrypt/argon2 used? Are passwords logged?
- Rate limiting: any rate limiter on auth endpoints?
- CORS configuration: wildcard `*` origins?

## F. HTTPS & Transport Security

- Hardcoded `http://` URLs (should be `https://`)
- Missing HSTS headers
- TLS certificate validation disabled (`rejectUnauthorized: false`, `verify=False`)
- Mixed content risks

## G. Exposed Endpoints Without Auth

Look for:
- API routes without auth middleware
- Admin panels without authentication gates
- Debug endpoints left enabled (`/debug`, `/metrics`, `/health` with sensitive data)
- GraphQL introspection enabled in production

## H. Dependency Hygiene

Run each as a **separate Bash call** (never chain or pipe):

```bash
npm outdated
```

```bash
pip list --outdated
```

Claude can read the full output — no need to truncate with `head`. Also cross-reference lock files with audit results above for known-vulnerable package versions.

Flag:
- Dependencies not updated in >6 months
- Packages with known CVEs (cross-reference with audit results)
- Unmaintained packages (archived repos, no releases in >1 year)
