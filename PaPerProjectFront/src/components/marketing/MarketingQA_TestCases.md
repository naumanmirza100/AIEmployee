# Marketing Q&A - Test Cases for Manual Query vs AI Response Comparison

## Purpose
This file contains 10 test cases to verify that manual API queries return the same results as AI-generated responses for both **Search Mode** and **Graph Mode**.

---

## Test Case 1: Total Campaigns Count
**Mode:** Search  
**Question:** "How many campaigns do we have?"  
**Expected Query:** `SELECT COUNT(*) FROM campaigns`  
**Expected AI Response:**  
```json
{
  "answer": "You currently have [X] campaigns in total.",
  "insights": ["Campaign count breakdown", "Active vs inactive campaigns"]
}
```
**Verification:** Check if AI answer matches the count from manual query

---

## Test Case 2: Active Campaigns
**Mode:** Graph  
**Question:** "Show me a chart of active campaigns"  
**Expected Query:** `SELECT name, status FROM campaigns WHERE status='active'`  
**Expected AI Response:**  
```json
{
  "title": "Active Campaigns Overview",
  "chart": {
    "type": "bar",
    "data": [
      {"label": "Campaign A", "value": 150},
      {"label": "Campaign B", "value": 200}
    ]
  },
  "insights": ["Campaign performance comparison"]
}
```
**Verification:** Chart data matches query results

---

## Test Case 3: Email Open Rates
**Mode:** Search  
**Question:** "What is the average email open rate?"  
**Expected Query:** `SELECT AVG(open_rate) FROM email_campaigns`  
**Expected AI Response:**  
```json
{
  "answer": "The average email open rate across all campaigns is [X]%.",
  "insights": ["Industry benchmark comparison", "Top performing campaigns"]
}
```
**Verification:** AI percentage matches calculated average

---

## Test Case 4: Campaign Performance by Month
**Mode:** Graph  
**Question:** "Generate a line chart showing campaign performance over the last 6 months"  
**Expected Query:** `SELECT month, SUM(conversions) FROM campaigns GROUP BY month ORDER BY month DESC LIMIT 6`  
**Expected AI Response:**  
```json
{
  "title": "Campaign Performance - Last 6 Months",
  "chart": {
    "type": "line",
    "data": [
      {"label": "Jan", "value": 450},
      {"label": "Feb", "value": 520},
      {"label": "Mar", "value": 480}
    ]
  },
  "insights": ["Month-over-month growth trends"]
}
```
**Verification:** Data points match monthly aggregation

---

## Test Case 5: Top Performing Campaigns
**Mode:** Search  
**Question:** "Which campaigns have the highest conversion rate?"  
**Expected Query:** `SELECT name, conversion_rate FROM campaigns ORDER BY conversion_rate DESC LIMIT 5`  
**Expected AI Response:**  
```json
{
  "answer": "The top performing campaigns are:\n1. Campaign X (15.3%)\n2. Campaign Y (14.7%)\n3. Campaign Z (13.2%)",
  "insights": ["Common success factors", "Target audience analysis"]
}
```
**Verification:** Rankings and percentages match query

---

## Test Case 6: Email Status Distribution
**Mode:** Graph  
**Question:** "Show me a pie chart of email statuses"  
**Expected Query:** `SELECT status, COUNT(*) FROM emails GROUP BY status`  
**Expected AI Response:**  
```json
{
  "title": "Email Status Distribution",
  "chart": {
    "type": "pie",
    "data": [
      {"label": "Sent", "value": 1200},
      {"label": "Delivered", "value": 1150},
      {"label": "Opened", "value": 850},
      {"label": "Bounced", "value": 50}
    ]
  },
  "insights": ["Delivery rate analysis", "Action items for bounced emails"]
}
```
**Verification:** Status counts match grouped query

---

## Test Case 7: Failed Campaigns
**Mode:** Search  
**Question:** "How many campaigns failed last quarter?"  
**Expected Query:** `SELECT COUNT(*) FROM campaigns WHERE status='failed' AND created_at >= DATE_SUB(NOW(), INTERVAL 3 MONTH)`  
**Expected AI Response:**  
```json
{
  "answer": "[X] campaigns failed in the last quarter.",
  "insights": ["Common failure reasons", "Recommendations to prevent failures"]
}
```
**Verification:** Failed count matches with date filter

---

## Test Case 8: Campaign Budget Allocation
**Mode:** Graph  
**Question:** "Create a bar chart showing budget allocation across campaigns"  
**Expected Query:** `SELECT name, budget FROM campaigns ORDER BY budget DESC LIMIT 10`  
**Expected AI Response:**  
```json
{
  "title": "Campaign Budget Allocation",
  "chart": {
    "type": "bar",
    "data": [
      {"label": "Campaign A", "value": 50000},
      {"label": "Campaign B", "value": 35000},
      {"label": "Campaign C", "value": 28000}
    ]
  },
  "insights": ["Budget utilization percentage", "ROI comparison"]
}
```
**Verification:** Budget values match query results

---

## Test Case 9: Lead Generation Stats
**Mode:** Search  
**Question:** "How many leads were generated this month?"  
**Expected Query:** `SELECT COUNT(*) FROM leads WHERE created_at >= DATE_FORMAT(NOW(), '%Y-%m-01')`  
**Expected AI Response:**  
```json
{
  "answer": "This month, [X] new leads have been generated.",
  "insights": ["Lead source breakdown", "Conversion funnel metrics"]
}
```
**Verification:** Lead count matches month filter

---

## Test Case 10: Email Template Usage
**Mode:** Graph  
**Question:** "Show me which email templates are most used"  
**Expected Query:** `SELECT template_name, COUNT(*) as usage_count FROM emails GROUP BY template_name ORDER BY usage_count DESC LIMIT 5`  
**Expected AI Response:**  
```json
{
  "title": "Most Used Email Templates",
  "chart": {
    "type": "bar",
    "data": [
      {"label": "Welcome Email", "value": 450},
      {"label": "Newsletter", "value": 380},
      {"label": "Promotion", "value": 320},
      {"label": "Follow-up", "value": 280},
      {"label": "Survey", "value": 150}
    ]
  },
  "insights": ["Template effectiveness rates", "Optimization suggestions"]
}
```
**Verification:** Template usage counts match grouped query

---

## How to Use These Test Cases

### Manual Testing:
1. Open Marketing Q&A component
2. For each test case, enter the question
3. Open browser DevTools Console (F12)
4. Check console logs for comparison results:
   - 🔍 Starting comparison
   - 📊 Manual API Response
   - ✅ Comparison Result

### Automated Verification:
```javascript
// In browser console
window.marketingQAComparison.compareNow("How many campaigns do we have?", "search")
window.marketingQAComparison.getLatestComparison()
```

### Validation Checklist:
- [ ] Manual query returns data
- [ ] AI response contains same data
- [ ] Data format is consistent
- [ ] Insights are relevant
- [ ] No errors in console
- [ ] Response time < 3 seconds
- [ ] Chart renders correctly (for graph mode)
- [ ] Numbers/percentages match exactly

---

## Expected Results

All 10 test cases should show:
- ✅ `success: true` in comparison result
- ✅ Manual API response matches AI response data
- ✅ No errors in console logs
- ✅ Response stored in `comparisonResults` array

If any test fails:
1. Check `window.marketingQAComparison.getAllComparisonStatus()`
2. Review failed comparison details
3. Verify API endpoint is working
4. Check query formatting
5. Validate data transformation logic
