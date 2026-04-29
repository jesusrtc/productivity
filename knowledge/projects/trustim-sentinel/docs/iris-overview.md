# How IRIS Works

IRIS is LinkedIn's incident management system. It handles alerting, escalation, and notification delivery. To set up monitoring for a new domain you configure three things: an Application, a Notification Template, and an Escalation Plan.

Note: The IRIS legacy UI (iris.prod.linkedin.com) is being deprecated. Incidents now show in Observe Escalation (observe.prod.linkedin.com/escalations). Filter by Source to find your app's incidents. Infrastructure fields like Fabric, Nodes, and Zones will show N/A for IRIS incidents since they are designed for service-level alerts.

## Application

An IRIS application is the top-level container. It defines the context your alerts will carry. You configure it at iris.prod.linkedin.com/applications.

- **Variables**: named fields that your code sends with each incident (e.g. `title`, `severity`, `source`). These are the data contract between your alerting code and your templates. One variable per line in the UI.
- **Incident title variable**: which variable IRIS uses as the incident title in its UI and lists. Must match one of the variables above.
- **Context Template**: HTML with Jinja2 syntax. Rendered when someone opens an incident in the IRIS web UI. This is the full detail view with all the context the oncall needs to triage. Should include all key variables in a readable layout.
- **Summary Template**: a single-line Jinja2 template shown in the incidents list view. Should be scannable at a glance so oncall can quickly prioritize.
- **Sample Context**: a JSON object with example values for all your variables. Used by the "Test Plan" button in the IRIS UI to preview how templates render before going live. Must include every variable.
- **Mobile Template**: plain text with Jinja2 syntax. Shown in the IRIS mobile app. Same information as the context template but without HTML.
- **Supported modes**: which notification channels the app supports. Check the ones you need: email, Slack, IM, SMS, call.

## Notification Template

A notification template defines how alerts look when delivered to the oncall. One template covers all delivery channels. You configure it at iris.prod.linkedin.com/templates.

Each template is linked to one application. It has separate fields for each channel:

- **Email**: subject line + body. Include enough context to triage without clicking links. Add claim instructions at the bottom (reply with incident ID).
- **Slack/IM**: formatted message using Slack markdown. Use backticks for severity/source, code blocks for errors, and link syntax for URLs.
- **SMS**: short one-liner with claim instructions. Must fit in a single SMS.
- **Call**: text-to-speech script read aloud when IRIS calls the oncall. Keep it brief, no special characters, spell out abbreviations.

All templates use Jinja2 syntax. Reference your application variables with `{{ variable_name }}`. Available filters include `{{ severity | upper }}`. Use conditionals for optional fields: `{% if error_message %}...{% endif %}`. IRIS provides built-in variables: `{{ iris.incident_id }}` and `{{ iris.plan }}`.

## Escalation Plan

An escalation plan defines who gets notified and in what order if the incident is not claimed. You configure it at iris.prod.linkedin.com/plans.

Each plan has a sequence of steps. If the oncall does not claim the incident within the wait time, IRIS moves to the next step. Each step specifies:
- **Role**: who to notify (oncall-primary, oncall-secondary, manager).
- **Target**: the oncall team from go/oncall.
- **Priority**: how urgently to notify (high, urgent).
- **Template**: which notification template to use.
- **Wait**: how long to wait before escalating to the next step.

Plans also support a **tracking notification**: a Slack message sent to a channel every time an incident is created under this plan. This gives the whole team visibility even if they are not on the escalation path. You must invite the Iris app to the Slack channel first (type `@iris` in the channel).

Once a plan is published, you can test it with the "Test Plan" button which uses the Sample Context from the application.

## Notifying Multiple Slack Channels

There are three ways to notify different Slack channels depending on the alert type:

### 1. Tracking Notification (per plan)
Each plan has one tracking notification channel. Every incident under that plan posts there. This is the "broadcast" for team visibility.

### 2. Dynamic Targets (per incident)
When your code fires an incident, you can pass extra targets at runtime:

```python
client.incident(
    plan_name,
    context,
    dynamic_targets=[
        {"role": "user", "target": "#im-scraping-oncall", "mode": "slack"}
    ]
)
```

This lets you decide at code level which additional channels to notify based on the alert type.

### 3. Multiple Plans (per domain)
Create separate plans for different alert categories. Same app, same templates, different routing. Each plan gets its own tracking channel and can have different escalation behavior.

## How It Fits Together

```
Your code builds a context dict with your variables
        |
        v
irisclient.IrisClient.incident(plan_name, context, dynamic_targets=[...])
        |
        v
IRIS creates an incident under your Application
        |
        +--> Context Template renders in IRIS web UI / Observe Escalation
        +--> Summary Template renders in incidents list
        +--> Tracking notification sent to plan's Slack channel
        +--> Dynamic target notifications sent to additional channels
        |
        v
Escalation Plan starts stepping through notifications
        |
        +--> Step 1: Notification Template renders for email/Slack/SMS/call
        +--> (wait) Step 2: escalate if unclaimed
        +--> (wait) Step 3: escalate further
        +--> Step 4: notify manager
```
