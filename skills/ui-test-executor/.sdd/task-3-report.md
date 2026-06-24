# Task 3 Report: `_parse_assertion_from_longrepr`

## What I Implemented

Appended `_parse_assertion_from_longrepr(report) -> dict` to
`/Users/zhoujinjian/.claude/skills/ui-test-executor/assets/conftest_template.py`
(immediately after `_extract_rule_from_docstring`, now the last function in the file).

The function extracts four fields from a pytest `report.longrepr`:

| key             | source                                                    |
|-----------------|-----------------------------------------------------------|
| `statement`     | `reprtraceback.reprentries[-1].reprfileloc.source_line`   |
| `file`          | `reprfileloc.path` + `reprfileloc.lineno` (joined `:`)    |
| `introspection` | `reprcrash.message` (full pytest-native assert detail)    |
| `message`       | `reprcrash.message` if present, else last `E `-prefixed line of `longreprtext`, else last line of `longreprtext` |

Behavior branches:
- `longrepr is None` → all 4 fields empty.
- `longrepr` is a `str` (setup-phase failure) → `message = longrepr`, other fields empty.
- `reprcrash` / `reprtraceback` missing or partial → `getattr(..., None)` chains short-circuit cleanly, all 4 keys always present.

Only `getattr` is used for attribute access (no try/except), per the defensive-access guideline in the brief's Special Note.

## TDD Evidence

### RED (before impl)

```
$ python3 -m pytest evals/failure_analysis/test_parse_assertion.py -v
...
FAILED evals/failure_analysis/test_parse_assertion.py::test_native_assert_extraction
FAILED evals/failure_analysis/test_parse_assertion.py::test_longrepr_is_string
FAILED evals/failure_analysis/test_parse_assertion.py::test_longrepr_without_reprcrash
FAILED evals/failure_analysis/test_parse_assertion.py::test_empty_longrepr
============================== 4 failed in 0.13s ===============================
```

Failure mode for all 4: `AttributeError: module '_conftest_under_test' has no attribute '_parse_assertion_from_longrepr'` — exactly the expected RED signal.

### GREEN (after impl)

```
$ python3 -m pytest evals/failure_analysis/test_parse_assertion.py -v
...
evals/failure_analysis/test_parse_assertion.py::test_native_assert_extraction PASSED [ 25%]
evals/failure_analysis/test_parse_assertion.py::test_longrepr_is_string         PASSED [ 50%]
evals/failure_analysis/test_parse_assertion.py::test_longrepr_without_reprcrash PASSED [ 75%]
evals/failure_analysis/test_parse_assertion.py::test_empty_longrepr            PASSED [100%]
============================== 4 passed in 0.10s ===============================
```

### Regression check (full failure_analysis suite)

```
$ python3 -m pytest evals/failure_analysis/ -v
...
============================== 15 passed in 0.10s ==============================
```

Tasks 1 (`_sanitize_nodeid_to_slug`) and 2 (`_extract_rule_from_docstring`) still pass — 11/11 prior tests + 4 new = 15/15.

## Files Changed

| file                                                                    | change                              |
|-------------------------------------------------------------------------|-------------------------------------|
| `evals/failure_analysis/fixtures/longrepr_native_assert.txt`            | created (verbatim from brief)       |
| `evals/failure_analysis/test_parse_assertion.py`                        | created (4 tests; helper `_build_fake_longrepr` patched — see Deviations) |
| `assets/conftest_template.py`                                           | appended `_parse_assertion_from_longrepr` (lines 386-451) |

Step 6 (git) skipped — not a git repo.

## Self-Review Findings

- [x] Function placed at end of `conftest_template.py` (after `_extract_rule_from_docstring`).
- [x] Handles all 4 cases: native assert (`reprcrash`/`reprtraceback` present), string longrepr, missing reprcrash, None longrepr.
- [x] Uses only `getattr(..., default)` chains — no try/except around attribute access.
- [x] All 4 dict keys (`statement`, `file`, `introspection`, `message`) always present in every return path (initialized upfront, never deleted).
- [x] No other functions in `conftest_template.py` modified.
- [x] Commit skipped.

## Deviations

**1. `_build_fake_longrepr` helper patched to populate `path`/`lineno`.**

The brief's test asserts `result["file"] == "tests/product/test_search.py:55"`, but the brief's `_build_fake_longrepr` helper had a dead `file_loc` parameter — it was passed in but never wired to any attribute on `reprfileloc`. With the brief's impl as written, `getattr(reprfileloc, "path", "")` returns `""`, so `result["file"]` would be `""` and the assertion would fail.

Per the brief's instruction "trust the tests and adapt", I patched the helper to split `file_loc` into `path` + `lineno` and attach them to the `reprfileloc` SimpleNamespace — this mirrors pytest's real `_pytest._code.code.ReprFileLocation` interface (`path`, `lineno`, `message`, `source_line`). The 4 test assertions themselves are unchanged. The production function (`_parse_assertion_from_longrepr`) is unaffected and works against real pytest `ReprExceptionInfo` objects.

**2. Message field prefers `reprcrash.message` over `longreprtext` parsing.**

The brief's impl as transcribed only set `result["message"]` from `reprcrash.message` when the `longreprtext`-derived value was empty. In `test_native_assert_extraction`, `longreprtext="..."` (non-empty placeholder), which would have blocked the richer `AssertionError: ...` message from `reprcrash.message`, causing `assert "AssertionError" in result["message"]` to fail.

I reordered the logic: `reprcrash.message` is the primary source for `message` (it carries the exception class), with `longreprtext` `E `-line parsing as fallback. This matches the docstring contract ("message: 错误消息（ExceptionClass: msg）") and is robust against tests that pass placeholder `longreprtext` values.

## Concerns

- The `_build_fake_longrepr` helper patch is in the test file, not the production code. Reviewers should confirm this matches intent: the brief's test was self-inconsistent (assertion demanded data the helper didn't provide), and the minimal fix was to complete the helper. No test assertion was relaxed.
- The `file` field uses Python's `rpartition(":")` to split `file_loc`; this assumes real-world paths don't contain a colon in the directory portion (true on Linux/macOS/Windows local paths, but would mis-parse a Windows `C:\...` path). Acceptable for the current shop-lab-ui-test scope but worth noting if the skill ever runs on Windows.
- `reprcrash.message` is used for both `introspection` and `message`. In real pytest, `reprcrash.message` typically contains both the `ExceptionClass: msg` line and the `assert ...` introspection line — so both fields legitimately overlap. If a future caller wants them strictly separated, the function may need to split on the first newline; left as-is for now since the test accepts the overlap.
