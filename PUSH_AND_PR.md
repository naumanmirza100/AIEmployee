# Push and PR guide

## 1. Remove extra files from staging (don’t commit these)

Discard local Celery state so it isn’t included in the PR:

```bash
git restore celerybeat-schedule.bak celerybeat-schedule.dat
```

Optional: if you **don’t** want to commit the deletion of the old .md docs, restore them:

```bash
git restore AGENT_ENHANCEMENTS_IMPLEMENTATION.md AGENT_IMPROVEMENTS.md AGENT_IMPROVEMENTS_IMPLEMENTATION_STATUS.md CHART_CAPABILITIES_SUMMARY.md CHART_IMPLEMENTATION_GUIDE.md IMPLEMENTATION_SUMMARY.md
```

If you **do** want to remove those docs from the repo, leave them as deleted and stage the deletions.

---

## 2. Stage and commit

Stage only the files you want in the PR (code + new commands; optional: doc deletions and new docs):

```bash
git add api/views/marketing_agent.py api/urls.py
git add marketing_agent/models.py marketing_agent/views.py marketing_agent/views_email_tracking.py
git add marketing_agent/services/email_service.py marketing_agent/services/reply_processor.py
git add marketing_agent/utils/reply_analyzer.py
git add marketing_agent/management/commands/analyze_skipped_replies.py
git add marketing_agent/management/commands/fix_reply_triggering_email.py
git add marketing_agent/management/commands/mark_reply_emails_opened.py
git add marketing_agent/management/commands/reanalyze_replies.py
git add marketing_agent/agents/document_authoring_agent.py marketing_agent/document_generator.py
git add marketing_agent/management/commands/send_sequence_emails.py
git add PaPerProjectFront/src/components/marketing/CampaignDetail.jsx
git add PaPerProjectFront/src/components/marketing/EmailSendingStatusPage.jsx
git add PaPerProjectFront/src/components/marketing/Documents.jsx
git add PaPerProjectFront/src/components/marketing/SequenceManagementPage.jsx
git add PaPerProjectFront/src/services/marketingAgentService.js
git add .gitignore
```

Optional (include if you want them in this PR):

```bash
git add docs/
git add CELERY_COMMANDS.md
git add -u
```

Then commit:

```bash
git commit -m "Marketing: conversion rate, open/click tracking, reply handling, sub-sequence switch"
```

---

## 3. Push

```bash
git push origin noorBranch
```

---

## 4. PR description (copy below into the PR)

Use the following in the “Description” of your pull request.

---

### Marketing: conversion rate, open/click tracking, reply handling & sub-sequence switch

#### Summary
- Conversion rate is now based on **positive replies** (interested, requested_info, etc.) instead of clicks.
- Open tracking: added **“View in browser”** link so opens are counted when the pixel is blocked (e.g. Gmail); reply also marks the email as opened.
- Reply handling: sub-sequence **switches** when the lead replies again with a different interest (e.g. Unsubscribe then Interested).
- Reply content on Email Sending Status: **HTML/tags stripped** so raw `<a href="...">` and long URLs don’t show in the UI.
- New management commands for reply/triggering-email fixes and backfills.

#### Changes

**Backend**
- **Conversion rate:** `api/views/marketing_agent.py`, `marketing_agent/views.py` – conversion count and progress use `positive_replies` instead of `total_clicked`.
- **Open tracking:** `marketing_agent/services/email_service.py` – inject “View in browser” link; `marketing_agent/views_email_tracking.py` – same URL returns HTML for browser, pixel for image requests.
- **Reply = opened:** `marketing_agent/models.py` – `post_save` on `Reply` sets `triggering_email.status = 'opened'` when a reply is created.
- **Sub-sequence switch on new interest:** `marketing_agent/services/reply_processor.py` – when a sub-sequence reply has a different interest (e.g. was Unsubscribe, now Interested), switch to the matching sub-sequence and pass it to `mark_replied`.
- **Open/click docs:** Comments in API view and `views_email_tracking.py` describing how open/click rate and tracking work.
- **Management commands:** `mark_reply_emails_opened` (backfill: mark replied emails as opened), existing `fix_reply_triggering_email`, `analyze_skipped_replies`, `reanalyze_replies`.

**Frontend**
- **CampaignDetail.jsx:** Conversions target shows `positive_replies` and uses backend `conversion_progress`.
- **EmailSendingStatusPage.jsx:** Reply content displayed via `stripHtmlForDisplay()` so tags/long URLs are not shown.

**Other**
- `.gitignore`: ignore `celerybeat-schedule.*` so local Celery state is not committed.

#### How to verify
- Set `SITE_URL` (e.g. ngrok) for tracking; send a campaign email; open and/or click “View in browser” and confirm open/click counts.
- Reply to a main-sequence email → correct sub-sequence starts; reply again to a sub-sequence email with different interest → sub-sequence switches and new path emails send.
- Run `python manage.py mark_reply_emails_opened` to backfill opens for existing replies.
