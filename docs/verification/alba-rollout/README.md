# Alba Agent rollout — 9 November 2026

This snapshot covers the desktop/web interface, account connections, model selection and agent-team execution. The application uses the owner-supplied ALBA master emblem. Existing data directories, encrypted API settings and internal `NEXUS_*` identifiers remain compatible.

## Automated checks

| Check | Observed result |
| --- | --- |
| Latest backend full suite | 649 passed, 21 skipped, 1 expected failure; one stale path-validation error-message assertion failed |
| Updated path-traversal regression cases | 5 passed: parent traversal, absolute paths, nested traversal, empty segments and reserved attempt filenames are rejected before provider creation |
| Terminal-interrupt test, isolated rerun | 1 passed; the later full suite also passed this test |
| Chromium private-pipe/takeover test, isolated rerun after an earlier startup timeout | 1 passed |
| Final studio/artifact-field regression suite | 56 passed, including HTML-only, report-only and paired deliverables, with missing files still rejected |
| Browser payload and HTML verification suites | 73 passed before the final six artifact-field cases were added |
| Strict mypy | 261 source files passed |
| Web ESLint, TypeScript, production build | Passed |
| Web tests | 82 passed |
| Desktop TypeScript and tests | 16 passed |
| Dependency license scripts | Passed: 340 reachable npm packages and 198 installed Python distributions |
| Restricted third-party branding scan in application/package source | No matches |
| Staged secret-pattern scan | No matches; provider credentials and local diagnostic logs are excluded |

The final full-suite failure was an outdated assertion matching the former flat-filename error text. The input contract now accepts safe relative paths for staged website artifacts; traversal remains rejected. Its updated five-case security test passed separately. The full suite and targeted rerun cover 654 passing backend cases; this is not a claim that one full-suite invocation was entirely green. Earlier timing failures passed on reruns. No timeout, verification or sandbox gate was relaxed.

## Live desktop checks

- Codex, Claude and Gemini each displayed **Connected** after a real provider reply. Claude initially returned 429; the later check succeeded. Plan availability can change independently of Alba.
- Copilot is absent from the account catalog, installation actions and model settings. A remembered Copilot model cannot silently use a different API account. Temporary local Copilot files were removed without enabling plaintext token storage.
- The official Codex model catalog populated the picker. **GPT-6.1-Sol / Low** was selected through the actual Model and Effort controls. Account programs own authentication; no subscription tokens were pasted into Alba.
- Clear Vietnamese website requests generated a real workflow. The Auto example created 12 visible canvas nodes and 32 agents; that large test was stopped after initial documents were produced. It is not presented as a finished website.
- A compact execution created a real `artifacts/index.html`. The assigned browser navigated to its managed loopback server and extracted the visible page text. A Start-button click used an explicit one-time approval.
- Chat controls were measured at 1440, 768 and 390 pixels with the auxiliary panel closed: Model, Effort, permissions and Send remained visible with no horizontal page overflow. On small screens an open auxiliary panel intentionally covers the chat.

## Runtime corrections verified by regression cases

Website sandbox nodes receive only browser/process tools actually enabled in their workspace. Browser navigation accepts both the documented nested argument shape and a flat URL payload, while model-supplied approval/human-control flags are stripped. HTML deliverables use the existing test-count, baseline discrimination and mutation thresholds. The mutation runner restores all implementation files before testing each mutant.

Crew outputs are checked against their actual file fields. An HTML-only `artifact_filename` no longer invents an additional media-report requirement. Declared missing artifacts still fail, and paired media/report recovery keeps its tool requirements.

Screenshots: [home](../../screenshots/alba-home.png), [agent canvas](../../screenshots/alba-canvas.png), [account connections](../../screenshots/alba-models.png).

## Canvas toolbar and Git credential follow-up

The run-log toggle now participates in the toolbar layout instead of floating above Save. Title and action groups wrap within the canvas container. Browser measurements at 1440, 1024, 768 and 390 pixels found no overlapping controls or horizontal page overflow; the log button uses normal static positioning. Generation labels show a count instead of a lineage identifier. The existing graph, node controls and inspector remain available.

The macOS Keychain dialog was caused by Git’s inherited `osxkeychain` credential helper. A repository-local empty helper resets that inherited helper for this checkout; the macOS Keychain itself and other repositories were not changed. A public read of the repository succeeded without invoking the helper. Publishing uses the authenticated GitHub connector in this session.
