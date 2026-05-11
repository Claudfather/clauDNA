---
name: file-github-issue
description: "Use when a user wants to file a GitHub issue with a screenshot against a GitHub repo. Expected inputs: a screenshot, a short description, the target repo, and the page URL or app section where the issue was observed (the skill prompts for the URL if missing)."
argument-hint: "[repo]"
---

# File an issue

Turn a screenshot + a short description into a well-structured GitHub issue on the target repo. Images are committed to a user-configured public attachments repo (set via the `CLAUDNA_ATTACHMENTS_REPO=<owner>/<repo>` env var) and embedded in the issue body via their raw URLs. If no attachments repo is configured, the skill prompts once and falls back to embedding the screenshot's local file path in the issue body.

**Reference files:**

- `body-template.md` — issue body structure, title rules, proposed-label logic.

## Procedure

Follow these steps exactly in order. If any prerequisite fails, stop and surface the error — do not improvise around it.

### Step 1: Confirm intent and collect inputs

Trigger: the user invoked `/claudna:file-github-issue [repo]`, or wrote ambient prose containing at least one image AND a filing-intent phrase ("open an issue", "report this", "log a bug", "file a bug", "file an issue"). If neither the image nor a filing phrase is present, ask the user to confirm intent and halt.

Collect:

- **Image paths:** every image attached to the current turn, in attachment order. If none, ask the user to attach a screenshot and halt this round.
- **User prose:** the free-form description accompanying the images.
- **Target repo:** resolution order — (1) slash-command arg if provided; (2) explicit `owner/repo` slug in the prose; (3) current repo's `origin` remote, derived via `git remote get-url origin` and parsed to `owner/repo`; (4) ask the user *"Which repo?"*. If both an arg and a prose slug are provided, the arg wins.

### Step 2: Validate and resolve the target repo

- **Target repo:** accept a fully-qualified `owner/repo` slug. If a bare name is given (e.g., `my-app`) and Step 1's resolution fell through to it, ask the user for the owner — do not guess. Record the resolved slug; every subsequent step uses it. Existence and access are verified implicitly by the label pre-flight (step 3) and the final `gh issue create` — no separate allowlist.
- **Image format** for each path: extension must be `.png`, `.jpg`, `.jpeg`, `.gif`, or `.webp` (case-insensitive). Reject any other extension with a clear error naming the rejected path and the accepted set, then halt.
- **Tooling prereqs:** `gh` must be installed and authenticated. If `gh --version` fails: error with `brew install gh` hint. If `gh auth status` fails: error with `gh auth login` hint.

### Step 3: Label pre-flight

Run once the target repo is known, BEFORE rendering the preview (and again if a later edit changes the target repo):

```sh
gh label list --repo <repo-slug> --json name --jq '.[].name'
```

Intersect the command output with the proposed label set (see `body-template.md`) to get the **effective label set**. Record labels that were proposed but not present in the repo as **dropped** — they'll be shown inline in the preview and repeated as a post-filing warning.

If the pre-flight command itself fails (network, rate limit, non-zero exit): do not abort. Fall back to sending all proposed labels unchanged and note in the preview: *"(label pre-flight unavailable; all proposed labels will be attempted)"*.

### Step 4: Gather context and draft the issue

Lean toward richer context. The issue body is only as useful as what you pull in here. Don't fabricate — if a field has no source, prompt the user (for the Page/URL anchor, see 4b.5) or omit it (for optional enrichers like Action, Inputs, Links).

**4a. Extract from the screenshot(s).** Read each image carefully and pull:

- **Page / URL:** The browser URL bar (if visible in chrome), the window/tab title, in-app breadcrumbs, section headers. A screenshot of "MyApp — conversation — Item123" is a concrete anchor even without a full URL. If none of these are visible, leave the anchor blank — Step 4b.5 will ask the user directly.
- **Visible UI state:** error banners, toast messages, tool output text (including any "fallback" or "not supported" notes — quote them verbatim in `## What I saw`).
- **Inputs:** the exact query, prompt, entity, or selection the user used, if it appears in the screenshot.

**4b. Extract from the user prose.** Pull:

- Links to Slack threads, docs pages, dashboards, pipeline/CI runs, related PRs — any URL-shaped string.
- Explicit issue references (`#123`, `owner/repo#45`).
- Product/feature names that help disambiguate the surface.

**4b.5. Prompt for URL if missing.** Decide whether 4a + 4b produced a concrete Page/URL anchor. Concrete means: a browser URL visible in the screenshot chrome, a URL-shaped string in the prose, or an app + section + specific surface in the screenshot (e.g., "MyApp — entity page — Item123"). Just an app name ("MyApp") or an app + generic surface ("MyApp — dashboard") is NOT enough on its own. If nothing concrete, halt and ask:

> I don't see a URL or page anchor in the screenshot or your description. What page is this from? Paste the URL or describe the surface — e.g., `app.example.com/dashboard` or "Settings → Notifications".

Wait for a reply. Use it as the Page/URL value.

- If the user replies with a URL or page description → use it verbatim.
- If the user replies "skip" / "unknown" / "n/a" → mark the body field as `unknown — user declined to provide`. This makes the informed choice explicit rather than making it look like the skill forgot to ask.
- Don't badger. One prompt, one reply, move on.

**4c. Dupe and related-issue search.** Run once, against the target repo (re-run if target repo changes during Step 5 edits). Use 2–3 salient keywords from the user prose and screenshot (the draft title doesn't exist yet — it's produced in 4d):

```sh
gh issue list --repo <repo-slug> --search "<2-3 keywords>" --state all --limit 10 --json number,title,state
```

Include any clearly related hits in the `## Related > Issues` bullet with their state and a one-line relationship note. If the search returns nothing germane, the bullet is "none found" (or omit if there are also no Links).

If there's an obviously open duplicate with the same framing, do NOT silently file a second one — raise it in the preview and let the user choose (comment on the existing issue vs. file anyway with a cross-reference).

**4d. Draft.** Produce title, body, and proposed labels per `body-template.md`. Pick the single-image template if exactly one image was attached, otherwise the multi-image template. Leave `<attachment-url-N>` placeholders literal — they're substituted in step 6.

**4e. Resolve the attachments repo.** Resolution order:

1. `CLAUDNA_ATTACHMENTS_REPO` env var (format: `owner/repo`). Validate that it parses cleanly — if malformed, surface the value and ask.
2. If unset, ask once: *"This skill embeds screenshots by committing them to a public GitHub repo and linking the raw URL. Reply with `<owner>/<repo>` to use one for this filing (and consider exporting `CLAUDNA_ATTACHMENTS_REPO=<owner>/<repo>` to make it persistent), or reply `skip` to file the issue with the screenshot's local file path embedded instead (won't render inline)."*
   - If the user replies with a slug → record it in `$ATTACHMENTS_REPO` for this filing only.
   - If the user replies `skip` → set `$ATTACHMENTS_MODE=local` and skip the upload step. The preview and final body will use `![screenshot](file://<absolute-path>)` markdown.
3. The repo must already exist and the user must have write access. The skill never creates the attachments repo.

### Step 5: Preview and confirm

Render exactly this block. The first line varies based on Step 4e resolution: if `$ATTACHMENTS_REPO` is set, use the "committed to <slug>" wording; if `$ATTACHMENTS_MODE=local`, use this instead: *"Screenshot(s) will be embedded as local file paths only — they will not render inline. Filing only — no upload."*

```
Screenshot(s) will be committed to <$ATTACHMENTS_REPO> (public repo; unlisted-by-path). Anyone with the URL can view. Cancel now if redaction is needed.
------------------------------------------
Target repo:   <repo-slug>
Title:         <title>
Labels:        <effective set>   (dropped: <comma-separated>, if any)

Body:
  <full rendered markdown; each <attachment-url-N> placeholder shown as "(uploaded on confirm)" — for single-image render as "![screenshot](uploaded on confirm)", for multi as "![screenshot 1](uploaded on confirm)", etc.>
------------------------------------------

File this? [y / n / or describe edits]
```

Keep the `<attachment-url-N>` tokens in the internal body string — only the preview hides them behind the stub. The real URLs are swapped in after `y` (step 6).

Wait for the user's reply:

- `y` → proceed to step 6.
- `n` or `cancel` → exit cleanly. No commit, no issue.
- Anything else → treat as edit instructions. Apply them (may change title, body, labels, or target repo). If the target repo changed, re-run step 3 (label pre-flight) AND step 4c (dupe search), since both are repo-scoped. Then re-render this preview. No round limit.
- Edit rounds can change text and metadata but NOT the image set. If the user wants to add, remove, or replace screenshots, treat that as a new `/claudna:file-github-issue` invocation — cancel this one and restart.

### Step 6: Upload images

Only run after the user replies `y`. If `$ATTACHMENTS_MODE=local` from Step 4e, skip this entire step — substitute each `<attachment-url-N>` placeholder with `file://<absolute-path>` of the corresponding image instead, then go to step 7.

Images are committed to `$ATTACHMENTS_REPO` (resolved in Step 4e) on the `main` branch at `<YYYY>/<MM>/<uuid>.<ext>`. Each image gets a fresh UUID so paths don't collide and aren't guessable by enumeration.

For each image (in turn order):

1. Compute the path:
   ```sh
   EXT="${IMG_PATH##*.}"                                # e.g. "png"
   UUID=$(uuidgen | tr '[:upper:]' '[:lower:]')
   ATTACH_PATH="$(date +%Y)/$(date +%m)/$UUID.$EXT"
   ```
2. Commit the image via the Contents API. Base64-encode to a tmpfile first, then use `jq --rawfile` — passing the base64 as a `--arg` value still puts it on the command line and blows past `ARG_MAX` on anything over ~100KB:
   ```sh
   B64_FILE=$(mktemp "${TMPDIR:-/tmp}/file-github-issue-b64.XXXXXX")
   base64 -i "$IMG_PATH" | tr -d '\n' > "$B64_FILE"
   jq -n --arg msg "file-github-issue attachment: <title>" \
         --rawfile content "$B64_FILE" \
         '{message: $msg, content: $content}' \
   | gh api --method PUT \
       "/repos/$ATTACHMENTS_REPO/contents/$ATTACH_PATH" \
       --input -
   rm "$B64_FILE"
   ```
3. Construct the raw URL:
   ```sh
   ATTACH_URL="https://raw.githubusercontent.com/$ATTACHMENTS_REPO/main/$ATTACH_PATH"
   ```
4. Substitute the `<attachment-url-N>` placeholder matching this image's turn position (image 1 → `<attachment-url-1>`, image 2 → `<attachment-url-2>`, etc.) with this image's `$ATTACH_URL`.

If any upload fails: abort before filing. Print the attachment URLs of any images already committed — they're persistent and re-usable. No rollback.

Max file size: the Contents API hard-limits at 100MB. For files over ~1MB the API also warns — still works for typical screenshots (well under), but if you hit a size error, surface it and halt.

### Step 7: File the issue

1. Write the substituted body to a tmpfile. BSD `mktemp` on macOS requires `XXXXXX` at the **end** of the template — no `.md` suffix; `gh --body-file` doesn't care about extension:
   ```sh
   TMPFILE=$(mktemp "${TMPDIR:-/tmp}/claudna:file-github-issue.XXXXXX")
   ```
2. File the issue with the effective label set from step 3:
   ```sh
   gh issue create \
     --repo <repo-slug> \
     --title "<title>" \
     --body-file "$TMPFILE" \
     [--label <effective-label-1>] [--label <effective-label-2>] ...
   ```
3. Delete the tmpfile: `rm "$TMPFILE"`.
4. Print the issue URL (from `gh` stdout) and the attachment URL(s). If any labels were dropped in step 3, repeat the warning:
   > ⚠ Filed without labels (target repo missing: `<comma-separated>`). Create them in the repo to enable labeling next time.

If `gh issue create` fails (e.g., 403/404 for missing permissions): surface the exact `gh` stderr and suggest requesting access. The attachment URLs are preserved — print them so the user can reuse or delete (delete via `gh api --method DELETE /repos/$ATTACHMENTS_REPO/contents/<path>` with the file's blob SHA).

## Invocation

Two surfaces, same body underneath:

- **Slash command:** `/claudna:file-github-issue [repo]`. Arg optional — if missing, default to the current repo's `origin` remote (parsed from `git remote get-url origin`); if no remote or ambiguous, ask. Accepts a fully-qualified `owner/repo` slug.
- **Ambient:** a user prompt with an image and filing-intent language ("open an issue…", "report this bug…"). Strong signals for activation: at least one image in the turn **and** a filing-intent phrase. These are guidance, not hard gates — step 1 re-checks for both and asks for confirmation if either is missing.

## Failure modes

| Failure | Behavior |
|---|---|
| No image in the turn | Ask for one. Do not proceed. |
| Unsupported image format (not png/jpg/jpeg/gif/webp) | Error listing the rejected path and the accepted formats. Halt. |
| Image file unreadable / corrupt / empty | Error with the path. Ask to re-provide. Halt. |
| `gh` not installed | Error with `brew install gh` hint. Exit. |
| `gh auth status` fails | Error with `gh auth login` hint. Exit. |
| Target repo doesn't exist (404 at label pre-flight or issue create) | Surface `gh` stderr (404). Re-prompt the user for the correct repo. |
| User lacks issue:write on target repo | Surface `gh` stderr, suggest requesting access. Attachment URLs preserved — print them. |
| User lacks write on the configured `CLAUDNA_ATTACHMENTS_REPO` | Surface `gh` stderr, suggest requesting access or setting a different repo. Halt before filing. |
| `CLAUDNA_ATTACHMENTS_REPO` unset and user replies `skip` | File the issue with `![screenshot](file://<absolute-path>)` markdown — won't render inline but preserves the path. |
| Body mentions a repo different from target | Warn inline in the preview; do not block. User is authoritative. |
| Contents API commit fails | Abort before `gh issue create`. Print error. |
| Image exceeds 100MB Contents API limit | Surface the error. Suggest compressing or using a smaller screenshot. Halt. |
| Issue creation fails after attachment upload | Print the orphaned attachment URLs. They're reusable if refiled. |
| Proposed label missing in repo | Caught by pre-flight (step 3). Dropped labels shown in preview and repeated post-filing. |
| `gh label list` pre-flight fails | Don't abort. Send all proposed labels. Note in preview. |
| User cancels at preview | Exit cleanly. No commit, no issue. |
| User interrupts mid-upload | No partial-cleanup guarantee. Already-committed images remain in the attachments repo. |
| Multi-image, any one upload fails | Abort all. Print already-committed attachment URLs so they can be reused or deleted. |

## Notes

- **Why `--body-file`:** avoids shell-escaping pain with markdown (backticks, newlines, special chars).
- **Why pre-flight labels (not retry-on-fail):** if `gh issue create` fails on a missing label, stripping all `--label` flags would also drop the valid ones. Pre-flight gives a clean, one-round answer.
- **Why a public attachments repo (vs. gists):** `gh gist create` only accepts text files — binaries like PNGs are rejected. GitHub has no public API for inline issue attachments (the web UI's paste-image flow uses a private session-cookie endpoint). Committing to a public repo and embedding the raw URL is the only `gh`-reachable path that renders inline. Public is required because raw URLs from private repos go through signed, short-lived redirects that don't render in issue markdown. Secrecy is by-path: each image gets a fresh UUID, so the URL isn't guessable.
- **Why `jq --rawfile` (not `--arg` or `-f content=…`):** base64-encoded images blow past `ARG_MAX` on anything over ~100KB. Both `jq --arg content "$(base64 ...)"` and `gh api -f content=…` shell-expand the value onto the command line and fail with "argument list too long". `--rawfile` reads from a file descriptor, so the payload never touches argv.
- **Finding past attachments:** browse `https://github.com/$ATTACHMENTS_REPO/tree/main/<YYYY>/<MM>/` or `gh api /repos/$ATTACHMENTS_REPO/git/trees/main?recursive=1 --jq '.tree[].path'`.

## Red Flags — STOP

If you catch yourself thinking any of these, STOP — you are about to file an issue that will land badly:

- **"I'll just file it, skip the preview"** — Preview exists because GitHub issues are team-visible and hard to retract. Read the draft before `y`.
- **"Close enough on the repo"** — Wrong repo = noise in someone else's tracker + real bug falls on the floor. If unsure, ask the user; don't guess.
- **"The screenshot is fine to upload"** — Screenshots routinely show customer names, credentials, internal URLs, dashboards. Pre-upload check: is there anything in this image you wouldn't paste in a public Slack channel? If yes, cancel and redact.
- **"The description is sparse but good enough"** — A two-word description makes the issue unactionable. The sparse-prose warning exists for a reason. Ask the user to add context via edit before filing.
- **"Looks like a duplicate, but I'll file it anyway"** — Step 4c runs the dupe search for you and surfaces candidates in the `Related > Issues` bullet. Still your job to read them and decide: if an open issue already covers this exactly, raise it in the preview and let the user choose (comment vs. file with cross-reference). Never silently file a second copy.
- **"Let me just create the repo / labels myself"** — The skill is intentionally limited to filing issues. Creating repos or labels bypasses human review. Tell the user to request it through normal channels.

## Common Rationalizations

| Excuse | Reality |
|---|---|
| "I can tell from the screenshot which repo" | Maybe, maybe not. The user is authoritative. Ask if unsure. |
| "The sparse warning is ugly, I'll drop it" | The warning is the feature — it nudges the user to add context before filing. |
| "I'll guess the URL from the app name" | Don't. Step 4b.5 prompts the user explicitly when extraction fails. Use their reply. Fabricated URLs are worse than missing ones. |
| "I'll skip the 4b.5 prompt, they can fix it in the preview" | No. The preview is for reviewing the draft, not for remembering missing anchors. Asking once upfront is cheaper than the user catching an "unknown" placeholder in the preview and re-triggering an edit round. |
| "The Related section is empty, I'll invent a tangentially-related issue" | No. If the dupe search found nothing and there are no links in the prose, omit the section entirely per `body-template.md`. |
| "I'll swap in the real attachment URLs now to save a step" | No. Commit happens only after `y`. A cancelled preview should never leave an attachment in the repo. |
| "Missing label? I'll create it" | Out of scope. Ship the issue without the label; flag the gap in the post-filing warning. |
| "I'll just use `cat <<EOF \| gh issue create --body -`" | Backticks and pipes in markdown break this. Always `--body-file`. |
| "The pre-flight failed, I'll bail" | Don't. Fall back to sending all proposed labels and note it in the preview. |
| "The user's 4b.5 reply is terse / unhelpful, I'll reword or expand it" | No. One prompt, one reply. Use the reply verbatim. If it's wrong, the user will fix it in the preview edit round. |
| "The user changed the target repo in preview edits, the old dupe results probably still apply" | No. Dupe search is repo-scoped. Re-run step 4c alongside step 3 whenever the target repo changes. |
| "The user wants to swap the screenshot, I'll just attach it in the preview edit" | No. Edit rounds change text and metadata only. For image changes, cancel and restart `/claudna:file-github-issue`. |
