# Knowledge QA Agent — Restrictions Removed

## 1. System Prompt Restrictions Removed

| # | Old Restriction | What Changed |
|---|----------------|-------------|
| 1 | "You ONLY provide descriptive answers and information - you do NOT perform actions" | Softened to "You provide descriptive answers. For actions, redirect to Project Pilot" |
| 2 | "You have READ-ONLY access to user information" | Removed entirely — was making LLM refuse to share user details |
| 3 | "You can view and report on user information, but you CANNOT create, update, or delete users" | Removed — unnecessary since the agent has no write capability anyway |
| 4 | "Answer ONLY what the user asked. Do NOT add extra information they did not request" | Changed to "Answer the user's question fully and completely. Include all relevant details" |
| 5 | "If they ask about users, only provide user info. Do NOT include task assignments unless they specifically ask" | Changed to "When listing users, include name, username, email, and role by default" |
| 6 | "If they ask about tasks, only provide task info. Do NOT add user details unless relevant" | Changed to "When listing tasks, include title, status, priority, assignee, and due date by default" |
| 7 | "If they ask for a count, give the number and one short sentence. Do NOT list items unless asked" | Changed to "If user asks how many AND name them, give both count AND full list" |

## 2. Context String Restrictions Removed

| # | Location | Old Text | New Text |
|---|----------|----------|----------|
| 1 | User context header | "USERS ADDED BY COMPANY USER" + "NOTE: You have READ-ONLY access..." | Just "COMPANY USERS" — removed the READ-ONLY warning |
| 2 | Aggregates context | "Answer using ONLY the numbers above. Do not list individual tasks or users." | "Use the data above to answer the question." |

## 3. LLM Prompt Restrictions Removed

| # | Path | Old Instruction | New Instruction |
|---|------|----------------|-----------------|
| 1 | Count/aggregate fallback prompt | "Give ONLY the requested number(s) and at most one short sentence. Do not list individual tasks, projects, or users." | "Provide the numbers and any relevant details the user asked for." |
| 2 | Detail/list prompt | "Answer ONLY what the user asked. Do NOT volunteer extra information" | "Answer the question fully using all relevant data" |
| 3 | Detail/list prompt | "provide ONLY user info. Do NOT include task assignments" | "include their name, username, email, and role" |
| 4 | Detail/list prompt | "provide ONLY task info. Do NOT add unrelated user details" | "include title, status, priority, assignee, and deadline" |
| 5 | Detail/list prompt | "Do NOT add disclaimers, notes, or please note sections" | Removed entirely |

## Summary

The agent was over-restricted — it would refuse to list user names even when explicitly asked ("name them"). All restrictions that prevented the agent from sharing available data have been removed. The agent now provides complete, detailed answers with all relevant information from the context.

The only remaining restriction is the action redirect: if the user asks to create/update/delete something, it redirects them to the Project Pilot agent (which is correct behavior since KnowledgeQA has no write access).
