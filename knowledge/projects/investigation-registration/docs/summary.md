# Registration Spike — Summary & Next Steps

**Date:** 2026-04-17
**Status:** Investigation complete; mitigation pending
**Investigator:** Jesus Cortes

---

## What we found

A residential-proxy bot farm created **1,186 fake accounts on 2026-04-07** using two Edge UAs (Chrome/138 Edg/138 → 671, Chrome/139 Edg/139 → 515), a ~20x spike over a stable 14-day baseline (~60/day).

- **Infra:** 280+ residential IPs across 52 countries (top: BR 173, US 171, MX 164); all `ip_proxy_type='?'`.
- **Emails:** auto-generated `{prefix}{spanish-surname}{suffix}{number}.gmail.com`; only 28/1,186 used plain `gmail.com`.
- **Cadence:** two bursts (00–12 UTC, 17–23 UTC) with a 13–16 UTC silence gap.
- **Challenge gap:** CAPTCHA not served on the bulk of these flows — model scored them below the gating threshold.
- **Downstream:** most accounts already picked up by restriction models; **45 remain unrestricted**.
- **Broader context:** Gmail-pattern campaign on Apr 7 totals **12,505 accounts**, of which these 1,186 are a subset.

Full analysis: [investigation.md](investigation.md) · [one-pager.md](one-pager.md)

---

## Next steps

Remaining open tasks (from `lab task ls`):

1. **Profile the broader Gmail-pattern campaign (12,505 accounts on Apr 7)** — task #8
   - Confirm same operator vs. parallel campaigns; compare UA/IP/timing fingerprints.
2. **Review and restrict the 45 unrestricted accounts** — task #10
   - Highest-urgency action; these are still live.
3. **Recommend pausing or gating the "All sign-up challenge experiment" lix for scores ≥ 0.95** — task #9
   - Mitigates the challenge-not-served gap found in task #6.
4. **Recommend the email-domain regex as a blocking signal + severity assessment** — task #11
   - Write-up for abuse-platform team; propose SEV level based on post-reg behavior of the 1,186.

### Suggested sequencing
1. Triage the 45 unrestricted accounts (#10) — contain first.
2. Land the lix gating recommendation (#9) — stop bleed.
3. Broaden scope to the 12,505 cohort (#8) — understand full campaign.
4. Package findings + regex signal + severity (#11) — hand off.

---

## Open questions

- Are the 1,186 accounts showing post-registration abuse (spam, scraping, connection-farming)?
- Does the 12,505 Gmail-pattern cohort share the same proxy network and burst cadence?
- What is the false-positive risk of the email-domain regex against legitimate Gmail users?
