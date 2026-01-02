# Outreach & Campaign Agent - Test Data

## Test Data for Campaign Agent Actions

### 1. Design Campaign Action

**Action:** `design`

**Campaign Name:**
```
Summer Sale 2024
```

**Campaign Description:**
```
Launch a comprehensive summer sale campaign targeting tech-savvy consumers aged 25-45. Focus on increasing brand awareness, driving online sales, and growing our email subscriber base. The campaign should emphasize our new product line and special summer discounts.
```

**Campaign Type:**
```
integrated
```

**Channels:**
- ✅ Email
- ✅ Social Media
- ✅ Paid Ads
- ✅ Partnerships

**Budget:**
```
25000
```

**Campaign Goals (JSON):**
```json
{
  "revenue": 150000,
  "leads": 5000,
  "conversions": 2500,
  "email_subscribers": 3000,
  "social_followers": 2000,
  "brand_awareness": "high"
}
```

**Target Audience (JSON):**
```json
{
  "age_range": "25-45",
  "interests": ["technology", "business", "entrepreneurship", "innovation"],
  "location": "North America",
  "income_level": "middle_to_high",
  "buying_behavior": "online_shoppers",
  "device_preference": "mobile_and_desktop"
}
```

**Additional Context (JSON):**
```json
{
  "industry": "Technology/SaaS",
  "competitors": ["Competitor A", "Competitor B", "Competitor C"],
  "key_messages": [
    "Summer savings up to 40%",
    "New product line launch",
    "Limited time offer",
    "Free shipping on orders over $100"
  ],
  "brand_voice": "Professional yet approachable",
  "campaign_theme": "Summer Innovation"
}
```

---

### 2. Create Multi-Channel Campaign Action

**Action:** `create_multi_channel`

**Campaign Name:**
```
Q4 Product Launch Campaign
```

**Campaign Description:**
```
Launch our new AI-powered marketing tool with a multi-channel campaign. Target B2B customers, emphasize ROI and efficiency gains. Coordinate messaging across all channels for maximum impact.
```

**Campaign Type:**
```
integrated
```

**Channels:**
- ✅ Email
- ✅ Social Media
- ✅ Paid Ads
- ✅ Partnerships

**Budget:**
```
50000
```

**Campaign Goals (JSON):**
```json
{
  "revenue": 500000,
  "trial_signups": 10000,
  "paid_conversions": 2000,
  "demo_requests": 5000,
  "webinar_registrations": 3000
}
```

**Target Audience (JSON):**
```json
{
  "business_type": "B2B",
  "company_size": "50-500 employees",
  "industries": ["Marketing", "Sales", "E-commerce"],
  "decision_makers": ["CMO", "Marketing Director", "VP of Marketing"],
  "geographic_region": "Global",
  "budget_range": "$10k-$100k annual marketing spend"
}
```

**Start Date:**
```
2024-10-01
```

**End Date:**
```
2024-12-31
```

**Additional Context (JSON):**
```json
{
  "industry": "B2B SaaS",
  "product_name": "AI Marketing Pro",
  "key_features": [
    "AI-powered campaign optimization",
    "Multi-channel automation",
    "Real-time analytics",
    "ROI tracking"
  ],
  "competitors": ["HubSpot", "Marketo", "Salesforce Marketing Cloud"],
  "unique_selling_points": [
    "AI-first approach",
    "Ease of use",
    "Affordable pricing",
    "Fast implementation"
  ]
}
```

---

### 3. Launch Campaign Action

**Action:** `launch`

**Campaign ID:**
```
1
```

*(Note: Use an existing campaign ID from your database)*

---

### 4. Manage Campaign Action

**Action:** `manage`

**Campaign ID:**
```
1
```

**Additional Context (Optional JSON):**
```json
{
  "focus_areas": ["performance", "messaging_consistency", "budget_optimization"],
  "concerns": [
    "CTR is lower than expected",
    "Email open rates declining",
    "Need to optimize ad spend"
  ]
}
```

---

### 5. Optimize Campaign Action

**Action:** `optimize`

**Campaign ID:**
```
1
```

**Additional Context (Optional JSON):**
```json
{
  "optimization_focus": "performance",
  "priority_channels": ["email", "paid"],
  "constraints": {
    "budget_limit": 50000,
    "cannot_change_messaging": false,
    "must_maintain_brand_voice": true
  },
  "current_issues": [
    "Low conversion rate on paid ads",
    "Email engagement dropping",
    "High cost per acquisition"
  ]
}
```

---

### 6. Schedule Campaign Action

**Action:** `schedule`

**Campaign ID:**
```
1
```

**Start Date:**
```
2024-11-01
```

**End Date:**
```
2024-11-30
```

**Additional Context (Optional JSON):**
```json
{
  "launch_sequence": "email_first",
  "channel_stagger": true,
  "peak_times": {
    "email": "Tuesday-Thursday, 9-11 AM",
    "social": "Monday-Friday, 12-2 PM, 6-8 PM",
    "paid": "Monday-Friday, 9 AM - 5 PM"
  },
  "timezone": "EST"
}
```

---

## Quick Test Scenarios

### Scenario 1: Quick Email Campaign Design
- **Action:** `design`
- **Campaign Name:** `Holiday Email Blast`
- **Campaign Type:** `email`
- **Channels:** Email only
- **Budget:** `5000`
- **Goals:** `{"revenue": 50000, "email_opens": 10000, "clicks": 2000}`
- **Audience:** `{"age_range": "30-50", "interests": ["shopping", "deals"]}`

### Scenario 2: Social Media Campaign
- **Action:** `design`
- **Campaign Name:** `Brand Awareness Social Campaign`
- **Campaign Type:** `social`
- **Channels:** Social Media only
- **Budget:** `15000`
- **Goals:** `{"impressions": 1000000, "engagement": 50000, "followers": 5000}`
- **Audience:** `{"platforms": ["Facebook", "Instagram", "LinkedIn"], "age_range": "25-40"}`

### Scenario 3: Paid Advertising Campaign
- **Action:** `design`
- **Campaign Name:** `Google Ads Lead Generation`
- **Campaign Type:** `paid`
- **Channels:** Paid Ads only
- **Budget:** `20000`
- **Goals:** `{"leads": 2000, "cpa": 10, "conversions": 500}`
- **Audience:** `{"keywords": ["marketing software", "crm tools"], "location": "United States"}`

---

## Sample Campaign IDs for Testing

After creating campaigns, you can use these IDs for testing launch, manage, optimize, and schedule actions:

1. Create a campaign first using `create_multi_channel` action
2. Note the `campaign_id` from the response
3. Use that ID for subsequent actions

**Example Response:**
```json
{
  "success": true,
  "action": "create_multi_channel",
  "campaign_id": 1,
  "campaign_name": "Summer Sale 2024",
  "status": "draft",
  "channels": ["email", "social", "paid", "partnership"]
}
```

Use `campaign_id: 1` for launch, manage, optimize, and schedule actions.

---

## Tips for Testing

1. **Start with Design**: Always test the `design` action first to see campaign strategy
2. **Create Campaign**: Use `create_multi_channel` to save a campaign to the database
3. **Launch**: Use the campaign ID to launch the campaign
4. **Manage**: Check campaign performance and get recommendations
5. **Optimize**: Get optimization suggestions based on current performance
6. **Schedule**: Set up campaign timeline and scheduling

---

## JSON Format Examples

### Valid Goals JSON:
```json
{
  "revenue": 100000,
  "leads": 5000,
  "conversions": 2000,
  "email_subscribers": 3000
}
```

### Valid Target Audience JSON:
```json
{
  "age_range": "25-45",
  "interests": ["technology", "business"],
  "location": "North America",
  "income_level": "middle_to_high"
}
```

### Valid Context JSON:
```json
{
  "industry": "Technology",
  "competitors": ["Competitor A", "Competitor B"],
  "key_messages": ["Message 1", "Message 2"],
  "brand_voice": "Professional"
}
```

