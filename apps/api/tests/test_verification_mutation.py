"""AST mutation and the V3 self-test gates."""

from __future__ import annotations

from pathlib import Path

from verification.mutation import count_sites, gate, mutate, pick_sites

SOURCE = "def clamp(value, low, high):\n    if value < low:\n        return low\n    if value > high:\n        return high\n    return value\n"
STRONG = (
    "import unittest\nfrom clamp import clamp\n\n\nclass T(unittest.TestCase):\n"
    "    def test_low(self): self.assertEqual(clamp(-1, 0, 5), 0)\n"
    "    def test_high(self): self.assertEqual(clamp(9, 0, 5), 5)\n"
    "    def test_mid(self): self.assertEqual(clamp(3, 0, 5), 3)\n"
    "    def test_edges(self): self.assertEqual((clamp(0, 0, 5), clamp(5, 0, 5)), (0, 5))\n"
)
WEAK = "import unittest\nfrom clamp import clamp\n\n\nclass T(unittest.TestCase):\n    def test_runs(self): self.assertTrue(callable(clamp))\n"


def test_mutations_are_deterministic_and_change_the_source() -> None:
    total = count_sites(SOURCE)
    assert total >= 5
    assert {mutate(SOURCE, site) for site in range(total)} - {mutate(SOURCE, -1)}
    assert mutate(SOURCE, 0) == mutate(SOURCE, 0)
    assert all(compile(mutate(SOURCE, site), "m", "exec") for site in range(total))


def test_pick_sites_spreads_evenly_within_limit() -> None:
    assert pick_sites(3, 12) == [0, 1, 2]
    picked = pick_sites(100, 10)
    assert len(picked) == 10 and picked[0] == 0 and picked[-1] < 100


def build(tmp_path: Path, tests: str) -> dict[str, object]:
    (tmp_path / "clamp.py").write_text(SOURCE)
    (tmp_path / "test_clamp.py").write_text(tests)
    return gate(str(tmp_path), ["clamp.py"], ["test_clamp.py"], baseline={})


def test_strong_tests_discriminate_and_kill_most_mutants(tmp_path: Path) -> None:
    result = build(tmp_path, STRONG)
    assert result["passed"] and result["discriminates"]
    assert int(result["mutants"]) >= 5 and int(result["killed"]) / int(result["mutants"]) >= 0.6  # type: ignore[call-overload]  # `<`->`<=` in clamp is an equivalent mutant


def test_weak_tests_are_exposed_by_mutation(tmp_path: Path) -> None:
    result = build(tmp_path, WEAK)
    assert result["passed"] and result["discriminates"]
    assert result["killed"] == 0


def test_failing_tests_skip_the_expensive_gates(tmp_path: Path) -> None:
    (tmp_path / "clamp.py").write_text("def clamp(v, lo, hi):\n    return v\n")
    (tmp_path / "test_clamp.py").write_text(STRONG)
    result = gate(str(tmp_path), ["clamp.py"], ["test_clamp.py"], baseline={})
    assert not result["passed"] and result["mutants"] == 0


def run_self_test_probe(workdir: Path, files: dict[str, str], staged: dict[str, bytes]):  # type: ignore[no-untyped-def]
    import subprocess
    import sys

    from verification import build_self_test_probe, parse_self_test_output

    for name, content in files.items():
        (workdir / name).write_text(content)
    source, nonce = build_self_test_probe(staged)
    done = subprocess.run([sys.executable, "-c", source], cwd=workdir, capture_output=True, text=True, timeout=120, check=False)
    return parse_self_test_output(done.stdout, nonce)


def test_self_test_probe_verifies_strong_tests_that_fail_on_the_starter(tmp_path: Path) -> None:
    from verification import Status, decide

    stub = b"def clamp(value, low, high):\n    raise NotImplementedError\n"
    evidence = run_self_test_probe(tmp_path, {"clamp.py": SOURCE, "test_clamp.py": STRONG}, {"clamp.py": stub})
    assert evidence is not None
    report = decide(evidence, execution_ok=True)
    assert report.status is Status.VERIFIED and report.level.value == "v3_self_tests"


def test_self_test_probe_rejects_tests_that_prove_nothing(tmp_path: Path) -> None:
    from verification import Status, decide

    evidence = run_self_test_probe(tmp_path, {"clamp.py": SOURCE, "test_clamp.py": WEAK}, {"clamp.py": b"def clamp(v, lo, hi):\n    return v\n"})
    assert evidence is not None
    assert decide(evidence, execution_ok=True).status is Status.UNVERIFIED


def test_self_test_probe_without_test_files_is_unverified(tmp_path: Path) -> None:
    from verification import Status, decide

    evidence = run_self_test_probe(tmp_path, {"clamp.py": SOURCE}, {})
    assert evidence is not None and evidence.ran == 0
    assert decide(evidence, execution_ok=True).status is Status.UNVERIFIED


HTML = '<!doctype html><html><head><title>Alba Agent</title><meta name="viewport" content="width=device-width"><style>body{background:black;color:white}</style></head><body><h1>Alba Agent</h1><canvas id="scene"></canvas><script type="module">import * as THREE from "https://cdn.example/three.js";const scene=new THREE.Scene();</script></body></html>'
HTML_TESTS = '''import unittest
from pathlib import Path
class WebRequirements(unittest.TestCase):
    def page(self): return Path("artifacts/index.html").read_text()
    def test_brand_title(self): self.assertIn("<title>Alba Agent</title>",self.page())
    def test_responsive_viewport(self): self.assertIn('name="viewport"',self.page())
    def test_visible_scene(self): self.assertIn('<canvas id="scene">',self.page())
    def test_three_module(self): self.assertIn('import * as THREE',self.page())
    def test_black_white_style(self): self.assertIn('background:black;color:white',self.page())
'''


def test_html_artifacts_pass_the_same_discrimination_and_mutation_gates(tmp_path: Path) -> None:
    from verification import Status, decide
    (tmp_path / "artifacts").mkdir()
    evidence=run_self_test_probe(tmp_path,{"artifacts/index.html":HTML,"test_page.py":HTML_TESTS},{})
    assert evidence is not None and evidence.ran==5 and evidence.mutants>=3 and evidence.killed==evidence.mutants
    assert decide(evidence,execution_ok=True).status is Status.VERIFIED


def test_html_tests_that_only_check_file_existence_do_not_prove_web_behaviour(tmp_path: Path) -> None:
    from verification import Status, decide
    (tmp_path / "artifacts").mkdir()
    weak='import unittest\nfrom pathlib import Path\nclass T(unittest.TestCase):\n'+''.join(f'    def test_{i}(self): self.assertTrue(Path("artifacts/index.html").exists())\n' for i in range(5))
    evidence=run_self_test_probe(tmp_path,{"artifacts/index.html":HTML,"test_page.py":weak},{})
    assert evidence is not None and evidence.mutants>=3 and evidence.killed==0
    assert decide(evidence,execution_ok=True).status is Status.UNVERIFIED


def test_unchanged_html_input_does_not_falsely_count_as_new_verified_work(tmp_path: Path) -> None:
    from verification import Status, decide
    (tmp_path / "artifacts").mkdir()
    evidence=run_self_test_probe(tmp_path,{"artifacts/index.html":HTML,"test_page.py":HTML_TESTS},{"artifacts/index.html":HTML.encode()})
    assert evidence is not None and not evidence.discriminates
    assert decide(evidence,execution_ok=True).status is Status.UNVERIFIED


def test_mutation_isolation_restores_other_source_files_before_testing(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text('import b\ndef value():\n    return 1\n')
    (tmp_path / "b.py").write_text('def other():\n    return 2\n')
    (tmp_path / "test_weak.py").write_text('import unittest\nimport a\nclass T(unittest.TestCase):\n    def test_import(self): self.assertTrue(callable(a.value))\n')
    result=gate(str(tmp_path),["a.py","b.py"],["test_weak.py"],{})
    assert result["passed"] and result["discriminates"] and result["killed"]==0
