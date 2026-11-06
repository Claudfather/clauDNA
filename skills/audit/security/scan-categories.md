# Scan Categories

Run all 9 categories. If a scan tool isn't installed, skip it with a note — don't fail the whole audit.

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

Search for hardcoded secrets in the codebase. **Never surface a raw secret value — report file:line + variable name, and scrub the findings file through the redactor (`python3 "<claudna-root>/scripts/redact.py" <file>`, with `<claudna-root>` per `../../_shared/claudna-root.md`; orchestration-guide §7) before it leaves the subagent.** Secret Detection is the exact producer of non-`sk-` matches, so hand-masking is not enough.

Use the Grep tool for each pattern below. For each match:
- Report the file and line number
- Show the variable/key name
- Never print the full value — the redactor masks it to `[REDACTED]`
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

## I. CI Triggers

A CI workflow can run code or text that someone outside the project controls, with the repository's token or secrets. Read every workflow in `.github/workflows/`, the reusable workflows and local actions they call, and the repository's Actions settings. Look for three shapes:

1. **The outsider supplies the workflow file.** `deployment` and `deployment_status` workflows run the workflow file from the deployed commit, with the repository's secrets and default token, and a checkout step with no `ref` checks out that commit. If anything deploys pull request commits, including commits from forks, a pull request can bring its own version of the workflow.
2. **A default-branch workflow takes outsider input.** `pull_request_target`, `workflow_run`, `issue_comment`, `issues`, `discussion` and `discussion_comment` run the default branch's workflow file with secrets and the default token, yet anyone's pull request, comment or issue can start them. Such a run is unsafe when it checks out the pull request head and executes anything from it (an install, build, test or local action), trusts an artifact or cache that a pull request run produced, or puts event text (titles, bodies, comments, branch names) into a `run:` step or script through `${{ }}`.
3. **Fork code reaches a self-hosted runner.** A `pull_request` run from a fork executes the fork's code on the runner its job names. On a self-hosted runner that code gets the machine, its network and anything stored there; on a persistent runner it can stay and wait for later jobs and their secrets.

Read:
- **Triggers:** each workflow's `on:` block. Note every workflow an outsider can start: through a fork pull request (`pull_request`, `pull_request_target`, or `workflow_run` after a pull request run), a comment, issue or discussion, or a deployment of their commit.
- **Permissions:** `permissions:` at workflow and job level. A workflow without them gets the repository default.
- **Token default:** `gh api repos/<owner>/<repo>/actions/permissions/workflow` (`default_workflow_permissions`: `read` or `write`). For a private repository, also `.../actions/permissions/fork-pr-workflows-private-repos` (`send_write_tokens_to_workflows`, `send_secrets_and_variables`).
- **Checkouts:** each checkout step (the checkout action, `git fetch`, `gh pr checkout`) and the ref it takes. `github.event.pull_request.head.sha`, `github.event.pull_request.head.ref`, `github.head_ref`, `refs/pull/<n>/merge` and `github.event.workflow_run.head_sha` are pull request code. Unless `persist-credentials: false` is set, the checkout leaves the token where later steps can read it.
- **Event text:** `${{ github.event.* }}` and `${{ github.head_ref }}` inside `run:` steps and any action input that runs as a script.
- **Artifacts and caches:** artifact downloads that take another run's `run-id`, and caches a privileged workflow restores. Note what the job does with them: unpacks, sources or executes them, or writes them to `$GITHUB_ENV`, `$GITHUB_OUTPUT` or `$GITHUB_PATH`.
- **Deployments and their creators:** workflows on `deployment` or `deployment_status`, and whatever creates the deployments: hosting or preview integrations, apps, and workflows using a personal or app token (a deployment a workflow creates with its own `GITHUB_TOKEN` starts no workflow run). Find whether any of them deploys pull request or fork commits: the integration's settings, the project's docs, and `gh api repos/<owner>/<repo>/deployments` (each deployment's `sha`, `ref` and `creator`).
- **Secrets:** `secrets.*`, `secrets: inherit` and environment secrets in every job an outsider can start, and in every job that shares a self-hosted runner with one.
- **Runners:** each job's `runs-on:`. For a self-hosted label, find whether fork pull request runs reach it (the repository or runner group it serves, and an organization runner group's `allows_public_repositories`), whether the runner is ephemeral or persistent, and the outside-contributor approval policy (`.../actions/permissions/fork-pr-contributor-approval`, `approval_policy`).

A setting you cannot read (no `gh`, no admin access) is unknown, not safe: grade as if it allowed the run, and say which setting went unread.

Grade each finding by what the outsider's code or text gets (`severity-definitions.md`, CI Triggers).

Usual fixes:
- Run untrusted code only under plain `pull_request`, where a fork's run gets a read-only token and no secrets. Keep `pull_request_target` and `workflow_run` for steps that run no pull request code, and read a pull request run's artifacts as data, never as code or environment.
- In a privileged workflow, check out only the base, with `persist-credentials: false`.
- Pass event text through `env:` and quote it in the shell (`"$TITLE"`), never through `${{ }}` inside `run:`.
- Gate secret-using steps on a same-repository head: `if: github.event.pull_request.head.repo.full_name == github.repository` (for `workflow_run`, `github.event.workflow_run.head_repository.full_name`).
- Give each workflow and job the least `permissions:` it needs, starting from `contents: read`, and set the repository default to read.
- Don't deploy fork commits, or deploy them only after a maintainer approves, and keep secrets out of workflows that run on those deployments.
- Keep fork pull request runs off self-hosted runners: run them on GitHub-hosted runners, close self-hosted runner groups to public repositories, and use ephemeral runners wherever untrusted code must run.
