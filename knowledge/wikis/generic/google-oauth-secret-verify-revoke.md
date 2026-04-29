---
title: "Google OAuth Client Secret — Verify & Revoke"
date: 2026-04-21
type: wiki
scope: generic
projects: []
tags: [oauth, google-cloud, credentials, security, secret-rotation, how-to]
sources:
  - "https://oauth2.googleapis.com/token (Google OAuth 2.0 token endpoint)"
  - "https://console.cloud.google.com/ (Google Cloud Console — APIs & Services > Credentials)"
---

# Google OAuth Client Secret — Verify & Revoke

How to check whether a Google OAuth 2.0 client secret is still live, and how to revoke it safely. Use this when a secret has leaked (committed to a repo, pasted somewhere public, shared with the wrong audience, etc.).

## 1. Verify status via the token endpoint

Test the credential by exchanging a dummy authorization code against Google's token endpoint. Replace `YOUR_CLIENT_ID` and `YOUR_CLIENT_SECRET`:

```bash
curl -s -X POST https://oauth2.googleapis.com/token \
  -d "client_id=YOUR_CLIENT_ID" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "grant_type=authorization_code" \
  -d "code=dummy_test_code" \
  -d "redirect_uri=http://localhost"
```

### Reading the response

| Response | HTTP | Meaning |
|---|---|---|
| `"error": "invalid_grant"` | 400 | Secret is **ACTIVE**. Google recognized the Client ID + Secret and rejected the fake `code`. |
| `"error": "invalid_client"` | 401 | Secret is **REVOKED**. Google rejected the credential itself. |

Any other error (e.g. `unauthorized_client`, `invalid_request`) usually means the redirect URI or grant type doesn't match the client config — not conclusive about secret status.

### Why this is safe

- Uses a syntactically invalid code, so no real authorization is granted even if the secret is live.
- Makes a single request to Google's public token endpoint — no side effects on the project.

## 2. Revoke the secret

1. Log in to the **Google Cloud Console** — https://console.cloud.google.com/
2. Select the project associated with this credential from the top dropdown.
3. Navigate to **APIs & Services → Credentials**.
4. Find the **OAuth 2.0 Client ID** that was exposed and click the **pencil (Edit)** icon.
5. Scroll down to the **Client secrets** section.
6. Click the **trash can** next to the exposed secret to delete it permanently.

### Zero-downtime rotation

Before deleting, click **Add Secret** to generate a replacement, then:

1. Roll out the new secret in your app / deployment (env vars, secret manager, CI/CD).
2. Confirm traffic is succeeding on the new secret.
3. Return to the credential and delete the old secret.

This avoids an outage window where neither the old nor new secret is fully wired up.

## 3. After revoking

- Re-run the `curl` from step 1 — you should now see `invalid_client` (401).
- **Rotate anything that depended on the leaked secret**: refresh tokens issued under it may still be usable until revoked separately. Review `APIs & Services → Credentials → OAuth consent screen → Grants` and revoke sessions if sensitive.
- **Check logs** for usage between the leak time and revocation. Google Cloud audit logs (`APIs & Services → Metrics` and Cloud Logging) show token-exchange activity.
- **Scrub the leak source**: git history rewrite (BFG / `git filter-repo`), remove from chat/email, rotate any co-leaked artifacts (API keys, service account JSON).

## References

- Google OAuth 2.0 token endpoint — https://oauth2.googleapis.com/token
- Google Cloud Console, APIs & Services → Credentials — https://console.cloud.google.com/apis/credentials
- Google error codes — https://developers.google.com/identity/protocols/oauth2
