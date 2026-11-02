---
name: Full Stack Code Audit & Testing
slug: full-stack-code-audit-and-testing
category: engineering
description: "Practical SOPs, validation checks, and guardrails for full stack code audit & testing."
trigger_keywords: ["code", "audit", "security", "OWASP", "pytest", "debugging"]
required_tools: ["sandbox_shell", "browser_automation"]
recommended_models: ["anthropic/claude-sonnet", "openai/gpt-4.1"]
---

## Purpose
Review code for correctness, security, maintainability, and reproducible test coverage.

## Standard operating procedure
1. Identify entry points, trust boundaries, authentication/authorization checks, sensitive data paths, and external side effects before editing.
2. Reproduce the reported behavior with the narrowest safe test or trace. Preserve the failing case as a regression test.
3. Review input validation, tenant scoping, injection risks, path traversal, SSRF, secrets handling, permissions, cryptographic use, and dependency exposure.
4. Trace error paths, concurrency, retries, timeouts, cleanup, and partial failures. Check idempotency and race conditions around state changes.
5. Write pytest cases for normal behavior, invalid inputs, boundary values, authorization failures, and regression scenarios. Avoid tests that depend on live services unless explicitly required.
6. Run the relevant formatter, linter, type checker, and test suite. Report findings by severity with file and line references and a concrete exploit or failure path.

## Checklist
- [ ] Every claimed bug is reproducible or clearly marked as a risk hypothesis.
- [ ] Tenant and workspace isolation is enforced at data access boundaries.
- [ ] External calls have bounded timeouts and safe redirect/network rules.
- [ ] Tests cover both success and rejection paths.
- [ ] No secret, private data, or unsafe command appears in logs.

## Guardrails
Never run destructive commands or execute untrusted code outside the approved sandbox. Do not weaken a security control merely to make a test pass. Minimize changes and preserve existing public contracts unless change is intended.

## Output template
### Findings
Severity, location, impact, and reproduction.

### Tests performed
Commands and outcomes.

### Fixes
Minimal patch and regression coverage.

### Remaining risks
Unverified assumptions or broader follow-up.

## Golden example
For a suspected tenant leak, construct two tenants with similar identifiers, issue a cross-scope request, assert a not-found/forbidden response, and verify no data or side effect was produced in the other tenant.
