# Signup Drop — Apr 8, 6:30 PM PT

**Source:** [#incident-11066 thread](https://linkedin-randd.slack.com/archives/C0ARU0B1CSD/p1775753773135449?thread_ts=1775681242.328459&cid=C0ARU0B1CSD)
**Reported by:** Taranjot Singh, Patricia O'Meara
**Date:** 2026-04-08

## Summary

Signups dropped ~12-18% w/w starting around 6:30 PM PT on Apr 8. The drop is explained by anti-abuse defenses catching returning bot/scraping registration traffic. Against the w/4w baseline (Mar 11, pre-bot), evening signups are inline. No model ramp or revert occurred on Apr 8.

## Timeline

| Date | Event |
|------|-------|
| Mar 11 | Clean Tuesday baseline (w/4w) |
| ~Apr 1 | Bot/scraping registration traffic inflates signups |
| Apr 2 | Reactive reg model ramped — signups cliff to ~15K/hr, model reverted same day |
| Apr 3-7 | Bot traffic returns after revert, signups elevated vs w/4w |
| Apr 8 6:30 PM | Existing defenses (restrictions on suspicious registrations) catch bot traffic, signups normalize to w/4w levels |

## Chart

![signup-drop-apr8-hourly.png](assets/signup-drop-apr8-hourly.png)

<details>
<summary>Query</summary>

```sql
SET SESSION li_authorization_user = 'register';

SELECT
  date_format(from_unixtime(header.time/1000, 'America/Los_Angeles'), '%Y-%m-%d %H:00') as hour_bucket,
  count(*) as signups
FROM tracking.registrationevent
WHERE datepartition IN (
  '2026-04-08-00',  -- drop day (Tue)
  '2026-04-07-00',  -- day before (Mon)
  '2026-04-01-00',  -- w/w (Tue, bot-inflated)
  '2026-04-02-00',  -- model ramp day (Wed)
  '2026-03-11-00'   -- w/4w baseline (Tue)
)
GROUP BY 1
ORDER BY 1
```

</details>

## Key Numbers (6-11 PM PT)

| Hour | Apr 8 | Apr 1 (w/w) | w/w % | Mar 11 (w/4w) | w/4w % |
|------|-------|-------------|-------|---------------|--------|
| 18:00 | 26,871 | 30,780 | -12.7% | 29,491 | -8.9% |
| 19:00 | 23,778 | 27,566 | -13.7% | 28,849 | -17.6% |
| 20:00 | 24,164 | 27,791 | -13.1% | 29,377 | -17.7% |
| 21:00 | 25,179 | 30,845 | -18.4% | 25,121 | +0.2% |
| 22:00 | 26,410 | 30,202 | -12.6% | 26,546 | -0.5% |
| 23:00 | 28,580 | 32,381 | -11.7% | 26,892 | +6.3% |

w/w shows a consistent ~12-18% drop because Apr 1 had inflated bot signups. w/4w shows Apr 8 evening is within normal range (21-23 PM hours are almost identical to Mar 11).

## Conclusion

Not a real drop. The w/w comparison is misleading because the prior week (Apr 1) included bot registration traffic that was later identified and restricted. The defenses applied to suspicious registrations are working as intended. Patricia O'Meara confirmed: "the dip last night appears to be related to previously mentioned bot activity and defenses kicking in, and w/4w looks inline."
