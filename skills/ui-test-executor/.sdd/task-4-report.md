# Task 4 Report: `_parse_playwright_error`

## What was implemented

Appended to `assets/conftest_template.py` (after `_parse_assertion_from_longrepr`, line 454):

- `import re as _re_pw` (module-level, scoped alias to avoid collision with any existing `re` usage)
- 4 module-level regex constants:
  - `_PW_PATTERNS` — dict with keys `locator` / `expected` / `received` / `action`
  - `_PW_TIMEOUT_RE` — `Timeout\s+(\d+)\s*ms` (IGNORECASE)
  - `_PW_PROTOCOL_NAV_RE` — `Protocol error.*navigate` (IGNORECASE)
  - `_PW_COUNT_ZERO_RE` — `count\s*[=><!]+\s*0\b|count\s+is\s+0\b|结果数[^\n]*0\b` (IGNORECASE)
- `_parse_playwright_error(text)` — returns 6-key dict (`locator`/`expected`/`received`/`action`/`hint`/`raw`); early-returns empty dict on empty input
- `_infer_hint(text, parsed)` — 5 priority rules producing hints ending with `（推断，仅作参考）`

Also created:
- `evals/failure_analysis/fixtures/playwright_expect_visible.txt`
- `evals/failure_analysis/fixtures/playwright_text_mismatch.txt`
- `evals/failure_analysis/test_parse_playwright_error.py` (6 tests, verbatim from brief)

## TDD Evidence

### RED (before impl)

```
python3 -m pytest evals/failure_analysis/test_parse_playwright_error.py -v
→ 6 failed
→ AttributeError: module '_conftest_under_test' has no attribute '_parse_playwright_error'
```

### GREEN (after impl)

```
python3 -m pytest evals/failure_analysis/test_parse_playwright_error.py -v
→ 6 passed in 0.09s
```

### Regression

```
python3 -m pytest evals/failure_analysis/ -v
→ 21 passed in 0.13s  (6 new + 15 prior)
```

## Files Changed

- `assets/conftest_template.py` (+119 lines appended; no existing lines modified)
- `evals/failure_analysis/fixtures/playwright_expect_visible.txt` (new)
- `evals/failure_analysis/fixtures/playwright_text_mismatch.txt` (new)
- `evals/failure_analysis/test_parse_playwright_error.py` (new)

## Self-Review Findings

- All 4 regex constants are module-level — PASS
- `_PW_PATTERNS` has exactly 4 keys (locator/expected/received/action) — PASS
- `_parse_playwright_error` returns dict with all 6 keys always present — PASS
- `_infer_hint` priority order: Protocol > Timeout+Locator > Expected≠Received > count=0+locator > count=0 fallback — PASS
- All 5 hint strings end with `（推断，仅作参考）` — PASS
- Empty input → all 6 fields empty (early `if not text: return result`) — PASS
- Only appended code; no prior function modified — PASS

## Deviations from Brief

Two deviations from the brief's impl code, both required to satisfy the brief's tests (which are source of truth per task instructions):

### Deviation 1: `_PW_COUNT_ZERO_RE` extended to match Chinese `结果数...0`

**Brief regex:** `count\s*[=><!]+\s*0\b|count\s+is\s+0\b`
**Adopted regex:** `count\s*[=><!]+\s*0\b|count\s+is\s+0\b|结果数[^\n]*0\b`

**Justification:** `test_no_playwright_structure_falls_back_to_raw` uses input
`"AssertionError: 搜索 '小米' 应返回商品，但结果数为 0\nassert 0 > 0"` and asserts `result["hint"]`
is non-empty. The brief's regex requires the literal English token `count`, which does not appear
in this input — so the brief's impl would return empty hint, failing the test. The test's inline
comment ("断言含 count = 0") suggests the author intended the count-zero rule to fire. Extending
the regex to also match the Chinese pattern `结果数...0` honors that intent.

### Deviation 2: `_infer_hint` rule 3 condition relaxed

**Brief condition:** `parsed["expected"] and parsed["received"] and parsed["expected"] != parsed["received"]`
**Adopted condition:** `parsed["expected"] and parsed["expected"] != parsed["received"]`

**Justification:** `test_text_mismatch` uses a fixture where `Received value: ""`. The received
regex `Received(?: value)?:\s*"?([^"\n]+)"?` cannot capture an empty string (the character class
`[^"\n]+` requires at least one non-quote char), so `parsed["received"]` is `""`. Under the brief's
condition, rule 3 would NOT fire (received is falsy) and hint would be empty — but the test asserts
`"文案变更" in result["hint"]`. The playwright failure mode "expected text X, received empty string"
is precisely a text-mismatch scenario, so dropping the truthiness check on received is both
semantically correct and required by the test. The inequality check `expected != received` still
guards against the trivial equal case.

## Concerns

- **`_re_pw` alias**: brief writes `import re as _re_pw` mid-file (after `_parse_assertion_from_longrepr`).
  PEP 8 recommends imports at top of file, but keeping it adjacent to the regex constants that use it
  preserves locality with the appended block and avoids touching the import block at the top of the
  file (minimizing diff against Tasks 1–3). Functionally equivalent.
- **`received` regex cannot capture empty received values** — empty `Received value: ""` yields
  `parsed["received"] = ""`. This is compensated by Deviation 2, but if a future caller relies on
  distinguishing "no Received line" vs "Received line with empty value", the current impl conflates
  them. Out of scope for Task 4; flagging for future revision if needed.
