# Centered Settings dialog

Settings now opens in a bounded, centered dialog over the current screen, matching the supplied reference. The desktop frame is at most 1040 × 760 px with viewport gutters; smaller windows keep a visible margin. Navigation and settings content scroll independently. The close button stays within the dialog, outside the scrolling content. Native macOS window-control padding is no longer applied inside this floating panel.

The background remains visible and mounted, with `inert` and `aria-hidden` preserving modal keyboard/accessibility behavior. Closing returns to the screen that opened Settings, including Automations and Customizations, instead of always navigating to chat. Existing chat drafts and the team canvas remain mounted.

Validation:

- Frontend lint, TypeScript, all 89 unit tests and production build passed.
- Real Chromium: six settings tabs; forward/backward focus containment; close button and Escape; chat draft and component retention; original non-chat screen retention; close-button position after scrolling; dialog and controls within bounds at 1440, 768 and 390 px.
- Screenshot review found and removed an older rule hiding the background behind Settings. The final browser check additionally asserts that the background stays visible.
- Restricted-reference branding scan: zero matches in web/desktop source and packages.

Required repository-wide backend checks were attempted separately. Pytest was stopped after five minutes with no progress in `test_patcher_and_cost_savings.py`; it did not complete. Mypy reported 11 errors in six backend/runtime test files being edited independently. No Python files or dependencies are included in this UI change.
