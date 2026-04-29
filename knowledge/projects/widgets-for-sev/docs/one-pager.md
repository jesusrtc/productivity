## Widgets for SEV Metrics and L1 Analysis

**Owner:** Jesus Talamantes
**Team:** Trust IM, Detection Engineering
**April 2026**

### Proposal

Codify the SEV framework (metrics, thresholds, SEV level assignment, and L1 analysis) as tested widgets, then have every consumer call the same widgets. One piece of logic serves four consumers:

- **IM Alerting Engine** calls widgets to evaluate thresholds and trigger SEVs. No separate alerting implementation that can drift from the framework.
- **Scheduled monitoring jobs** (Darwin) call widgets on a schedule to track metric health.
- **Human investigators** call the same widgets in Darwin or Claude Code to validate a SEV and run L1 analysis on demand.
- **AI agents** call the same widgets during agent-led triage.

Same tested code, same results, wherever it runs. When the framework evolves (thresholds tuned, modifiers revised, new metrics added), the widget updates and every consumer gets the new behavior without coordination across teams.

### Background

The V1 SEV framework (ratified April 13, 2026) defines what constitutes an abuse SEV, how severity is assigned, and the 48-hour L1 analysis commitment for every triggered SEV. See [Abuse Incidents Sev Framework 1-pager](https://docs.google.com/document/d/1I9f7l93fHWaXA_DcsWk-rjS0oj2OY8Et2LXArrnjAXE/edit).

The framework is the authoritative definition. Today the implementation is scattered:

- **Alerting logic** lives in the IM Alerting Engine, translated from framework docs by engineers.
- **Thresholds** live in Google Docs, then duplicated into alert configurations.
- **L1 analysis** lives as one-off Darwin notebooks and tribal knowledge, with the framework explicitly flagging "On-demand, one-click Darwin notebooks to perform standard metric cuts" as a short-term need.
- **Investigator triage** depends on each analyst's interpretation of the framework.

Each consumer implements the framework its own way. When the framework changes, the updates happen asynchronously across all of them.

The March 18 Agility DRI decision made this sharper: the framework needs "a scalable L1 analysis suite that is comprehensive and high quality enough that, if run and finds no anomalies, we should have confidence in closing the SEV." That suite does not exist yet.

### Why This Matters

The framework targets 90% of SEV 0 and all prevalence/report incidents mitigated in SLA, and 80% of abuse incidents detected by ongoing Trust monitoring. Hitting these targets depends on a 48-hour L1 completion that is currently manual and inconsistent.

The risks of keeping the implementation scattered:

- **Alerts disagree with investigator findings.** The IM Alerting Engine fires based on one interpretation of the threshold, the investigator evaluates it using another, and the team wastes cycles reconciling which is right.
- **L1 analysis cannot meet the 48-hour SLA at scale.** Manual cuts across cohorts, surfaces, defenses, and data health checks take too long. Without widgets, each analyst writes the same queries from scratch.
- **False positives are hard to close quickly.** The framework wants confidence in closing SEVs when L1 finds nothing. Without a comprehensive, tested L1 suite, "nothing found" is not trustworthy.
- **Framework drift.** When thresholds or metrics change, the alert config, the investigator playbook, and the ad-hoc notebooks drift apart. There is no single place that represents the current framework.
- **Audit gap.** "Why was this a SEV 2?" and "why did this alert fire?" should be answered by the same tested logic. Today the answer depends on which system you ask.

### What We Propose

Build the widget suite that the framework needs. Organized by consumer:

**Metric widgets (the True North set).** One widget per metric covered by the framework:
- Prevalence @ Response (T28D)
- ATO self reports (T7D)
- ATO member reports (T7D)
- FA member reports (T7D)
- Private Content Reports (T7D)
- Public Content Reports (T7D)
- Scraped Data Freshness

Each widget computes the metric, its magnitude (% change), and its velocity (WoW, Wo4W). These are the same values the alerting engine needs to evaluate thresholds, the same values investigators quote when validating a SEV, and the same inputs L1 analysis uses for the "magnitude and velocity" question.

**Threshold and SEV level assignment widgets.** Given a metric value and its movement, output the SEV level. Extends SevCalculator to cover the full framework (magnitude, velocity, modifiers, unknown cohort handling, pre and post-triage adjustments). The IM Alerting Engine calls this to decide whether to fire.

**L1 analysis widgets** (the bounded question set from the framework):

*For all metrics:*
- Data pipeline health check (flow failures, missing data, missing partitions, delays). Rules out system problems before investigating abuse.
- Metric reliability check (upstream dependencies, sample size). Critical for prevalence.

*For entity-based metrics:*
- Abuser cohort breakdown (account age, NDA, MLC, entitlements, authenticity tier, restriction history, FA or ATO)
- Victim cohort breakdown (jobseekers, verified members, new members)
- Surface breakdown (7 core surfaces: Invites, Messages, Feed posts, Comments, Group posts, Jobs, Ads)
- Defense effectiveness check (restrictions, limits, challenges)
- Product ramp check (was there a recent ramp that could explain the movement?)
- Defense regression check (did a model's precision or recall change?)

*For population-based metrics:*
- Built-in breakdown widgets using whatever dimensions the metric supports (e.g., harm_type for prevalence NDA<28d)

Chained together, these produce the L1 48-hour output template: *"The movement is real. It is driven by [cohort] with [characteristics], doing [activities], affecting [victims]. Our defenses [performed as follows]. Corroborating evidence from other metrics: [X]."*

**Alert verification.** Given a fired alert, call the relevant widgets and confirm the underlying metric actually crossed the threshold. Flags discrepancies between the alerting engine and the widget suite.

### Scope

**In scope:**
- True North metrics defined in the V1 SEV framework
- Threshold evaluation and SEV level assignment (full framework, including modifiers)
- L1 analysis cuts defined in the framework's bounded question set
- Alert verification
- Same widgets available to IM Alerting Engine, scheduled monitoring, Darwin investigators, and Claude Code agents

**Not in scope:**
- L2 analysis (attacker MO deep dive). Still requires human judgment and exploratory investigation.
- Mitigation decisions (what action to take). Remains with IM and product teams.
- Alert routing, escalation, and SEV case management. Handled by InResponse and existing infrastructure.
- The SEV framework itself. Widgets implement the framework, they do not define it.

### Roadmap

<table style="border-collapse: collapse; width: 100%;">
  <tr style="background-color: #d9d9d9;">
    <th style="border: 1px solid #000; padding: 6px;">Milestone</th>
    <th style="border: 1px solid #000; padding: 6px;">Description</th>
    <th style="border: 1px solid #000; padding: 6px;">Status</th>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">True North metric widgets</td>
    <td style="border: 1px solid #000; padding: 6px;">Prevalence @ Response (T28D), ATO self reports, ATO member reports, FA member reports, Private/Public Content Reports, Scraped Data Freshness. Each computes value, magnitude, and velocity.</td>
    <td style="border: 1px solid #000; padding: 6px;"></td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">Threshold evaluation and SEV level assignment</td>
    <td style="border: 1px solid #000; padding: 6px;">Extend SevCalculator to cover the full V1 framework: all modifiers, unknown cohort handling, pre and post-triage adjustments.</td>
    <td style="border: 1px solid #000; padding: 6px;"></td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">L1 data health widgets</td>
    <td style="border: 1px solid #000; padding: 6px;">Pipeline health, metric reliability, and upstream dependency checks. Rules out system problems first so SEVs are not triggered on data issues.</td>
    <td style="border: 1px solid #000; padding: 6px;"></td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">L1 cohort and surface widgets</td>
    <td style="border: 1px solid #000; padding: 6px;">Abuser cohort, victim cohort, and surface breakdowns for entity-based metrics. Produces the "who, doing what, affecting whom" part of the L1 output.</td>
    <td style="border: 1px solid #000; padding: 6px;"></td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">L1 defense and regression widgets</td>
    <td style="border: 1px solid #000; padding: 6px;">Defense effectiveness, product ramp check, model precision/recall regression check. Produces the "defenses performed as follows" part of the L1 output.</td>
    <td style="border: 1px solid #000; padding: 6px;"></td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">IM Alerting Engine integration</td>
    <td style="border: 1px solid #000; padding: 6px;">IM Alerting Engine calls the metric and threshold widgets to fire SEVs. One source of truth for alerting logic.</td>
    <td style="border: 1px solid #000; padding: 6px;"></td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">Alert verification</td>
    <td style="border: 1px solid #000; padding: 6px;">Given a fired alert, call the widgets to independently confirm whether the underlying metric crossed the threshold. Flag discrepancies.</td>
    <td style="border: 1px solid #000; padding: 6px;"></td>
  </tr>
</table>

### Benefits

- **One framework, one implementation.** Alerting, monitoring, investigator triage, and L1 analysis all call the same widgets. Framework changes propagate everywhere at once.
- **48-hour L1 becomes mechanically achievable.** The bounded question set from the framework becomes a chain of widget calls rather than hours of manual SQL per investigation.
- **Closing SEVs on "nothing found" is trustworthy.** When the L1 suite runs end to end and reports no anomalies, that conclusion comes from comprehensive, tested logic, supporting the March 18 Agility decision.
- **Alerts are independently verifiable.** The alerting engine and the investigator use the same widgets. Disagreements surface as bugs, not as differing opinions.
- **Audit-ready.** Every SEV assignment and every L1 finding is backed by a widget output that can be rerun and reproduced.

### Success Metrics

- **SEV framework coverage.** Percentage of V1 framework metrics and L1 cuts implemented as tested widgets. Target: 100%.
- **Alerting integration.** Percentage of SEV-triggering alerts that call widgets instead of duplicated threshold logic. Target: 100%.
- **L1 completion time.** Median time from SEV trigger to completed L1 output. Target: well under the 48-hour SLA.
- **SEV close confidence.** Percentage of closed SEVs backed by a comprehensive L1 run (all relevant widgets executed, results recorded). Target: 100%.
- **Framework-to-widget lag.** Time between a framework change and the corresponding widget update. Target: near-zero.

### Appendix: Why DAVI Widgets

DAVI is the right tooling for this work:

- **Dual-environment execution.** DAVI widgets are the only mechanism at LinkedIn where the same tested investigation code runs in both scheduled Darwin jobs and Claude Code sessions. This is required because the same SEV logic needs to execute in scheduled alerting pipelines, in Darwin notebooks for human investigators, and in Claude Code for agent-led triage.
- **Tested, peer-reviewed, versioned.** Widgets are Python with unit and integration tests, version-controlled, and reviewed. Changes are traceable, rollbacks are possible. This is the baseline of rigor required for logic that drives SEV assignment and alerting.
- **Existing foundation to extend.**
  - **SevCalculator** already implements initial SEV level assignment based on magnitude and velocity. The V1 framework (modifiers, unknown cohort handling, pre and post-triage adjustments) is a natural extension.
  - **AlertPlotWidget** already provides period-over-period spikes, IQR outliers, and rolling z-scores. This is the same statistical math the framework's magnitude and velocity thresholds depend on, and directly supports the L1 material-increase check.

The work ahead is extending what already works and plugging it into the IM Alerting Engine, not starting from scratch.
