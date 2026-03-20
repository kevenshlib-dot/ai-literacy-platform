# Question Bank Timeout Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Increase the "new question bank" generation timeout from 5 minutes to 10 minutes across the full request path.

**Architecture:** Keep the existing synchronous generation flow and raise the timeout ceiling consistently in the frontend request override, backend LLM client, and nginx proxy layer so the same request is not cut off by a lower limit elsewhere.

**Tech Stack:** Vue 3, Axios, FastAPI, OpenAI Python client, Nginx

---

### Task 1: Update timeout values

**Files:**
- Modify: `frontend/src/views/Questions.vue`
- Modify: `app/agents/question_agent.py`
- Modify: `nginx.conf`
- Modify: `frontend/nginx.conf`
- Modify: `DEPLOY.md`

- [x] **Step 1: Raise frontend request timeout**

Change the explicit `request.post(..., { timeout: 300000 })` values used by the "new question bank" flow to `600000`.

- [x] **Step 2: Raise backend LLM timeout**

Change `Timeout(300.0, connect=10.0)` to `Timeout(600.0, connect=10.0)` in the question generation client.

- [x] **Step 3: Raise proxy read timeout**

Change `proxy_read_timeout 300s;` to `proxy_read_timeout 600s;` in both nginx config files and mirror the same value in deployment docs.

- [x] **Step 4: Verify exact values**

Run: `rg -n "600000|600s|Timeout\\(600\\.0" frontend app nginx.conf frontend/nginx.conf DEPLOY.md`
Expected: only the updated timeout locations appear with 10-minute values.
