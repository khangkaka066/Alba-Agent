---
name: Executive Report & Document Authoring
slug: executive-report-and-document-authoring
category: writing
description: "Practical SOPs, validation checks, and guardrails for executive report & document authoring."
trigger_keywords: ["executive", "report", "memo", "document", "authoring"]
required_tools: ["report_exporter"]
recommended_models: ["openai/gpt-4.1-mini", "anthropic/claude-sonnet"]
---

## Purpose
Create concise reports and polished documents that lead with the decision and preserve evidentiary context.

## Standard operating procedure
1. Identify the audience, decision or action needed, requested length, tone, and delivery format.
2. Use the Pyramid Principle: state the recommendation or answer first, group supporting reasons, then provide evidence and detail.
3. Separate facts, calculations, interpretations, and recommendations. Attach source notes to material claims and define technical terms.
4. Use consistent headings, parallel bullet grammar, compact tables, descriptive labels, and stable units. Keep table headers with their data and avoid excessively wide layouts.
5. Write an informative title and an executive summary that stands alone. Move methodology, definitions, and detailed evidence to appendices when useful.
6. Render or parse the final Markdown, DOCX, or PDF and inspect page breaks, table wrapping, heading hierarchy, links, and special characters.

## Checklist
- [ ] The first paragraph answers the requested question or gives the decision.
- [ ] Each section supports one clear point.
- [ ] Tables include units, periods, and source notes.
- [ ] Claims can be traced to their evidence.
- [ ] Exported files are readable and have no broken layout.

## Guardrails
Do not imply certainty beyond the evidence. Preserve important dissent and caveats. Do not include confidential details in broadly distributed summaries without authorization.

## Output template
### Executive summary
Decision, key reason, and expected impact.

### Evidence and analysis
Grouped findings with metrics and sources.

### Recommendation
Action, owner, timing, and dependencies.

### Appendix
Definitions, methodology, and detailed tables.

## Golden example
Replace a long chronological activity log with one decision sentence, three evidence-backed drivers, a compact table with units and comparison periods, and an appendix containing methods and source details.
