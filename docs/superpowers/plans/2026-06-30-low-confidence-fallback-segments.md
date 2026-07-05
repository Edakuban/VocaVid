# Low Confidence Fallback Segments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent low-confidence fallback lyrics from automatically replacing instrumental render gaps.

**Architecture:** Keep alignment data visible on lyric rows, but make render segment construction skip unreliable fallback rows. Segment generation continues to derive instrumental gaps from time ranges not covered by trusted lyric rows.

**Tech Stack:** Python, unittest, existing `musicvideogen.segments` and pipeline tests.

---

### Task 1: Segment Builder Trust Filter

**Files:**
- Modify: `tests/test_segments.py`
- Modify: `musicvideogen/segments.py`

- [ ] **Step 1: Write the failing test**

Add a test where matched chorus lines are followed by a long instrumental gap and then low-confidence fallback lines. Expected result: the matched chorus remains lyrics, while the low-confidence fallback range is rendered as instrumental gap segments.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_segments.SegmentBuilderTests.test_low_confidence_fallback_lines_do_not_displace_instrumental_gaps`

Expected: FAIL because current `build_render_segments()` treats all timed rows as lyrics.

- [ ] **Step 3: Write minimal implementation**

Filter out rows with `confidence < 0.45` before grouping render lyrics. Keep existing grouping, gap chunking, intro/outro/break labeling, and pipeline storage behavior intact.

- [ ] **Step 4: Run focused and full tests**

Run: `python -m unittest tests.test_segments tests.test_pipeline_segments tests.test_app_endpoints`

Run: `python -m unittest discover -s tests`

Expected: all tests pass.
