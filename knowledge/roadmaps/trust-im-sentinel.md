---
title: "Roadmap: Trust IM Sentinel"
date: 2026-04-06
type: roadmap
scope: org
projects: [davi, trust-im]
tags: [roadmap, iris, alerting, operational, trust-im, sentinel, davi]
people: [jcortes]
iris_app: davi
iris_url: "https://iris.prod.linkedin.com/applications/davi"
---

# Roadmap: Trust IM Sentinel

Operational health alerting for Trust IM products via the IRIS `davi` application. Covers service outages, stale data, widget errors, InResponse failures, and platform health — **not** abuse incident alerts (those stay on `liairp`).

## Phase 1: IRIS Application Configuration

### 1.1 Define Application Variables

Go to https://iris.prod.linkedin.com/applications/davi → **Edit Application**

Add these variables (one per line in the Variables field):

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
```

Set **Incident title variable** to: `title`

### 1.2 Fill Application Templates

All templates use Jinja2 syntax. Copy-paste these exactly:

#### Context Template
*(What users see when opening an incident in the IRIS web UI)*

```
<h2>{{ title }}</h2>
<table>
  <tr><td><b>Severity</b></td><td>{{ severity }}</td></tr>
  <tr><td><b>Source</b></td><td>{{ source }}</td></tr>
  <tr><td><b>Affected System</b></td><td>{{ affected_system }}</td></tr>
  <tr><td><b>Reporter</b></td><td>{{ reporter }}</td></tr>
  <tr><td><b>Date</b></td><td>{{ alert_date }}</td></tr>
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
*(One-liner shown in the incidents list view)*

```
[{{ severity | upper }}] {{ title }} — {{ source }}/{{ affected_system }}
```

#### Sample Context
*(JSON for testing plans — paste this exactly)*

```json
{
  "title": "Data freshness alert: u_tdsauto.data_egression_by_cohorts",
  "description": "Table u_tdsauto.data_egression_by_cohorts has not been updated in 26 hours. Expected refresh interval is 24h. Downstream alerting notebooks may produce stale results.",
  "severity": "major",
  "source": "DataFreshnessWidget",
  "affected_system": "u_tdsauto.data_egression_by_cohorts",
  "error_message": "Last partition: 2026-04-04T12:00:00Z. Current time: 2026-04-06T14:00:00Z. Delta: 26h (threshold: 24h).",
  "alert_url": "https://darwin.prod.linkedin.com/apps/publish/12345?execution_id=67890",
  "reporter": "davi-sentinel",
  "alert_date": "2026-04-06"
}
```

#### Mobile Template
*(What users see on the IRIS mobile app)*

```
{{ severity | upper }}: {{ title }}

Source: {{ source }}
System: {{ affected_system }}
{{ description }}
{% if error_message %}Error: {{ error_message }}{% endif %}
```

### 1.3 Checklist

- [ ] Add variables to davi app
- [ ] Set incident title variable to `title`
- [ ] Paste Context Template
- [ ] Paste Summary Template
- [ ] Paste Sample Context JSON
- [ ] Paste Mobile Template
- [ ] Verify supported modes: email, slack, im, call, sms are checked

## Phase 2: Create Notification Template

Go to https://iris.prod.linkedin.com/templates → **Create New Template**

**Template name:** `davi-sentinel`
**Application:** `davi`

### Email

**Subject:**
```
[DAVI {{ severity | upper }}] {{ title }}
```

**Body:**
```
DAVI Sentinel Alert

Title: {{ title }}
Severity: {{ severity | upper }}
Source: {{ source }}
Affected System: {{ affected_system }}
Date: {{ alert_date }}
Reporter: {{ reporter }}

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

### SMS

```
DAVI {{ severity | upper }}: {{ title }} ({{ source }}/{{ affected_system }}). Reply "{{ iris.incident_id }} claim" to claim.
```

### Slack / IM

```
:rotating_light: *DAVI Sentinel Alert*

*{{ title }}*
Severity: `{{ severity | upper }}`
Source: `{{ source }}`
System: `{{ affected_system }}`
Reporter: {{ reporter }}

{{ description }}

{% if error_message %}```{{ error_message }}```{% endif %}
{% if alert_url %}<{{ alert_url }}|View Execution>{% endif %}

_Incident {{ iris.incident_id }} | Plan: {{ iris.plan }}_
```

### Call

```
DAVI sentinel alert. Severity {{ severity }}. {{ title }}. Source: {{ source }}. Affected system: {{ affected_system }}.
```

### Checklist

- [ ] Create template `davi-sentinel` for app `davi`
- [ ] Fill email subject + body
- [ ] Fill SMS template
- [ ] Fill Slack/IM template
- [ ] Fill call template
- [ ] Save template

## Phase 3: Create Escalation Plan

Go to https://iris.prod.linkedin.com/plans → **Create New Plan**

**Plan name:** `davi-sentinel-plan`
**Description:** "Operational health alerts for Trust IM products (data freshness, service errors, widget failures)"

### Escalation Steps

| Step | Action | Role | Target | Priority | Template | Wait | Count |
|------|--------|------|--------|----------|----------|------|-------|
| 1 | Notify primary | oncall-primary | anti-abuse-incident-response | high | davi-sentinel | 5 min | 1 |
| 2 | Notify primary again | oncall-primary | anti-abuse-incident-response | urgent | davi-sentinel | 5 min | 1 |
| 3 | Notify secondary | oncall-secondary | anti-abuse-incident-response | urgent | davi-sentinel | 5 min | 1 |
| 4 | Notify manager | manager | anti-abuse-incident-response | urgent | davi-sentinel | — | 1 |

### Tracking Notification (Slack)

Enable tracking notification at the bottom of the plan creation page:
- **Mode:** Slack
- **Target:** `#davi-alerts` (or your team's alert channel)
- **Template for `davi` app:**

```
:rotating_light: *New DAVI Sentinel Incident*
*{{ title }}* | Severity: `{{ severity | upper }}`
Source: `{{ source }}` | System: `{{ affected_system }}`
{{ description }}
{% if alert_url %}<{{ alert_url }}|View Execution>{% endif %}
```

> **Note:** You must invite the **Iris** app to the Slack channel first. Type `@iris` in the channel and follow the prompt.

### Checklist

- [ ] Create plan `davi-sentinel-plan` with 4 escalation steps
- [ ] Set oncall target to `anti-abuse-incident-response`
- [ ] Configure Slack tracking notification
- [ ] Invite Iris app to the Slack channel
- [ ] Click **Publish Plan**
- [ ] Test plan using IRIS UI "Test Plan" button (uses Sample Context from Phase 1)

## Phase 4: DAVI Code Integration

Update DAVI to support the new `davi` IRIS app alongside the existing `liairp` app.

### 4.1 New Service: `TrustSentinelIrisService`

A new service (separate from `TrustAlertIrisService`) that fires ops alerts through the `davi` app:

```python
APP = "davi"
PLAN_PROD = "davi-sentinel-plan"
PLAN_TEST = "davi-sentinel-plan-test"  # create a test plan too
```

Context variables match Phase 1 variables: `title`, `description`, `severity`, `source`, `affected_system`, `error_message`, `alert_url`, `reporter`, `alert_date`.

### 4.2 HDFS API Key

From the existing roadmap (Phase 2.5 of davi-alerting.md):
- Store the `davi` app API key in HDFS (separate from `liairp` key)
- Path: `hdfs:///user/trustim/secrets/davi_iris_api_key`
- Service reads from HDFS if `DAVI_IRIS_API_KEY` env var is empty

### 4.3 Widget: `TrustSentinelIrisWidget`

Thin wrapper for use in Darwin health-check notebooks.

### Checklist

- [ ] Create `TrustSentinelIrisService` in lipy-davi
- [ ] Create `TrustSentinelIrisWidget` in lipy-davi
- [ ] Upload davi API key to HDFS
- [ ] Add HDFS key-reading utility
- [ ] Tests for new service
- [ ] Register in SERVICE_REGISTRY
- [ ] Run `mint build`

## Phase 5: Testing & Production Rollout

- [ ] Create test plan `davi-sentinel-plan-test` (targets `#alerting-framework` or dev channel)
- [ ] Test with `is_prod=False` from Darwin
- [ ] Test with `is_prod=False` from local dev
- [ ] Validate Slack tracking notification arrives
- [ ] Validate email/SMS escalation works
- [ ] Toggle `is_prod=True` on validated notebooks
- [ ] Monitor via IRIS incidents dashboard

## Architecture Summary

```
┌──────────────────────────────────────────────────────────────┐
│ Trust IM Alerting Architecture                               │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Abuse Incidents (existing)    Ops Health (new — sentinel)   │
│  ┌─────────────────────┐      ┌─────────────────────────┐   │
│  │ TrustAlertIrisService│      │ TrustSentinelIrisService│   │
│  │ app = "liairp"       │      │ app = "davi"             │   │
│  │ plan = trust-incident│      │ plan = davi-sentinel     │   │
│  │   -auto-alert        │      │   -plan                  │   │
│  │                      │      │                          │   │
│  │ Purpose:             │      │ Purpose:                 │   │
│  │ - Abuse spikes       │      │ - Service down           │   │
│  │ - Scraping alerts    │      │ - Stale data tables      │   │
│  │ - Trust incidents    │      │ - Widget errors          │   │
│  │                      │      │ - InResponse failures    │   │
│  │ Slack: #im_alerts    │      │ - Pipeline failures      │   │
│  └─────────────────────┘      │                          │   │
│                                │ Slack: #davi-alerts      │   │
│                                └─────────────────────────┘   │
│                                                              │
│  Oncall: anti-abuse-incident-response (go/oncall)            │
└──────────────────────────────────────────────────────────────┘
```

## Quick Reference

| Component | Name | URL |
|-----------|------|-----|
| IRIS App | `davi` | https://iris.prod.linkedin.com/applications/davi |
| Template | `davi-sentinel` | https://iris.prod.linkedin.com/templates/davi-sentinel (after creation) |
| Plan | `davi-sentinel-plan` | https://iris.prod.linkedin.com/plans/davi-sentinel-plan (after creation) |
| Oncall | `anti-abuse-incident-response` | https://oncall.prod.linkedin.com/team/anti-abuse-incident-response |
| API docs | IRIS REST API | go/iris-api-docs |
| Python client | `irisclient` | https://github.com/linkedin-multiproduct/iris-client |
