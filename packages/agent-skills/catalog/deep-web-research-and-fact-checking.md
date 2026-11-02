---
name: Deep Web Research & Fact Checking
slug: deep-web-research-and-fact-checking
category: research
description: "Practical SOPs, validation checks, and guardrails for deep web research & fact checking."
trigger_keywords: ["web", "search", "sources", "citations", "fact", "checking"]
required_tools: ["web_search", "web_scraper", "knowledge_rag"]
recommended_models: ["openai/gpt-4.1", "anthropic/claude-sonnet"]
---

## Purpose
Answer research questions with traceable evidence, balanced sourcing, and citations readers can verify.

## Standard operating procedure
1. Turn the request into concrete subquestions. Mark the date range, geography, and terms that need definition.
2. Search for primary evidence first: official datasets, filings, documentation, court records, original research, and direct statements. Use secondary sources to add context and discover counterevidence.
3. Verify every material claim against two independent sources when possible. Independence means distinct reporting or data origins, not two pages repeating the same release.
4. Record source title, publisher, publication/update date, URL, relevant passage, and retrieval date. Check whether the source supports the exact wording and scope of the claim.
5. Reconcile conflicts by comparing authority, methods, dates, and directness. State unresolved disagreement instead of choosing silently.
6. Write a concise synthesis, attach citations beside claims, and label inference, uncertainty, and missing evidence.

## Checklist
- [ ] Each answerable subquestion has evidence or an explicit evidence gap.
- [ ] High-impact facts have a primary source and an independent cross-check.
- [ ] Numbers retain units, population, geography, and time period.
- [ ] Quotes are exact, short, and linked to their source.
- [ ] Sources are current enough for the claim and are not circularly cited.

## Guardrails
Never invent citations, quotes, dates, or source contents. Do not treat search snippets as evidence. Separate observed fact from interpretation. For disputed or changing topics, disclose the source dates and uncertainty.

## Output template
### Findings
Answer first, followed by the strongest supporting facts.

### Evidence
Numbered claims with direct citations, dates, and brief source notes.

### Caveats
Conflicting evidence, assumptions, and questions that remain open.

## Golden example
If two current official sources report different totals, cite both, identify the population and cutoff each uses, and explain why the totals differ before recommending which definition matches the question.
