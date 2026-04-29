## DAVI State of the Union

**Owner:** Jesus Talamantes
**Team:** Trust IM, Detection Engineering
**April 2026**

### Background

The Investigations organization lacks a centralized and searchable repository for investigative automations. Investigation scripts are scattered across local Jupyter notebooks, not version-controlled, not discoverable, not reusable. Analysts spend 30-120 minutes per investigation on repetitive data gathering. When an analyst solves a complex case, the intelligence stays in their local notebook. The organization learns, but the system does not.

Two analysts investigating the same alert can reach different conclusions because they query different tables, apply different thresholds, or miss a signal the other caught.
### Summary

DAVI (Dynamic Analytics & Visualizations for Investigations) is a library of reusable, tested investigation automations called **widgets**. Each widget is an autonomous module that performs a specific investigation task. An analyst finds the right widget, runs it, and gets a result. This helps test hypothesis quickly.

Widgets are:
- **Tested.** Peer-reviewed code with unit and integration tests. Same input, same output, every time.
- **Discoverable.** Indexed in a searchable catalog. Analysts find existing widgets instead of rebuilding them.
- **Reusable.** One widget serves every analyst, every case. Built once, leveraged across the organization.
- **Version-controlled.** Logic improves over time through code review. Changes are tracked, rollbacks are possible.

Benefits:
- **Time to Understand (MTTU).** Each widget saves 10-40 minutes per investigation. Analysts spend time on decisions, not data gathering. For example, InVizor saves 40+ hours weekly on scraping reviews and is used by TI, IM, and AI teams.
- **Investigation reliability.** Every analyst runs the same tested, peer-reviewed logic. Results can be trusted for enforcement decisions and leadership reporting.
- **Coverage capacity.** Faster per-investigation time means each analyst handles more alerts. The team scales investigations without scaling headcount proportionally.
- **Onboarding time.** New investigators use widgets from day one. The widget encodes expert knowledge that would otherwise take weeks to acquire.

### What We Delivered

**15 production widgets** covering core investigation tasks:

<table style="border-collapse: collapse; width: 100%;">
  <tr style="background-color: #d9d9d9;">
    <th style="border: 1px solid #000; padding: 6px;">Widget</th>
    <th style="border: 1px solid #000; padding: 6px;">What It Does</th>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">InVizor</td>
    <td style="border: 1px solid #000; padding: 6px;">Track and analyze scraping activity for a specific member</td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">AlertPlot</td>
    <td style="border: 1px solid #000; padding: 6px;">Detect anomalies: period-over-period spikes, IQR outliers, rolling z-scores</td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">MagicPlot</td>
    <td style="border: 1px solid #000; padding: 6px;">Auto-detect data type and generate the right visualization</td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">SurfaceVisualization</td>
    <td style="border: 1px solid #000; padding: 6px;">Analyze registration traffic with natural language filtering</td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">DIHE</td>
    <td style="border: 1px solid #000; padding: 6px;">Analyze Detected Inauthentic Account Harmful Experience metrics</td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">KeywordsAnalysis</td>
    <td style="border: 1px solid #000; padding: 6px;">Analyze search activity for specific keywords</td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">IPActivity</td>
    <td style="border: 1px solid #000; padding: 6px;">Analyze search activity from an IP perspective</td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">SearchTermRanking</td>
    <td style="border: 1px solid #000; padding: 6px;">Rank search terms by member IDs</td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">GenericAgentic</td>
    <td style="border: 1px solid #000; padding: 6px;">Flexible data processing with custom prompts</td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">UaReviewAgentic</td>
    <td style="border: 1px solid #000; padding: 6px;">Comprehensive user agent analysis with restriction insights</td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">AgenticAnalytics</td>
    <td style="border: 1px solid #000; padding: 6px;">AI-powered analytics from natural language</td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">Email</td>
    <td style="border: 1px solid #000; padding: 6px;">Send internal investigation emails</td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">CopyToClipboard</td>
    <td style="border: 1px solid #000; padding: 6px;">Copy data out of investigations in manageable chunks</td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">CopyFromClipboard</td>
    <td style="border: 1px solid #000; padding: 6px;">Load CSV or Excel data into an investigation</td>
  </tr>
  <tr>
    <td style="border: 1px solid #000; padding: 6px;">GaiProxy</td>
    <td style="border: 1px solid #000; padding: 6px;">Direct proxy for Generative AI calls</td>
  </tr>
</table>

**Platform capabilities:**
- Searchable widget catalog for discovery across the organization
- Consistent visualization styling across all widgets
- Widget usage tracking for measuring adoption and impact
- Standardized contribution process so any team member can create and submit widgets through peer review

### Key Learnings

- **Tested code over scattered notebooks.** When investigation logic is in peer-reviewed code, it gets better over time. When it lives in a local notebook, it gets lost.
- **Discoverability drives adoption.** If people can't find it, they'll recreate it.
- **Low barrier drives usage.** One-command imports and auto-configured visualizations meant analysts used widgets without understanding the internals.
- **The library compounds.** Reusability and leverage grow with every widget contributed.
- **Platform-agnostic design pays off.** Building widgets as independent modules made it possible to later expose the same logic through other interfaces.
