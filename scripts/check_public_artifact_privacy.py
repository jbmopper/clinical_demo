from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SAFE_PUBLIC_EXPORT_VALUES = {
    "export-safe",
    "export_safe",
    "sanitized",
    "synthetic",
}

HARD_BLOCK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("clinical note row", re.compile(r'"kind"\s*:\s*"note"', re.IGNORECASE)),
    ("note identifier", re.compile(r"\bnote_id\s*=", re.IGNORECASE)),
    (
        "MRN-like identifier",
        re.compile(r"\b(?:MRN|medical record number)\s*[:=#-]?\s*[A-Z0-9-]{5,}\b", re.IGNORECASE),
    ),
    ("SSN-like identifier", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("email address", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
    ("phone number", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")),
    (
        "MIMIC source id",
        re.compile(r"\b(?:subject_id|hadm_id|stay_id|icustay_id)\b", re.IGNORECASE),
    ),
)

CLASSIFICATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("patient identifier field", re.compile(r'"patient_id"\s*:', re.IGNORECASE)),
    (
        "exact patient date field",
        re.compile(
            r'"(?:birth_date|birthDate|date_of_birth|dob|deceased_date|document_date)"\s*:',
            re.IGNORECASE,
        ),
    ),
    (
        "patient evidence field",
        re.compile(r'"(?:patient_evidence|retrieved_rows|evidence_rows)"\s*:', re.IGNORECASE),
    ),
)


@dataclass(frozen=True)
class Finding:
    path: Path
    reason: str
    detail: str


def main() -> int:
    args = parse_args()
    paths = selected_paths(args)
    findings = scan_paths(paths)
    if findings:
        print("public-artifact-privacy-gate failed:", file=sys.stderr)
        for finding in findings:
            print(
                f"- {finding.path}: {finding.reason}: {finding.detail}",
                file=sys.stderr,
            )
        print(
            "\nAdd explicit artifact safety metadata for synthetic/sanitized eval outputs, "
            "and keep raw notes, note IDs, MIMIC IDs, MRNs, SSNs, phones, and emails out of git.",
            file=sys.stderr,
        )
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Block unsafe patient-originated data in public eval artifacts."
    )
    parser.add_argument("paths", nargs="*", help="Files to scan. Pre-commit passes these.")
    parser.add_argument(
        "--ref",
        help="Git diff range to scan, for example origin/main...HEAD.",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Scan staged files instead of positional paths.",
    )
    return parser.parse_args()


def selected_paths(args: argparse.Namespace) -> list[Path]:
    if args.ref:
        return git_changed_paths(args.ref)
    if args.staged:
        return git_changed_paths("--cached")
    return [Path(path) for path in args.paths]


def git_changed_paths(ref: str) -> list[Path]:
    if ref == "--cached":
        command = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRTUXB"]
    else:
        command = ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", ref]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return [Path(line) for line in result.stdout.splitlines() if line]


def scan_paths(paths: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted({normalize_path(path) for path in paths}):
        if not path.exists() or not path.is_file() or not is_public_artifact(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        findings.extend(scan_text(path, text))
    return findings


def scan_text(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for label, pattern in HARD_BLOCK_PATTERNS:
        match = pattern.search(text)
        if match:
            findings.append(
                Finding(path, "blocked patient data pattern", f"{label}: {sample(match)}")
            )

    marker = has_public_safety_marker(text)
    if not marker:
        findings.append(
            Finding(
                path,
                "missing artifact safety marker",
                "changed eval artifacts must declare synthetic/sanitized public-export safety",
            )
        )
        return findings

    for label, pattern in CLASSIFICATION_PATTERNS:
        match = pattern.search(text)
        if match and not marker:
            findings.append(Finding(path, "unclassified patient artifact content", label))
    return findings


def has_public_safety_marker(text: str) -> bool:
    json_marker = public_safety_from_json(text)
    if json_marker:
        return True
    header = "\n".join(text.splitlines()[:20])
    return bool(
        re.search(
            r"^Public-Artifact-Safety:\s*(?:export-safe|export_safe|sanitized|synthetic)\s*$",
            header,
            re.IGNORECASE | re.MULTILINE,
        )
    )


def public_safety_from_json(text: str) -> bool:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False
    return contains_safe_public_export_marker(data)


def contains_safe_public_export_marker(value: Any) -> bool:
    if isinstance(value, dict):
        for key in ("artifact_safety", "artifact_policy", "privacy", "metadata"):
            child = value.get(key)
            if isinstance(child, dict) and dict_contains_safe_marker(child):
                return True
        return dict_contains_safe_marker(value)
    return False


def dict_contains_safe_marker(value: dict[str, Any]) -> bool:
    public_export = value.get("public_export") or value.get("public_artifact")
    contains_real_patient_data = value.get("contains_real_patient_data")
    contains_patient_data = value.get("contains_patient_data")
    declared_safe = str(public_export).lower() in SAFE_PUBLIC_EXPORT_VALUES
    no_real_patient_data = contains_real_patient_data is False or contains_patient_data is False
    return declared_safe and no_real_patient_data


def is_public_artifact(path: Path) -> bool:
    parts = path.parts
    return "eval" in parts and path.suffix.lower() in {
        ".csv",
        ".json",
        ".jsonl",
        ".md",
        ".tsv",
        ".txt",
    }


def normalize_path(path: Path) -> Path:
    return Path(str(path).strip())


def sample(match: re.Match[str]) -> str:
    matched = match.group(0).replace("\n", "\\n")
    return matched[:80]


if __name__ == "__main__":
    raise SystemExit(main())
