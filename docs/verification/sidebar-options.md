# Sidebar conversation options

The options button beside Projects opens a compact nested menu matching the supplied reference. It controls project grouping, conversation sorting (actual update/creation times or name), project sorting, text/status/unread filters, timestamps/status icons/density, active-task auto pinning, archived-only view and marking everything read. Conversation menus provide manual pinning, read/unread, archive/unarchive and the existing confirmed deletion. Project menus move projects up/down in custom order.

Preferences and markers persist in localStorage under an account/workspace-scoped internal key. Archive only changes this device's sidebar visibility; it does not delete server data. Existing tenant authorization and backend isolation are unchanged.

Verified:

- `pnpm lint`, `pnpm check`, production web build: passed.
- `pnpm test`: 89 passed, including seven new behavioral tests covering ordering, filtering, archives, read activity, pinning, custom project order and storage validation/isolation.
- Real Chromium against the embedded app: all eight reference menu rows; sorting/display persistence after reload; pin/unread/mark-all-read/archive/unarchive; ArrowRight/ArrowLeft/Escape and focus return; menu bounds at 1440, 768 and 390 px.
- Source branding check for restricted reference names: no matches in web/desktop source and packages.
- Embedded frontend refreshed and Alba Agent reopened with the new menu.

Repository-wide backend checks were also attempted. The initial bundled-Python run reported 628 passed, 27 failed, 20 skipped and one expected failure; rerunning with process permissions resolved 25 failures. The remaining sandbox-command test passed with the project's Python 3.11 on PATH (all six tests in that module passed). The Redis queue integration test still requires a reachable configured Redis. `mypy packages/ apps/api/` reported five errors in three runtime/backend files outside this UI change. Concurrent backend edits were left untouched and are excluded from this commit.
