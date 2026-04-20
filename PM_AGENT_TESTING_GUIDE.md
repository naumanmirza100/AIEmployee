# Project Manager Agent — Testing Guide

This guide helps you test every feature of the Project Manager Agent system. Follow each section step by step. Each test takes 1-2 minutes.

---

## Setup Before Testing

1. Make sure the Django server is running: `python manage.py runserver`
2. Make sure the frontend is running: `cd PaPerProjectFront && npm run dev`
3. Log in as a **Company User** at `http://localhost:3000/company/login`
4. Navigate to the **Project Manager Dashboard**
5. Make sure you have at least **1 project** and **2 project users** created

---

## 1. Project Pilot Agent

**Tab:** Project Pilot

| # | What to do | What should happen |
|---|-----------|-------------------|
| 1 | Type: "Create a project called Test App with high priority" | Project gets created. You see a confirmation with project name. |
| 2 | Type: "Create a task called Fix Login Bug for Test App, assign to developer1" | Task gets created under Test App project. |
| 3 | Type: "Mark all tasks in Test App as in progress" | All tasks get updated to in_progress status. |
| 4 | Upload a .txt file with project requirements | Agent reads the file and creates project/tasks from it. |
| 5 | Check the **sidebar** — your conversations should be saved | Click an old conversation to reload it. |

---

## 2. Knowledge Q&A Agent

**Tab:** Knowledge Q&A

| # | What to do | What should happen |
|---|-----------|-------------------|
| 1 | Select a project, then ask: "How many users do I have, name them" | Shows the count AND lists each user by name. |
| 2 | Ask: "What tasks are assigned to developer1?" | Lists all tasks with title, status, priority. |
| 3 | Ask: "Show me their emails" | Shows email addresses (if available). |
| 4 | Ask: "Compare my projects" | Shows a comparison table of all projects. |
| 5 | Ask: "Create a new task" | Should redirect you to Project Pilot (it only answers questions, doesn't create). |

---

## 3. Task Prioritization Agent

**Tab:** Task Prioritization

| # | What to do | What should happen |
|---|-----------|-------------------|
| 1 | Select a project, click **Prioritize & Order Tasks** | Shows tasks ranked by AI priority with scores, reasoning, and execution order. |
| 2 | Click **Find Bottlenecks** | Shows bottleneck cards with severity, affected tasks, and resolution strategies. |
| 3 | Click **Suggest Delegation** | Shows task reassignment suggestions with workload analysis. |

---

## 4. Timeline & Gantt Agent

**Tab:** Timeline & Gantt

| # | What to do | What should happen |
|---|-----------|-------------------|
| 1 | Select a project, choose **Create Timeline**, click Run | Shows a visual timeline with task bars, dates, and status colors. |
| 2 | Use the **Auto/Days/Weeks/Months** toggle at the top right | Date scale changes accordingly. Weeks should show Mondays. |
| 3 | Choose **Check Deadlines**, click Run | Shows upcoming deadlines and overdue tasks. |
| 4 | Choose **Suggest Adjustments**, click Run | Shows AI suggestions for timeline improvements. |

---

## 5. Meeting Scheduler

**Tab:** Meeting Scheduler

### 5a. Basic Scheduling

| # | What to do | What should happen |
|---|-----------|-------------------|
| 1 | Type: "Schedule a meeting with developer1 tomorrow at 2 PM" | Meeting gets created. Chat shows confirmation with title, time, duration. |
| 2 | Type: "Schedule a meeting with developer1 and userPM on Friday at 10 AM to discuss the API and database migration" | Multi-participant meeting created with agenda items extracted. |
| 3 | Type a non-existent name: "Schedule with xyz" | Shows "user not found" with list of available team members. |
| 4 | Click the **Meetings** tab | See all your scheduled meetings with status badges. |
| 5 | Click the **.ics** download link on a meeting | Downloads a calendar file. Open it — should offer to add to your calendar app. |

### 5b. Recurring Meetings

| # | What to do | What should happen |
|---|-----------|-------------------|
| 6 | Type: "Set up a daily standup with developer1 at 9 AM" | Creates meeting with "Recurring: Weekdays" badge. Multiple occurrences created. |
| 7 | Type: "Schedule a weekly 1-on-1 with userPM on Monday at 3 PM" | Creates with pre-filled agenda (Check-in, Blockers, Goals). Duration auto-set to 30 min. |

### 5c. Smart Features

| # | What to do | What should happen |
|---|-----------|-------------------|
| 8 | Type: "Schedule with developer1 sometime" (no time specified) | Shows available time slots for the next 3 days. |
| 9 | Schedule a meeting at a time where developer1 already has one | Shows "Schedule Conflict Detected" with alternative available slots. |
| 10 | Type: "Show my meetings this week" | Lists your meetings directly in the chat. |
| 11 | Type: "Reschedule my meeting with developer1 to Thursday at 4 PM" | Updates the meeting time. Shows old → new time. Participants get notified. |

### 5d. Accept/Reject Flow

| # | What to do | What should happen |
|---|-----------|-------------------|
| 12 | Log in as the **project user** (developer1) at `http://localhost:3000` | Go to their dashboard. |
| 13 | Click the **bell icon** (top right) | Should show meeting request notification. |
| 14 | Click the **Meetings** tab | Should show the meeting with Accept / Reject buttons. |
| 15 | Click **Accept** on a meeting | Meeting status changes to "Accepted". |
| 16 | Or click **Reject / Suggest Time**, enter a reason and new time, click **Suggest Time** | Meeting status changes to "Counter Proposed". |
| 17 | Go back to the **Company User dashboard** → Meeting Scheduler → Meetings tab | Should show "Counter Proposed" status with the invitee's suggested time. |
| 18 | Click **Accept Proposed Time** | Meeting is confirmed for good. Both sides notified. |
| 19 | Or click **Withdraw** | Meeting is cancelled. Invitee gets notified. |

### 5e. Chat History

| # | What to do | What should happen |
|---|-----------|-------------------|
| 20 | Send a few messages | They appear in the sidebar as saved conversations. |
| 21 | Click the **search icon** in the sidebar, type a keyword | Filters conversations by content. |
| 22 | Click the **trash icon** on a conversation | Deletes it from the sidebar. |
| 23 | Click **+** to start a new conversation | Input clears, ready for a new chat. |

---

## 6. AI Tools Hub

**Tab:** AI Tools

### 6a. Daily Standup

| # | What to do | What should happen |
|---|-----------|-------------------|
| 1 | Select a project, choose Daily, click **Generate** | Shows a standup report with team summary, per-member updates, blockers, action items. |
| 2 | Switch to **Weekly** and generate | Shows weekly stats (total tasks, completed, in progress, blocked, completion rate). |

### 6b. Workflow & SOP

| # | What to do | What should happen |
|---|-----------|-------------------|
| 3 | Select a project, click **Get Suggestions** | Shows workflow phases (expandable), current phase highlighted, recommendations, bottlenecks. |
| 4 | Click **Phase Checklist** | Shows interactive checklist — click items to check them off. Progress bar updates. |
| 5 | Click **Validate Process** | Checks for tasks that skipped review or are stuck too long. |

### 6c. Smart Notifications

| # | What to do | What should happen |
|---|-----------|-------------------|
| 6 | Click **Scan for Issues** | Scans all projects for overdue tasks, blockers, workload imbalance. Shows results. |

### 6d. Meeting Notes Analyzer

| # | What to do | What should happen |
|---|-----------|-------------------|
| 7 | Paste some meeting notes, click **Analyze** | Extracts: summary, action items (with owner/deadline), key decisions, risks, participants. |
| 8 | Paste random unrelated text | Should tell you it's not meeting notes and give instructions on what to paste. |

---

## 7. Notification Bell (Both Dashboards)

| # | What to do | What should happen |
|---|-----------|-------------------|
| 1 | Click the **bell icon** on the company user dashboard | Shows PM notifications (meeting updates, scan results). |
| 2 | Click a meeting notification | Redirects to the Meeting Scheduler tab. |
| 3 | Click the **bell icon** on the project user dashboard | Shows meeting requests and task notifications. |
| 4 | Click a notification | Redirects to the relevant tab (Meetings for meeting notifs, Tasks for task notifs). |
| 5 | Click **Mark all read** | All notifications dim/clear the unread badge. |

---

## 8. Error Handling (Should NOT Break)

| # | What to do | What should happen |
|---|-----------|-------------------|
| 1 | Enter an empty message in any chat and press Enter | Nothing happens (button is disabled when empty). |
| 2 | Select a non-existent project and try to run an agent | Shows a friendly error message, not a crash. |
| 3 | If any tab crashes for any reason | Should show "Something went wrong" with a "Try Again" button — NOT a blank white screen. |

---

## 9. Health Check (For Admins)

| # | What to do | What should happen |
|---|-----------|-------------------|
| 1 | Open in browser: `http://localhost:8000/api/project-manager/health` | Shows JSON with: database status + latency, LLM config status, registered agents list, overall health. |

---

## Quick Smoke Test (5 Minutes)

If you only have 5 minutes, do these:

1. **Project Pilot:** Create a project with "Create a project called Demo App"
2. **Knowledge QA:** Ask "How many tasks does Demo App have?"
3. **Meeting Scheduler:** Type "Schedule a meeting with developer1 tomorrow at 2 PM"
4. **Meetings tab:** Check the meeting appears with status badge
5. **Bell icon:** Check notification appears
6. **Health check:** Visit `http://localhost:8000/api/project-manager/health`

If all 6 pass — the system is working.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Something went wrong" on every request | Check if Django server is running. Check browser console for 500 errors. |
| Meeting scheduler shows no users | Make sure you have project users created (Settings → Team Members). |
| Bell icon shows no notifications | Click it to refresh. Notifications poll every 30 seconds. |
| .ics file doesn't open | Try opening it with Google Calendar (import) or Outlook (drag & drop). |
| Chat history not saving | Check browser console for API errors. Try refreshing the page. |
| Rate limited (429 error) | Wait a few minutes. LLM endpoints are limited to 30 requests/hour. |
