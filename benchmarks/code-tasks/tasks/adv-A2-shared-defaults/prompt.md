`python -m unittest test_team` fails: teams seem to leak state into each other. The bug is in the team/settings code
(`team.py`, `settings.py`). Fix it so that no object ever shares or mutates mutable state that belongs to another
object, a module-level default, or the caller, and so that behaviour is correct in general, not only for the cases in
`test_team.py`. Do not modify `test_team.py`.
