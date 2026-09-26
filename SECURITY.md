# Security

Planner's PPT Hell includes a local review server for human approval and feedback capture.

## Local-Only Assumption

Review pages are served by the shared seam's local host (`planners-review-core`: `serve-review.mjs` /
`review-host.mjs`), bound to loopback. Do not expose it to the public internet unless you have added your
own authentication, access control, and deployment hardening. (The Skill used to ship its own
`scripts/review_server.py`; it was retired on 2026-09-26 once both review faces moved onto the seam.)

## Approvals

There is **no approval key or passphrase**. The requirement was retired: the old server discarded any
`approval_key` field in the payload, so any document claiming a key is required would describe a path
that does not exist. The page skips it too (the seam's host writes what the page sends, and the Skill
re-derives what counts).

What actually separates human approval from model-generated state is the review handshake:

- The review page is generated against a snapshot, and the submission must carry the matching
  one-time `review_id`. An old browser tab cannot approve a new version.
- Approval is bound to the exact artifacts it was given for: per-page version and PNG hash for
  page review; review-page hash, rendered source pages and template package hashes for template
  review.
- To cite human approval in a formal workflow, cite the review server provenance in the feedback
  file, not a key.

## Reporting Security Issues

Please report security issues privately:

- Email: Lawyif@163.com
- Website: https://demyth.info

Include the affected script, reproduction steps, and expected impact.
