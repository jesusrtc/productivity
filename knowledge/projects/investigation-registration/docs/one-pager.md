# Registration Spike: Investigation One-Pager

**Status:** Open / Investigating
**SEV Level:** TBD (pending post-reg abuse assessment)
**Date Detected:** April 7, 2026
**Investigator:** Jesus Cortes

---

## Executive Summary

A residential proxy-based bot farm created 1,186 fake accounts on 2026-04-07 using two Microsoft Edge user-agents (Edge/138 and Edge/139). The operation used 280+ residential IPs across 52 countries, auto-generated Spanish-named Gmail aliases (`jossalgadog001.gmail.com`, etc.), and ran in two distinct bursts (00-12 UTC, 17-23 UTC) with a 4-hour silence gap. This is confirmed automated abuse, not a false positive.

---

## The Spike

| IOC (User-Agent) | Spike (Apr 7) | Baseline Avg | Multiplier |
|-------------------|---------------|--------------|------------|
| Edge/138 (Chrome/138) | 671 | 37/day | ~18x |
| Edge/139 (Chrome/139) | 515 | 24/day | ~21x |
| **Combined** | **1,186** | **~60/day** | **~20x** |

Total platform registrations on Apr 7 were 792,881 — the spike is 0.15% of total volume but represents a coordinated campaign.

---

## Root Cause: Residential Proxy Bot Farm

### Infrastructure Profile
- **IPs:** 280+ unique residential IPs, no flagged proxies/VPNs (`ip_proxy_type = '?'`)
- **Geography:** 52+ countries. Top: Brazil (173), USA (171), Mexico (164), Russia (87), Peru (63)
- **ISPs:** Residential providers — Cablevision (MX), Claro (BR), Vimpelcom (RU), Charter (US)
- **Email pattern:** Auto-generated `{prefix}{spanish-surname}{suffix}{number}.gmail.com` — only 28/1,186 used plain `gmail.com`

### Operational Pattern
- **Two bursts:** 00-12 UTC and 17-23 UTC, with near-zero activity 13-16 UTC
- **UA rotation:** Two Edge versions only, same Windows 10 x64 platform — likely two browser configs in one toolchain
- **Reuse per IP:** Top IPs had 15-36 registrations each — too many for legitimate use, but spread enough to avoid simple rate limits

---

## Why This Is Real (Not a Data Issue)

- Baseline for these UAs was stable at ~60/day for 14 days — then 20x in a single day
- Email domains are programmatically generated, following a consistent naming convention
- Residential IPs with no proxy flags = residential proxy network designed to evade IP-based detection
- Two-burst operational pattern is consistent with bot farm shifts, not organic user behavior
- 1,186 accounts from just 2 UA strings is extreme concentration

---

## Open Questions & Next Steps

- [ ] Were CAPTCHA challenges served? What was the pass rate?
- [ ] Post-registration behavior: are these accounts already spamming, scraping, or farming connections?
- [ ] Have downstream restriction models already caught any of the 1,186 accounts?
- [ ] Cross-reference with known bot campaigns using similar email patterns
- [ ] Assess severity (impact depends on what the accounts do post-registration)
- [ ] Recommend mitigation: enhanced challenge for these UAs, email pattern blocking, or IP-based rate limiting

---

## Datasets Used

- `u_trustim.event_registration`: registration events with UA, IP, geo, email, timestamps
- `u_trustim.reg_automation_alert_2026_04_07_00`: alert member list (1,186 IDs)

## References

- Alert source: Z-Score anomaly detection pipeline, partition `2026-04-07-00`
- See [investigation.md](investigation.md) for detailed technical analysis with queries
