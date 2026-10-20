# PR visual evidence

One protocol for QA capture, review, verification, build deliverables and shipping.
Use it for visual or user-facing behavior changes. Backend/data-only work uses
command, request or test evidence; it does not need media. Scale states, viewports
and clip length to the change, without a fixed screenshot count or duration.

## 1. Establish scope and capabilities

- Use the actual application, its canonical startup/authentication flow and seeded
  fictional data or isolated test services. A generated mockup or transport fixture
  is not evidence of the implemented UI. Label capability probes as such.
- Identify the available capture, local validation, native GitHub attachment and
  authenticated browser tools. A restricted browser facade may lack recording
  even when a full Playwright library is available. Use documented capabilities;
  do not invent recorder APIs, infer support from the model name or copy browser
  profiles/cookies to obtain authentication.
- Reuse authorization for the stated repository and artifact scope. Ask only for
  genuinely missing authorization. Missing dependencies or native upload support
  have an explicit unsupported outcome; no upload endpoint reverse engineering,
  permission changes, automatic retries or replacement hosting services. On a
  Chrome extension host, missing local-file access is a user-managed prerequisite.
  An unavailable upload does not prevent authorized capture and local validation.

## 2. Own the packet before capture

The outer workflow owns one private `<scratch>` outside Git, made with `mktemp -d`
per `../_shared/orchestration-guide.md` §1. Reuse a caller's root when nested and
return ownership to that caller; do not create per-skill copies. Record the exact
root and actual browser/context/server handles for foreground finalization.

Keep a small `evidence.json` in that root. Record:

- Base and head revisions, dirty runtime-input file hashes (including relevant
  untracked inputs), app/service routing, fixture identity and startup command.
- For each artifact: source revision/input hashes, viewport, state, capture steps,
  behavioral check/result, pixel dimensions, relative filename and SHA-256.
- Separate `captured`, `locally_validated`, `uploaded` and `reviewer_verified`
  results, attachment/PR links and cleanup outcome. A state may be blocked or
  unsupported; neither is success. Before a PR exists, reviewer verification is
  pending. Reuse the existing session/result identity, not a new logging system.

Exclude credentials, signed URLs, sensitive request bodies and unnecessary traces.
After edits, rebases or service/fixture changes, compare the captured runtime inputs
with what will be reviewed. Recapture affected evidence unless revisions or exact
input hashes demonstrate source equivalence; unchanged screenshots alone do not.

## 3. Capture and validate locally

Capture matching before/after viewports and relevant interaction, loading, error,
empty or recovery states. Use semantic readiness and observable results instead of
fixed sleeps or screenshot polling. Persistence claims need save/reload evidence;
mutations need the actual request/result; timing claims need measurements.

With full Playwright, enable `recordVideo` when creating the context. This library
recipe takes `chromium`, the recorded `scratch` path, `viewport` and the app-specific
`driveChangedFlow(page)` from the capture task; that function performs the real
navigation, assertions and screenshots inside scratch:

```javascript
const browser = await chromium.launch({ headless: true });
let context;
try {
  context = await browser.newContext({
    viewport,
    recordVideo: { dir: scratch, size: viewport },
  });
  const page = await context.newPage();
  const video = page.video();
  await driveChangedFlow(page);
  await context.close(); // Flush the recording before reading it.
  context = undefined;
  const rawVideo = await video.path();
  // Validate/convert rawVideo while the browser handle is still available.
} finally {
  try { if (context) await context.close(); }
  finally { await browser.close(); }
}
```

Use the project's installed browser, or an explicitly supported installed channel
such as `chrome`; do not guess browser-cache paths or install global dependencies
to conceal a missing capability. Configure recording size to match the viewport.
Full Playwright's WebM can be converted with installed ffmpeg. Substitute the
actual recorded paths and run each command separately:

```bash
ffmpeg -v error -i "<raw-video>" -an -c:v libx264 -pix_fmt yuv420p -movflags +faststart "<scratch>/walkthrough.mp4"
ffprobe -v error -show_streams -show_format -of json "<scratch>/walkthrough.mp4"
ffmpeg -v error -xerror -i "<scratch>/walkthrough.mp4" -f null -
```

Observe successful exits, one H.264/yuv420p video stream, no audio, expected
dimensions and positive duration. Inspect the screenshots and video content with
available media tools. Corrupt, unsupported, unreadable or wrong-state media is not
locally validated. Hash the final artifacts after conversion; do not alter them
after recording those hashes.

## 4. Publish native attachments

Keep generated media out of the final diff **and feature history**. If any was
committed, stop before pushing it; do not rewrite published history without
authorization. Publish through the host's authorized GitHub user-attachment flow,
using the existing authenticated browser. Do not use release assets or Git commits
as media hosting.

Where exposed, register `waitForEvent("filechooser")` before activating the native
attachment control, then pass only the exact packet files to `chooser.setFiles`.
Use bounded native waits and inspect the resulting state. Final attachment links
and an enabled submit control permit saving; an attempted upload or transient
status message does not prove publication. Retain canonical attachment URLs,
never short-lived signed delivery URLs.

Write images as Markdown and leave a blank paragraph before each video URL. Native
multi-file insertion can put a video URL immediately after an HTML image tag,
leaving the video as plain text. The PR evidence section should contain:

```markdown
![Before: relevant state](RETURNED_IMAGE_ATTACHMENT_URL)

![After: relevant state](RETURNED_IMAGE_ATTACHMENT_URL)

RETURNED_VIDEO_ATTACHMENT_URL
```

Include the concise provenance and verification results in the existing PR/result;
the full scratch manifest need not become a permanent new document. Capture may
precede PR creation; publication and reviewer verification finish on the actual PR.

## 5. Verify the published reviewer experience

Reload the saved PR in the authenticated browser and inspect its actual media:

- **PNG:** the expected attachment is present, `complete` is true, natural width
  and height match the captured image, and visible content matches the intended
  state. `complete` with zero dimensions is a broken image. Verify rendering
  directly; do not initiate a round-trip PNG download or leave download cleanup
  to the user. This proves rendering, not byte-for-byte equality of hosted bytes.
- **MP4:** use the native player and observe time advancing from the start or a
  natural end with positive duration, plus the expected interaction frames and no
  media error. A player shell, metadata, URL, poster or seek to the end is not
  playback proof. Use the host's exposed media fields and controls; a missing
  observation capability stays unverified. No verification download is required.

Do not claim reviewer verification from a composer preview or an issue-only
capability probe. If attachments are inaccessible, media fails to render/play, or
the captured source is stale, report that state and finish the owned-resource
finalizer. Required repository checks still apply; media is not a reason to add
tests that merely mirror wording or file layout.

## 6. Finalize in the workflow

The owner must run `../_shared/orchestration-guide.md` §1.1 before its terminal
result, on success, failure, unsupported capability or handled cancellation.
Put programmatic resource closure in `finally`; across host-tool calls, the outer
workflow performs the same foreground finalizer before returning. Await closure
of owned writers/contexts, stop only owned servers by their actual handles, and
close owned browser tabs. Never delete under a live recorder or use process-name
scans, timed reapers or a later user cleanup command.

First preserve usable evidence as verified published attachments or a durable
host/user-authorized deliverable outside Git, with the sanitized manifest/results.
If publication is blocked, deliver it locally and report the incomplete state.
If no durable delivery surface exists, retain the one root only as an explicit
active handoff under §1.1; do not discard sole evidence or claim cleanup complete.
Then remove the exact owned scratch root and verify absence as §1.1 requires.
Borrowers return the packet and cleanup responsibility to their existing owner.
Published attachments are the deliverable and stay published. Cleanup failures
name the exact remaining owned resource; they never become a reminder for the
user. No claim covers an uncatchable termination or a machine reboot.
