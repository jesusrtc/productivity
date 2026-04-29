---
name: investigation-report-standards
description: >-
  Standards for writing investigation reports, notebooks, and Slack summaries.
  Covers language rules, notebook structure, recommendation formatting,
  threshold analysis, and common mistakes to avoid. Apply to all investigation
  output regardless of investigation type.
allowed-tools: Bash
---

# Investigation Report Standards

These standards apply to all investigation output: Jupyter notebooks, Google Docs audit trails, Slack summaries, and JIRA comments.

## 1. Language Rules

### Use objective, verifiable language

Every claim must be traceable to a query result.

| Do not write | Write instead |
|-------------|---------------|
| "The traffic is clearly malicious" | "The traffic shows 5.1 attempts/IP (3x the next highest country)" |
| "The attacker is evading detection" | "Between 03/31 and 04/02, the traffic spread to 44.8% more IPs while per-IP rate decreased from 5.81 to 4.69, consistent with rate-limit evasion" |
| "These accounts are NOT used for scraping" | "Zero Ultrascrapper labels were found; however the same result was observed for baseline accounts from all countries, making this inconclusive (see control group)" |
| "The throttling is indiscriminate" | "Throttling reduced all traffic proportionally, abusive and legitimate alike" |
| "This is likely a device farm" | "The UA distribution has a standard deviation of 30 across the top 15 user agents, consistent with emulator or device farm behavior (organic traffic follows power-law distributions)" |
| "We should block these IPs" | "Setting a drop threshold of >5/IP/day would cover 79% of the observed abusive traffic" |

Rules:
- Use "observed", "consistent with", "the data shows" instead of definitive claims
- Quantify everything: "X events from Y IPs (Z/IP)" not "lots of traffic from Italy"
- Never state a conclusion that requires assumptions. If assumptions are needed, state them explicitly.
- When a result is inconclusive, say so and explain why. Always run a control group before concluding "X is not happening."

### Avoid AI writing patterns

Reports will be read by directors and managers. They should read like a human engineer wrote them.

| Pattern to avoid | Why | Fix |
|-----------------|-----|-----|
| Em dashes (--) as parenthetical separators | Common AI pattern, instantly recognizable | Use commas, semicolons, periods, or parentheses |
| "Furthermore", "Moreover", "It's worth noting" | Filler that adds no information | Delete them |
| "Importantly", "Critically", "Notably" | Editorializing adverbs | Let the data speak; bold the number instead |
| Excessive bold/italic formatting | Looks machine-generated | Bold only key numbers and findings |
| "In conclusion", "To summarize" | Reader can see it's the last section | Just state the finding |
| "This represents a significant..." | Subjective magnitude | Give the number and let the reader judge |
| Starting every bullet with an action verb | Parallel structure obsession | Vary sentence structure naturally |
| Arrows for implications (X -> Y) | Use "to" or restructure the sentence | |

### Terminology precision

Be specific about what system, layer, or mechanism you are referring to. Different defense systems have different capabilities:
- Some systems drop/reject requests before processing
- Some systems assign challenges or friction
- Some systems restrict accounts after the fact
- Some systems flag for manual review

Do not say "block" when the system throttles. Do not say "restrict" when the system challenges. Use the actual terminology of the system being discussed.

## 2. Notebook Structure

Investigation notebooks should follow this structure. Each section is a markdown cell followed by code/query cells.

### Required sections in order:

1. **Executive Summary** (markdown)
   - What happened (1-2 sentences with key numbers)
   - Root cause (bullet points)
   - Key concerns (bullet points)
   - Recommended immediate actions (table with Priority, Action, Effort, Impact)

2. **Traffic/Volume Overview** (markdown + chart)
   - Baseline vs anomaly comparison table
   - Timeline of events
   - Figure: time-series showing the anomaly

3. **Root Cause Analysis** (markdown + chart)
   - Breakdown by the relevant dimension (country, IP org, member cohort, etc.)
   - Anomaly identification with specific metrics
   - Figure: breakdown chart

4. **Trend Analysis** (markdown + chart)
   - 7-day or 30-day lookback
   - Escalation or recurrence pattern identification
   - Figure: trend with baseline annotation

5. **Quantitative Impact Analysis** (markdown)
   - Coverage tables showing what percentage of the problem each threshold/rule would address
   - Separate tables for the target population and the general population
   - False positive risk assessment for each proposed threshold
   - Clearly label which defense system each recommendation targets

6. **Defense Effectiveness** (markdown)
   - How well did existing defenses perform?
   - What slipped through and why?
   - Cross-reference with other data sources (with control groups if the source has coverage limitations)

7. **Recommendations** (markdown)
   - Group by defense system/layer
   - Each recommendation backed by specific observed data
   - Prioritized roadmap with effort estimates

8. **Appendix** (markdown)
   - Data sources and tables used
   - Open items for follow-up
   - Reference data (member IDs, etc.)

### Cell organization rules:

- Each chart gets its own code cell
- Below each chart, add a markdown cell "Query used for Figure N:" followed by a code cell containing the SQL
- Do not mix narrative markdown with chart code in the same cell
- Code cells should be self-contained (import everything needed at the top)

## 3. Recommendation Formatting

### Understand the defense architecture before recommending

Before writing recommendations, map out which defense systems are involved and what each one does. For example, in a registration investigation there may be a throttle layer (drops requests), a scoring layer (assigns challenges), and a post-registration layer (restricts accounts). In a scraping investigation there may be rate limiters, block filters, and restriction pipelines.

Do not recommend an action for the wrong system. If traffic is being dropped before it reaches a scoring system, recommending score-based changes for that traffic is meaningless. Separate recommendations by system.

### Threshold recommendations must include coverage analysis

Do not recommend a threshold without showing what percentage of the problem it addresses and what the collateral impact is.

Bad:
> "Recommend dropping IPs with >20 attempts per day"

Good:
> | Threshold | Target IPs Affected | % of Abusive Traffic | Risk to Legitimate Users |
> |-----------|-------------|-----------------|------------------------|
> | >20/day | 637 | 11% | None observed (legit users at 1-3/day) |
> | >10/day | 4,507 | 50% | Minimal |
> | >5/day | 10,185 | 79% | Low |

### Scale recommendations to the problem size

If the problem involves thousands of entities (IPs, accounts, domains), do not provide a list of individual entities to act on. The top 50 out of 26,000 is 0.2% coverage. Instead:
- Show threshold coverage tables
- Identify signal combinations that concentrate the abusive traffic
- Show top 5 for reference to illustrate the pattern, not as an action list

### Always specify the defense system

| Priority | System | Action | Data Basis |
|----------|--------|--------|-----------|
| P0 | [name of system] | [specific action in that system's terms] | [observed data] |

## 4. Slack Summary Formatting

Slack summaries for directors/managers should be:

- **Short.** Under 20 lines. If longer, cut and link to the notebook.
- **Bullet points only.** No tables in Slack (they render poorly).
- **Findings only.** Do not include recommendations unless asked. Link to the notebook.
- **Lead with what happened and the root cause.** Not the methodology.
- **Notebook/doc link at the top**, not the bottom.

Structure:
```
Hi team, findings from the [date] [event type] investigation. Full notebook: `path/to/notebook.ipynb`

- [What happened, 1 line]
- [Root cause, 2-3 lines with key numbers]
- [What's working in defenses, 1 line]
- [What's not working, 1-2 lines]
- [Key data point for threshold decisions, 1-2 lines]
- [Any inconclusive findings with brief explanation, 1 line]
```

Do not include:
- Recommendation sections (save for the notebook)
- Tables (link to the notebook)
- Methodology descriptions
- Hedging language ("it's worth noting that...")

## 5. Common Report Mistakes

These caused revision rounds in past investigations:

1. **Concluding "X is not happening" from absence of data.** Zero results in a detection pipeline means either X is not happening OR the pipeline does not cover it. Always run a control group (check the same query against a known baseline). If the control group also returns zero, the result is inconclusive due to pipeline limitations.

2. **Recommending actions for the wrong defense system.** Map out what each system does before recommending. If a system drops requests before they reach scoring, score-based changes do not affect that traffic. Separate recommendations by system.

3. **Listing individual entities for a distributed problem.** If the problem involves thousands of IPs/accounts, a list of 50 is not actionable at scale. Show threshold/signal coverage tables instead.

4. **Using "block" when the system throttles, or "restrict" when it challenges.** Use the actual terminology of the system being discussed.

5. **Not showing false positive risk.** Every threshold recommendation needs a column showing the impact on legitimate users. Run the same threshold query without the abuse filter to see how many non-abusive entities fall in each bucket.

6. **Mixing data sources with different time ranges without noting it.** If you use an hourly table for the spike analysis and a daily table for the 30-day trend, state this in the appendix.

7. **Speculating about attacker intent without post-action data.** Registration data tells you about registration patterns. It does not tell you what the accounts will be used for. If you only have registration data, characterize the registration pattern, not the purpose.

8. **Writing a 40-line Slack summary.** The audience is directors. Keep it under 20 lines with bullet points. Link to the notebook for everything else.
