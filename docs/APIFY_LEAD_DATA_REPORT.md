# Apify for AI SDR lead data: is the free plan good enough?

Date: 2026-10-02

## Short answer

**The free plan is good enough to test, not to run real outreach.**

- Apify's free plan is limited, and the default actor in our code returns no emails at all.
- The best Apify actor for emails (`code_crafter/leads-finder`) does return emails. Its data quality is mixed, and Apify publishes no accuracy figure for it.
- Treat Apify as a source of raw leads. Verify emails before sending, or bounces will damage the sending domain.

## 1. What our code uses today

Source: `ai_sdr_agent/agents/lead_research_agent.py`

| Setting | Behaviour |
|---|---|
| Default actor (`APIFY_ACTOR_ID` empty) | `apify/google-search-scraper`, with queries like `site:linkedin.com/in "CEO" SaaS` |
| What that actor yields in our code | Name, job title and company, parsed from the Google result title. **Email is always empty** (`_parse_google_result` sets `'email': ''`) |
| Alternative actor | `code_crafter/leads-finder`. Our code maps the ICP to its filters and always asks for `email_status: validated` |
| Token in this machine's `.env` | Not set, so nothing could be run live in this report |

**Consequence:** with the default actor you get LinkedIn profile names with no email. This is why "proper emails and data are not coming". It is a setup problem as much as a free-plan problem.

## 2. What the free plan gives

| Item | Free plan |
|---|---|
| Price | $0 per month, no credit card |
| Included credit | $5 of platform usage per month |
| Concurrent runs / retention | 25 runs, 7 days of data |
| Support | Discord only |
| Paid entry plan | Starter, $19 per month |

Sources: [use-apify pricing](https://use-apify.com/docs/what-is-apify/apify-pricing), [checkthat.ai](https://checkthat.ai/brands/apify/pricing), [G2](https://www.g2.com/products/apify/pricing).

Independent reviewers say the free credit is enough to test actors but runs out quickly on real projects ([G2 summary](https://www.g2.com/products/apify/pricing), [SyncGTM review](https://syncgtm.com/blog/apify-review-2026)).

## 3. The actors that matter

### 3a. `code_crafter/leads-finder` (Apollo-style contact search)

Source: [actor page](https://apify.com/code_crafter/leads-finder)

| Item | Finding |
|---|---|
| Returns | Business email, personal email, LinkedIn URL, company details; mobile numbers only on paid plans |
| Price | From **$1.50 per 1,000 leads** |
| **Free plan limit** | **Maximum 100 leads per run**, no mobile numbers |
| Popularity | About 48,000 users, 99.3% of runs succeed |
| User rating | **3.46 out of 5** |
| Accuracy claim | None. The page offers a "validated" email filter but publishes no accuracy or bounce numbers |

In theory $5 of credit buys about 3,300 leads at $1.50 per 1,000. In practice the 100-lead cap per run means many runs, and I could not confirm any extra per-run costs.

Problems reported by users on the actor's Issues tab. I only saw the issue titles and search summaries; the full threads and the developer's replies were not readable, so I could not check whether they were resolved:

- "Only ~30% have emails" (a user calling it "awful and unreliable").
- "Not correct data": leads from cities that were not requested, and 637 results with no email.
- Asked for 1 result with validated emails and received 100.
- Pasted a list of websites with decision-maker titles and received 100 leads from one unrelated company.

A third-party guide also warns to de-duplicate on LinkedIn URL because email fallbacks collide more than expected ([use-apify guide](https://use-apify.com/docs/best-apify-actors/best-lead-generation-actors)).

### 3b. `apify/google-search-scraper` (our default)

Source: [actor page](https://apify.com/apify/google-search-scraper)

- Base price: $1.80 per 1,000 search result pages.
- It has an optional **business lead enrichment** feature that adds name, work email, phone, job title and LinkedIn. It is billed as an extra and is applied to every domain found, including news and directory sites.
- Our code does not turn this on, so we get search results only.

### 3c. LinkedIn and website email scrapers

From the [use-apify guide](https://use-apify.com/docs/best-apify-actors/best-lead-generation-actors):

- HarvestAPI LinkedIn scrapers: $4 per 1,000 profiles, or $10 per 1,000 with SMTP-validated email search. Emails found are mostly **personal** (gmail, outlook) unless the profile lists a work address.
- Contact Details Scraper (vdrmota): about $1.05 per 1,000 pages. Expect mostly **role** emails such as `sales@` or `hello@`.
- Google Maps exports show emails inconsistently, usually only `info@` or `contact@`.

## 4. How reliable is the email data?

- Apify has **no published accuracy benchmark** for contact data. "Contact data from scraping actors is unverified — bounce rates and deliverability vary significantly" ([SyncGTM](https://syncgtm.com/blog/apify-review-2026)).
- The same review says Apify has no verified contact database, and recommends budgeting for verification, de-duplication and CRM mapping on top.
- For comparison, Apollo (a paid database) says its verification is about 91% accurate, and third-party 2026 data shows 8 to 15% bounce rates without extra verification ([typpout](https://www.typpout.com/blog/apollo-io-email-accuracy/)). Best practice is under 3% bounces.
- Apollo's free plan limits are reported inconsistently: sources say 100 or 10,000 email credits per month, and only 10 exports ([Warmly](https://www.warmly.ai/p/blog/apollo-pricing), [PhantomBuster](https://phantombuster.com/blog/ai-automation/apollo-pricing/)). Check Apollo's own pricing page before relying on it.

## 5. Verdict for the AI SDR agent

| Question | Answer |
|---|---|
| Does the free plan give emails with the default setup? | **No.** The default actor returns profiles without emails |
| Can the free plan give emails at all? | **Yes, with `leads-finder`**, up to 100 leads per run, with unproven quality |
| Is the data "proper"? | Mixed. Reports of low email coverage and off-target results, no published accuracy |
| Safe to send to without checking? | **No.** Unverified lists can push bounce rates above the safe level |

## 6. Recommendations

1. **Switch the actor.** Set `APIFY_ACTOR_ID=code_crafter/leads-finder` (or enter it in SDR Settings) and update the onboarding text in `SDROverviewTab.jsx`, which still says the default searches Google for LinkedIn profiles.
2. **Run a measured test before trusting it:**
   - one 100-lead run on the free plan with your real ICP;
   - record the percentage of leads with an email and the percentage that match the ICP;
   - email 50 of them from a spare domain and record the bounce rate.
   Decide with those numbers. Under 3% bounces is the target.
3. **Verify emails before sending.** Add a verification step (for example NeverBounce, ZeroBounce, or Apify's own email-verification actors). Do not enroll leads without an email.
4. **Keep the new bounce handling.** The last two PRs added bounce detection, retry limits and send throttling, which limits damage from bad data.
5. **If quality is too low, compare paid sources** such as Apollo's paid plan or a waterfall-enrichment tool, using the same 100-lead test.

## Limits of this report

- No live Apify run was done: no token was configured on this machine.
- Issue titles and counts come from the actor's public Issues tab as shown in search results. The developer's replies could not be read.
- Prices and plan limits change often. Confirm them on Apify's pricing page before buying.
