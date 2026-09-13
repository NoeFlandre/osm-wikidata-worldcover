"""Dataset-level invariants.

These are the guarantees the published dataset claims, checked over the rows
themselves rather than over the code that produced them: a refactor that
quietly breaks blocking or dominance still fails here.

The result is a *report* rather than an exception so a run can show every
problem at once instead of one per attempt.
"""

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from osm_wikidata_worldcover.domain.dominance import DEFAULT_THRESHOLD
from osm_wikidata_worldcover.domain.nomenclature import CLASS_LABELS
from osm_wikidata_worldcover.domain.splits import Split
from osm_wikidata_worldcover.domain.text import DEFAULT_MIN_WORDS, dedup_key, is_usable

__all__ = ["Check", "ValidationReport", "Violation", "validate"]

_VALID_SPLITS = frozenset(s.value for s in Split)


class Check(Enum):
    """A named dataset guarantee."""

    EMPTY_DATASET = "empty_dataset"
    INVALID_SPLIT = "invalid_split"
    INVALID_LABEL = "invalid_label"
    BELOW_THRESHOLD = "below_threshold"
    UNUSABLE_TEXT = "unusable_text"
    DUPLICATE_EXAMPLE = "duplicate_example"
    POLYGON_LEAKAGE = "polygon_leakage"
    DOCUMENT_LEAKAGE = "document_leakage"


@dataclass(frozen=True, slots=True)
class Violation:
    """One failed guarantee, with a sample of the rows responsible."""

    check: Check
    count: int
    examples: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """The outcome of validating a dataset."""

    rows: int
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether every guarantee held."""
        return not self.violations


def validate(
    rows: Iterable[Mapping[str, Any]],
    threshold: float = DEFAULT_THRESHOLD,
    min_words: int = DEFAULT_MIN_WORDS,
) -> ValidationReport:
    """Check every published guarantee over ``rows`` and report all failures."""
    tally: Counter[Check] = Counter()
    examples: defaultdict[Check, list[str]] = defaultdict(list)
    splits_by_polygon: defaultdict[str, set[str]] = defaultdict(set)
    splits_by_document: defaultdict[str, set[str]] = defaultdict(set)
    seen_keys: set[str] = set()
    total = 0

    for r in rows:
        total += 1
        for check, culprit in _row_violations(r, threshold, min_words, seen_keys):
            _record(tally, examples, check, culprit)
        splits_by_polygon[str(r["polygon_id"])].add(str(r["split"]))
        splits_by_document[str(r["document_id"])].add(str(r["split"]))

    if total == 0:
        return ValidationReport(0, [Violation(Check.EMPTY_DATASET, 0)])

    _record_leakage(tally, examples, Check.POLYGON_LEAKAGE, splits_by_polygon)
    _record_leakage(tally, examples, Check.DOCUMENT_LEAKAGE, splits_by_document)

    # Ordered by the Check enum so two runs over the same data report identically.
    violations = [
        Violation(check, tally[check], tuple(sorted(examples[check])[:5]))
        for check in Check
        if tally[check]
    ]
    return ValidationReport(total, violations)


def _row_violations(
    r: Mapping[str, Any], threshold: float, min_words: int, seen_keys: set[str]
) -> Iterable[tuple[Check, str]]:
    """Yield the guarantees a single row breaks."""
    polygon_id = str(r["polygon_id"])
    code = int(r["worldcover_code"])

    if str(r["split"]) not in _VALID_SPLITS:
        yield Check.INVALID_SPLIT, polygon_id
    if CLASS_LABELS.get(code) != r["worldcover_label"]:
        yield Check.INVALID_LABEL, polygon_id
    if float(r["dominant_fraction"]) < threshold:
        yield Check.BELOW_THRESHOLD, polygon_id

    text = str(r["text"])
    if not is_usable(text, min_words):
        yield Check.UNUSABLE_TEXT, polygon_id

    key = dedup_key(text, str(code))
    if key in seen_keys:
        yield Check.DUPLICATE_EXAMPLE, polygon_id
    seen_keys.add(key)


def _record(
    tally: Counter[Check],
    examples: defaultdict[Check, list[str]],
    check: Check,
    culprit: str,
) -> None:
    tally[check] += 1
    if len(examples[check]) < 5:
        examples[check].append(culprit)


def _record_leakage(
    tally: Counter[Check],
    examples: defaultdict[Check, list[str]],
    check: Check,
    splits_by_key: Mapping[str, set[str]],
) -> None:
    """Record every key that appears under more than one split."""
    for key, splits in splits_by_key.items():
        if len(splits) > 1:
            _record(tally, examples, check, key)
