# Trust IM Sentinel - One Pager

## Background

Trust IM now owns multiple multiproducts for alerting, running pipelines, enforcement artifacts, and investigation tools. None of these have unified operational monitoring. Failures are discovered manually, often days late or not at all. The team has an oncall rotation for abuse incidents, but no mechanism to monitor the health of our own systems.

Recent examples of silent failures:
  - Scraping alert pipeline uptime was below 50% (Feb-Mar 2026).
  - Telesign cost alert was not running - elevated costs across several regions went undetected for weeks because the alert schedule had silently stopped. Discovered manually during a budget review, not by monitoring.    
  - Error in alerts due to upstream data gaps
  - Widget errors that are noticed only after stakeholders flag them (e.g InVizor or GaiProxyWidget).
  

## Proposed Solution

Create a dedicated IRIS escalation plan (trustim-sentinel) that monitors the operational health of all Trust IM products and routes alerts to the existing anti-abuse-incident-response oncall. This separates operational health alerts from abuse incident alerts while keeping a single oncall responsible for both.

The sentinel monitors domains like:
  - **Alert pipelines** - did each notebook run, did it produce alerts, did the IRIS incident actually fire.
  - **Data freshness** - are upstream tables landing on time.
  - **Widget and service health** - are DAVI widgets, InVizor reports, Working as expected? unnoticed errors on inResponse?.
  - **Enforcement artifact health** - are ASTA jobs, Drools rules, and mass actions running as expected, with nearline anomaly detection beyond the current weekly email.

### IRIS Configuration

See [iris-overview.md](iris-overview.md) for how IRIS applications, templates, and plans work.

#### Application Variables

```
title
description
severity
source
affected_system
error_message
alert_url
reporter
alert_date
suggested_owner
```

Incident title variable: `title`

#### Context Template

```html
<h2>{{ title }}</h2>
<table>
  <tr><td><b>Severity</b></td><td>{{ severity }}</td></tr>
  <tr><td><b>Source</b></td><td>{{ source }}</td></tr>
  <tr><td><b>Affected System</b></td><td>{{ affected_system }}</td></tr>
  <tr><td><b>Reporter</b></td><td>{{ reporter }}</td></tr>
  <tr><td><b>Date</b></td><td>{{ alert_date }}</td></tr>
  <tr><td><b>Suggested Owner</b></td><td>{{ suggested_owner }}</td></tr>
</table>
<h3>Description</h3>
<p>{{ description }}</p>
{% if error_message %}
<h3>Error</h3>
<pre>{{ error_message }}</pre>
{% endif %}
{% if alert_url %}
<p><a href="{{ alert_url }}">View Execution</a></p>
{% endif %}
```

#### Summary Template

```jinja2
[{{ severity | upper }}] {{ title }} - {{ source }}/{{ affected_system }}
```

#### Sample Context

```json
{
  "title": "Data freshness alert: u_tdsauto.data_egression_by_cohorts",
  "description": "Table u_tdsauto.data_egression_by_cohorts has not been updated in 26 hours. Expected refresh interval is 24h.",
  "severity": "major",
  "source": "data_freshness",
  "affected_system": "u_tdsauto.data_egression_by_cohorts",
  "error_message": "Last partition: 2026-04-04T12:00:00Z. Current time: 2026-04-06T14:00:00Z. Delta: 26h (threshold: 24h).",
  "alert_url": "https://darwin.prod.linkedin.com/apps/publish/12345?execution_id=67890",
  "reporter": "sentinel-watchdog",
  "alert_date": "2026-04-06",
  "suggested_owner": "klarocqu (egression pipeline owner)"
}
```

#### Mobile Template

```jinja2
{{ severity | upper }}: {{ title }}

Source: {{ source }}
System: {{ affected_system }}
Suggested Owner: {{ suggested_owner }}
{{ description }}
{% if error_message %}Error: {{ error_message }}{% endif %}
```

#### Notification Template (trustim-sentinel)

**Email Subject:**
```jinja2
[SENTINEL {{ severity | upper }}] {{ title }}
```

**Email Body:**
```jinja2
Trust IM Sentinel Alert

Title: {{ title }}
Severity: {{ severity | upper }}
Source: {{ source }}
Affected System: {{ affected_system }}
Date: {{ alert_date }}
Reporter: {{ reporter }}
Suggested Owner: {{ suggested_owner }}

{{ description }}

{% if error_message %}
Error Details:
{{ error_message }}
{% endif %}

{% if alert_url %}
Execution: {{ alert_url }}
{% endif %}

---
Incident ID: {{ iris.incident_id }}
Reply "{{ iris.incident_id }} claim" to claim this incident.
```

**Slack / IM:**
```jinja2
:rotating_light: *Trust IM Sentinel Alert*

*{{ title }}*
Severity: `{{ severity | upper }}`
Source: `{{ source }}`
System: `{{ affected_system }}`
Reporter: {{ reporter }}
Suggested Owner: {{ suggested_owner }}

{{ description }}

{% if error_message %}```{{ error_message }}```{% endif %}
{% if alert_url %}<{{ alert_url }}|View Execution>{% endif %}

_Incident {{ iris.incident_id }} | Plan: {{ iris.plan }}_
```

**SMS:**
```jinja2
SENTINEL {{ severity | upper }}: {{ title }} ({{ source }}/{{ affected_system }}). Reply "{{ iris.incident_id }} claim" to claim.
```

**Call:**
```jinja2
Trust IM sentinel alert. Severity {{ severity }}. {{ title }}. Source: {{ source }}. Affected system: {{ affected_system }}.
```

#### Escalation Plan (trustim-sentinel-plan)

| Step | Role | Target | Priority | Template | Wait |
|------|------|--------|----------|----------|------|
| 1 | oncall-primary | anti-abuse-incident-response | high | trustim-sentinel | 5 min |
| 2 | oncall-primary | anti-abuse-incident-response | urgent | trustim-sentinel | 5 min |
| 3 | oncall-secondary | anti-abuse-incident-response | urgent | trustim-sentinel | 5 min |
| 4 | manager | anti-abuse-incident-response | urgent | trustim-sentinel | - |

**Tracking Notification** (Slack to #trustim-sentinel-alerts):
```jinja2
:rotating_light: *New Sentinel Incident*
*{{ title }}* | Severity: `{{ severity | upper }}`
Source: `{{ source }}` | System: `{{ affected_system }}`
Suggested Owner: {{ suggested_owner }}
{{ description }}
{% if alert_url %}<{{ alert_url }}|View Execution>{% endif %}
```

## Requirements

- Dedicated IRIS application (trustim-sentinel) with its own escalation plan, separate from the abuse-incident liairp application.
- Oncall routing to anti-abuse-incident-response - same team handles both abuse incidents and operational health, but alerts are clearly distinguished by source.




## References

- [Scraping Alert Data Pipeline Assessment](https://docs.google.com/document/d/10Ma3QQvPIHiMg1uWvjAxw-ysNkpQwG9H4fyEWO4LxiI/edit)
- [Scraping Alerting Revamp](https://docs.google.com/document/d/1Kp7ZSSpPuhFuA-FNjBcymzMNqUc1K110PnR9XhoPnek/edit)
- [Enforcement Health One Pager](https://docs.google.com/document/d/1bbe3MBWJCoAB2CA14j9Z-Rr-hhX6dPNVQSuqgBjEjg8/edit)
- [Project Enforcement Health](https://docs.google.com/document/d/13sigdBmzthTJbW9lnCFket2GXq7ozOQ2tsXo2pkR-BY/edit)
