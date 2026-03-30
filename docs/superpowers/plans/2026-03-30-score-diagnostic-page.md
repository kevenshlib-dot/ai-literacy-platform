# Score Diagnostic Page Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route both score-list entry and post-submit completion into one dedicated diagnostic report page so the report shell, chart lifecycle, and actions stay consistent.

**Architecture:** Keep `DiagnosticReportView.vue` as the shared report-body component, add a dedicated `ScoreDiagnostic.vue` page as the single report shell, and update `Scores.vue` and `TakeExam.vue` to navigate to that route instead of rendering reports inline.

**Tech Stack:** Vue 3 Composition API, Vue Router, Ant Design Vue, ECharts, html2canvas, jsPDF

---

## Chunk 1: Routing And Dedicated Page

### Task 1: Add a dedicated score diagnostic route and page shell

**Files:**
- Create: `frontend/src/views/ScoreDiagnostic.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/components/DiagnosticReportView.vue`

- [ ] Step 1: Add the `ScoreDiagnostic` route under the authenticated layout
- [ ] Step 2: Create `ScoreDiagnostic.vue` with loading, success, and error states
- [ ] Step 3: Fetch `/scores/{scoreId}/diagnostic` from the new page
- [ ] Step 4: Reuse `DiagnosticReportView.vue` for the report body
- [ ] Step 5: Add shared page-level actions for returning to scores, downloading report, and downloading certificate

## Chunk 2: Update Existing Entry Points

### Task 2: Replace inline diagnostic rendering in scores management

**Files:**
- Modify: `frontend/src/views/Scores.vue`

- [ ] Step 1: Remove the inline diagnostic-report branch from `Scores.vue`
- [ ] Step 2: Replace both score-list “诊断报告” click handlers with router navigation
- [ ] Step 3: Pass optional `displayName` in query when navigating from manager records
- [ ] Step 4: Delete now-unused diagnostic page state and helpers from `Scores.vue`

### Task 3: Replace inline diagnostic rendering in take-exam completion flow

**Files:**
- Modify: `frontend/src/views/TakeExam.vue`

- [ ] Step 1: Remove the `diagnostic_ready` render branch and related report state
- [ ] Step 2: Keep the processing and failure states
- [ ] Step 3: When `/scores/process/{answer_sheet_id}` returns `completed`, `router.replace` to `ScoreDiagnostic`
- [ ] Step 4: Preserve retry and fallback behavior for failed processing

## Chunk 3: Verification

### Task 4: Verify unified entry behavior

**Files:**
- Verify: `frontend/src/views/ScoreDiagnostic.vue`
- Verify: `frontend/src/views/Scores.vue`
- Verify: `frontend/src/views/TakeExam.vue`

- [ ] Step 1: Run `cd frontend && npm run build`
- [ ] Step 2: Run `git diff --check -- frontend/src/router/index.ts frontend/src/views/ScoreDiagnostic.vue frontend/src/views/Scores.vue frontend/src/views/TakeExam.vue frontend/src/components/DiagnosticReportView.vue`
- [ ] Step 3: Confirm both entry points now land on the same route and page shell
