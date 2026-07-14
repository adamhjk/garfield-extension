from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .adapters.base import AdapterConfig
from .blind import prepare_blind_review
from .grading import grade_fixture
from .models import Case
from .report import write_reports
from .runner import BenchmarkRunner, CalibrationRequired
from .telemetry import calibrate_events, run_live_calibration
from .workspace import materialize_workspace


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except CalibrationRequired as error:
        print(f"blocked: {error}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="garfield-bench")
    subparsers = parser.add_subparsers(required=True)

    calibrate = subparsers.add_parser("calibrate", help="prove complete parent/child token accounting")
    calibrate.add_argument("--events", type=Path)
    calibrate.add_argument("--runtime-tree-total", type=int)
    calibrate.add_argument("--codex", default="codex")
    calibrate.add_argument("--model")
    calibrate.add_argument("--output", type=Path, required=True)
    calibrate.set_defaults(handler=_calibrate)

    verify = subparsers.add_parser("verify-fixtures", help="check candidate patches and hidden oracles")
    verify.add_argument("--base", type=Path, required=True)
    verify.add_argument("--cases", type=Path, default=_default_cases())
    verify.set_defaults(handler=_verify_fixtures)

    for name, repetitions in (("pilot", 1), ("full", 5)):
        command = subparsers.add_parser(name, help=f"run {repetitions} paired repetition(s)")
        _add_run_arguments(command)
        command.set_defaults(handler=_run_schedule, default_repetitions=repetitions)

    pair = subparsers.add_parser("run-pair", help="run one paired case repetition")
    _add_run_arguments(pair)
    pair.add_argument("--case", required=True)
    pair.add_argument("--repetition", type=int, default=1)
    pair.set_defaults(handler=_run_pair)

    one = subparsers.add_parser("run-one", help="run one treatment for a case repetition")
    _add_run_arguments(one)
    one.add_argument("--case", required=True)
    one.add_argument("--repetition", type=int, default=1)
    one.add_argument(
        "--treatment",
        choices=("garfield", "swamp-garfield", "workflow-garfield"),
        required=True,
    )
    one.set_defaults(handler=_run_one)

    report = subparsers.add_parser("report", help="aggregate completed run directories")
    report.add_argument("--runs", type=Path, default=Path("runs"))
    report.add_argument("--output", type=Path, default=Path("report"))
    report.add_argument("--factory-authoring-tokens", type=int)
    report.set_defaults(handler=_report)

    blind = subparsers.add_parser("prepare-blind", help="anonymize paired final patches for qualitative review")
    blind.add_argument("--runs", type=Path, default=Path("runs"))
    blind.add_argument("--output", type=Path, default=Path("blind-review"))
    blind.add_argument("--seed", type=int, default=20260713)
    blind.set_defaults(handler=_prepare_blind)
    return parser


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument(
        "--extension-repo",
        type=Path,
        default=_default_extension_repo(),
        help="Garfield extension checkout (defaults to the parent of benchmarking/)",
    )
    parser.add_argument(
        "--agents-repo",
        type=Path,
        help="dcramer/agents checkout; required only for garfield and swamp-garfield",
    )
    parser.add_argument("--cases", type=Path, default=_default_cases())
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--model")
    parser.add_argument("--effort", default="high")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--seed", type=int, default=20260713)
    parser.add_argument("--repetitions", type=int)


def _calibrate(args: argparse.Namespace) -> int:
    stream = ""
    if args.events:
        stream = args.events.read_text()
        result = calibrate_events(stream.splitlines(), runtime_tree_total=args.runtime_tree_total)
    else:
        result, stream = run_live_calibration(args.codex, args.model)
        if args.runtime_tree_total is not None and not result.passed:
            result = calibrate_events(stream.splitlines(), runtime_tree_total=args.runtime_tree_total)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n")
    args.output.with_suffix(".events.jsonl").write_text(stream)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.passed else 2


def _verify_fixtures(args: argparse.Namespace) -> int:
    failures = 0
    for case in _load_cases(args.cases):
        temp = Path(tempfile.mkdtemp(prefix=f"verify-{case.case_id}-"))
        try:
            workspace = temp / "workspace"
            materialize_workspace(args.base.resolve(), case.fixture_patch, workspace)
            grade = grade_fixture(case, workspace, temp / "grade")
            public_expected = bool(case.oracle.get("candidate_public_expected_pass"))
            solution = case.root / "solution.patch"
            solved = {"public_passed": False, "hidden_passed": False}
            if solution.exists():
                applied = subprocess.run(
                    ["git", "apply", str(solution.resolve())],
                    cwd=workspace,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if applied.returncode == 0:
                    solved = grade_fixture(case, workspace, temp / "solution-grade")
            candidate_output = "\n".join(
                str(result["stdout"]) + "\n" + str(result["stderr"])
                for result in [*grade["public"], grade["hidden"]]
            )
            markers_present = all(
                marker in candidate_output for marker in case.oracle.get("candidate_failure_markers", [])
            )
            exit_codes = [int(result["exit_code"]) for result in grade["public"]]
            passed = (
                grade["public_passed"] == public_expected
                and not grade["hidden_passed"]
                and exit_codes == case.oracle.get("candidate_public_exit_codes")
                and markers_present
                and solved["public_passed"]
                and solved["hidden_passed"]
            )
            print(
                f"{case.case_id}: {'ok' if passed else 'FAILED'} "
                f"(candidate public={grade['public_passed']}, expected={public_expected}, "
                f"candidate hidden={grade['hidden_passed']}, solution public={solved['public_passed']}, "
                f"solution hidden={solved['hidden_passed']}, intended failures={markers_present})"
            )
            failures += int(not passed)
        finally:
            shutil.rmtree(temp, ignore_errors=True)
    return 1 if failures else 0


def _run_pair(args: argparse.Namespace) -> int:
    case = next((item for item in _load_cases(args.cases) if item.case_id == args.case), None)
    if case is None:
        raise SystemExit(f"unknown case: {args.case}")
    runner = _runner(args)
    results = runner.run_pair(case, args.repetition)
    print(json.dumps([result.to_dict() for result in results], indent=2, sort_keys=True))
    return 0 if all(result.status == "passed" for result in results) else 1


def _run_one(args: argparse.Namespace) -> int:
    case = next((item for item in _load_cases(args.cases) if item.case_id == args.case), None)
    if case is None:
        raise SystemExit(f"unknown case: {args.case}")
    result = _runner(args).run_treatment(case, args.repetition, args.treatment)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "passed" else 1


def _run_schedule(args: argparse.Namespace) -> int:
    repetitions = args.repetitions if args.repetitions is not None else args.default_repetitions
    results = _runner(args).run_schedule(_load_cases(args.cases), repetitions)
    print(json.dumps([result.to_dict() for result in results], indent=2, sort_keys=True))
    return 0 if all(result.status == "passed" for result in results) else 1


def _runner(args: argparse.Namespace) -> BenchmarkRunner:
    return BenchmarkRunner(
        base=args.base,
        agents_repo=args.agents_repo,
        extension_repo=args.extension_repo,
        runs_root=args.runs,
        calibration=args.calibration,
        adapter_config=AdapterConfig(args.codex, args.model, args.effort, args.timeout),
        seed=args.seed,
    )


def _report(args: argparse.Namespace) -> int:
    report = write_reports(args.runs, args.output, args.factory_authoring_tokens)
    print(json.dumps({"run_count": report["run_count"], "output": str(args.output)}, indent=2))
    return 0


def _prepare_blind(args: argparse.Namespace) -> int:
    result = prepare_blind_review(args.runs, args.output, args.seed)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _load_cases(root: Path) -> list[Case]:
    return [Case.load(path) for path in sorted(root.iterdir()) if (path / "oracle.json").exists()]


def _default_cases() -> Path:
    return Path(__file__).resolve().parents[2] / "cases"


def _default_extension_repo() -> Path:
    return Path(__file__).resolve().parents[3]


if __name__ == "__main__":
    raise SystemExit(main())
