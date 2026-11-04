"""Command policy for the local sandbox: Deny > Ask > Allow.

This is the first layer only. A command is read as text, and text can be disguised (a script that builds a path at run time, an
interpreter one-liner). The enforcing layer is the operating-system sandbox in ``local_provider``, which blocks the same paths at the
kernel no matter how the command is written. The policy exists to refuse obvious abuse early, to say why, and to route the commands a
person should confirm to an approval instead of failing silently.

There is deliberately no allowlist of "safe commands": inside the kernel sandbox everything that is not denied or asked about may run,
and an allowlist would only be one more place for a bypass to hide. ``strict`` is the profile that does not trust that boundary: every
command that is not denied needs an approval.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum


class Decision(StrEnum):
    DENY = "deny"
    ASK = "ask"
    ALLOW = "allow"


# Commands a person has just approved, set by the supervisor around one call after the approval guard accepted it. A context variable
# rather than a parameter so the provider interface stays the same for Docker and the cloud drivers, and so an approval cannot leak into
# another request that runs at the same time.
approved_commands: ContextVar[frozenset[str]] = ContextVar("approved_commands", default=frozenset())

_RANK = {Decision.DENY: 0, Decision.ASK: 1, Decision.ALLOW: 2}


@dataclass(frozen=True)
class Rule:
    decision: Decision
    pattern: re.Pattern[str]
    reason: str
    needs_network: bool = False  # an approved ask of this kind runs that one command with the network open


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    reason: str
    needs_network: bool = False


def _rule(decision: Decision, pattern: str, reason: str, needs_network: bool = False) -> Rule:
    return Rule(decision, re.compile(pattern, re.IGNORECASE), reason, needs_network)


# Files whose contents are credentials. Example files that only document a variable name are fine to read.
SECRET_FILE = r"(?:^|[\s/'\"=:])\.env(?:\.(?!example\b|sample\b|template\b)[\w-]+)?(?=$|[\s'\";|&)<>])"
SECRET_DIRECTORY = r"(?:\.ssh|\.aws|\.gnupg|\.kube|\.netrc|\.pypirc|\.npmrc|Keychains|id_rsa|id_ed25519|/etc/shadow)(?=$|[\s/'\";|&)])"

DEFAULT_RULES: tuple[Rule, ...] = (
    _rule(Decision.DENY, SECRET_FILE, "reads a secret file (.env)"),
    _rule(Decision.DENY, SECRET_DIRECTORY, "touches credentials or keys"),
    _rule(Decision.DENY, r"\bsudo\b|\bsu\s+-?\w*\s*(?:$|;|&)", "asks for elevated privileges"),
    _rule(Decision.DENY, r"\brm\s+(?:-\w+\s+)*-\w*[rR]\w*\s+(?:-\w+\s+)*(?:/|~|\$HOME|\*)(?=\s|$)", "recursive delete of a root, home or wildcard path"),
    _rule(Decision.DENY, r"\b(?:curl|wget)\b[^|;&]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b", "pipes a download into a shell"),
    _rule(Decision.DENY, r"\bmkfs\b|\bdd\b[^|;&]*\bof=/dev/|:\(\)\s*\{\s*:\s*\|\s*:", "can damage the disk or exhaust the machine"),
    # Files that run by themselves later: a hook, a login script, a scheduled job. Writing one is how a prompt injection becomes code
    # execution outside the sandbox, so a person decides.
    _rule(Decision.ASK, r"\.(?:bashrc|zshrc|zprofile|bash_profile|profile)\b|\.git/hooks|\.husky|\.vscode/|sandbox\.json|\bcrontab\b|\blaunchctl\b|LaunchAgents", "creates or edits a file that runs by itself later"),
    _rule(Decision.ASK, r"\b(?:curl|wget|nc|ncat|ssh|scp|rsync|ftp|telnet)\b|\b(?:pip3?|npm|pnpm|yarn|brew|apt(?:-get)?)\s+(?:install|add|i)\b", "needs the network", needs_network=True),
)


class ExecutionPolicy:
    """Evaluates one command. The most restrictive matching rule wins; ties between asks keep the network flag."""

    def __init__(self, rules: tuple[Rule, ...] = DEFAULT_RULES, strict: bool = False) -> None:
        self._rules = rules
        self.strict = strict

    def evaluate(self, command: str) -> Verdict:
        matched = [rule for rule in self._rules if rule.pattern.search(command)]
        if matched:
            strongest = min(matched, key=lambda rule: _RANK[rule.decision])
            if strongest.decision is Decision.DENY:
                return Verdict(Decision.DENY, strongest.reason)
            asks = [rule for rule in matched if rule.decision is Decision.ASK]
            return Verdict(Decision.ASK, "; ".join(dict.fromkeys(rule.reason for rule in asks)), any(rule.needs_network for rule in asks))
        if self.strict:
            return Verdict(Decision.ASK, "strict mode asks before every command")
        return Verdict(Decision.ALLOW, "runs inside the sandbox")
