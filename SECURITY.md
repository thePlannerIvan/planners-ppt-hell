# Security

Planner's PPT Hell includes a local review server for human approval and feedback capture.

## Local-Only Assumption

`scripts/review_server.py` is intended for local review workflows. Do not expose it to the public internet unless you have added your own authentication, access control, and deployment hardening.

## Approval Keys

The one-time approval key is used to separate real human approval from model-generated state. Do not store, reuse, or publish approval keys.

Formal workflows require:

- `approval_key_required: true`
- `approval_key_verified: true`
- review server provenance

Any no-key approval path is considered invalid for formal delivery.

## Reporting Security Issues

Please report security issues privately:

- Email: Lawyif@163.com
- Website: https://demyth.info

Include the affected script, reproduction steps, and expected impact.
