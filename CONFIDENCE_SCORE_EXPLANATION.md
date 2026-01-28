# Confidence Score Calculation - Detailed Explanation

## Overview
The **confidence_score** (also called **qualification_confidence**) is calculated by the `LeadQualificationAgent` and represents how confident the system is in the hiring decision (INTERVIEW/HOLD/REJECT).

**Location**: `recruitment_agent/agents/lead_qualification/lead_qualification_agent.py` → `_recruiter_decide()`

---

## 🎯 Confidence Score Formula

The confidence score is calculated using **4 components** that add up to a maximum of 100:

```
Confidence Score = Base Score + Skill Evidence + Match Quality + Experience Boost
```

**Range**: 0-100 (capped at 100, floored at 0)

---

## 📊 Component Breakdown

### **1. Base Score (0-100 points)**
**Purpose**: Starting point based on role_fit_score or match ratio

**Calculation**:
- **If `role_fit_score` exists**: Use it directly as base score
- **If no role_fit_score**:
  - `matched_count == 0` → Base = **20**
  - `match_ratio < 0.4` (40%) → Base = **30**
  - `match_ratio >= 0.4` → Base = **40**

**Example**:
- Candidate with role_fit_score of 75 → Base = 75
- Candidate with 5/10 matches (50%) but no role_fit_score → Base = 40

---

### **2. Skill Evidence Score (0-30 points)**
**Purpose**: Rewards candidates with more matched and inferred skills

**Formula**:
```
Skill Evidence = min(30, (matched_count × 3) + (inferred_skills_count × 1))
```

**Breakdown**:
- **Explicit matched skills**: 3 points each
- **Inferred skills**: 1 point each
- **Maximum**: 30 points

**Examples**:
- 10 matched + 5 inferred = (10×3) + (5×1) = 35 → **Capped at 30**
- 4 matched + 8 inferred = (4×3) + (8×1) = 20 → **20 points**
- 2 matched + 3 inferred = (2×3) + (3×1) = 9 → **9 points**

---

### **3. Match Quality Score (0-30 points)**
**Purpose**: Rewards higher match percentages with bonus points

**Formula** (based on match_ratio = matched_count / total_keywords):
```
Match Ratio >= 80% → +30 points
Match Ratio >= 65% → +22 points
Match Ratio >= 50% → +12 points
Match Ratio >= 35% → +5 points
Match Ratio < 35%  → +0 points
```

**Examples**:
- 12/15 keywords matched (80%) → **+30 points**
- 8/12 keywords matched (67%) → **+22 points**
- 5/10 keywords matched (50%) → **+12 points**
- 4/10 keywords matched (40%) → **+5 points**
- 2/10 keywords matched (20%) → **+0 points**

---

### **4. Experience Boost (0-8 points)**
**Purpose**: Small bonus for candidates with relevant experience

**Formula**:
```
Experience >= 5 years → +8 points
Experience >= 3 years → +5 points
Experience >= 1 year  → +2 points
Experience < 1 year  → +0 points
```

**Examples**:
- 7 years experience → **+8 points**
- 4 years experience → **+5 points**
- 2 years experience → **+2 points**
- 0.5 years experience → **+0 points**

---

## ⚠️ Important Note

**Confidence score is ALWAYS calculated**, even for weak candidates with very low match ratios or few matched skills. The score will simply be low (e.g., 1-20%), but it will still be calculated and displayed.

**No gating rules**: All candidates receive a calculated confidence score, regardless of match count or match ratio.

---

## 📈 Complete Calculation Example

### **Example 1: Strong Candidate**

**Inputs**:
- `role_fit_score`: 85
- `matched_count`: 12 out of 15 keywords
- `inferred_skills`: 8 skills
- `total_exp_years`: 6 years

**Calculation**:
1. **Base Score**: 85 (from role_fit_score)
2. **Skill Evidence**: min(30, (12×3) + (8×1)) = min(30, 44) = **30**
3. **Match Quality**: 12/15 = 80% → **+30**
4. **Experience Boost**: 6 years → **+8**

**Final Confidence Score**: 85 + 30 + 30 + 8 = **153** → **Capped at 100**

**Decision**: 100 >= 65 (interview_threshold) → **INTERVIEW**

---

### **Example 2: Moderate Candidate**

**Inputs**:
- `role_fit_score`: None (not provided)
- `matched_count`: 6 out of 12 keywords
- `inferred_skills`: 4 skills
- `total_exp_years`: 2.5 years

**Calculation**:
1. **Base Score**: 6/12 = 50% → **40** (since match_ratio >= 0.4)
2. **Skill Evidence**: min(30, (6×3) + (4×1)) = min(30, 22) = **22**
3. **Match Quality**: 6/12 = 50% → **+12**
4. **Experience Boost**: 2.5 years → **+2**

**Final Confidence Score**: 40 + 22 + 12 + 2 = **76**

**Decision**: 76 >= 65 (interview_threshold) → **INTERVIEW**

---

### **Example 3: Weak Candidate (Low Score)**

**Inputs**:
- `role_fit_score`: None
- `matched_count`: 2 out of 10 keywords
- `inferred_skills`: 1 skill
- `total_exp_years`: 0.5 years
- `match_ratio`: 20% (< 35%)

**Calculation**:
1. **Base Score**: 2/10 = 20% → **30** (since match_ratio < 0.4)
2. **Skill Evidence**: min(30, (2×3) + (1×1)) = min(30, 7) = **7**
3. **Match Quality**: 2/10 = 20% → **+0** (below 35%)
4. **Experience Boost**: 0.5 years → **+0**

**Final Confidence Score**: 30 + 7 + 0 + 0 = **37**

**Decision**: 37 < 45 (hold_threshold) → **REJECT**

**Note**: Even weak candidates receive a calculated confidence score (37% in this case), not zero.

---

### **Example 4: Hold Candidate**

**Inputs**:
- `role_fit_score`: 50
- `matched_count`: 5 out of 12 keywords
- `inferred_skills`: 3 skills
- `total_exp_years`: 1.5 years

**Calculation**:
1. **Base Score**: 50 (from role_fit_score)
2. **Skill Evidence**: min(30, (5×3) + (3×1)) = min(30, 18) = **18**
3. **Match Quality**: 5/12 = 42% → **+5** (between 35-50%)
4. **Experience Boost**: 1.5 years → **+2**

**Final Confidence Score**: 50 + 18 + 5 + 2 = **75**

**Wait, that's 75, which is >= 65, so it would be INTERVIEW...**

Let me recalculate with different numbers:

**Inputs** (revised):
- `role_fit_score`: 40
- `matched_count`: 4 out of 12 keywords
- `inferred_skills`: 2 skills
- `total_exp_years`: 1 year

**Calculation**:
1. **Base Score**: 40 (from role_fit_score)
2. **Skill Evidence**: min(30, (4×3) + (2×1)) = min(30, 14) = **14**
3. **Match Quality**: 4/12 = 33% → **+0** (below 35%, but gating rule would apply)
4. **Experience Boost**: 1 year → **+2**

Actually, if match_ratio is 33% (< 35%), gating rule applies. Let me use a valid example:

**Inputs** (valid HOLD example):
- `role_fit_score`: 45
- `matched_count`: 5 out of 12 keywords (42% match - passes gating)
- `inferred_skills`: 2 skills
- `total_exp_years`: 1 year

**Calculation**:
1. **Base Score**: 45 (from role_fit_score)
2. **Skill Evidence**: min(30, (5×3) + (2×1)) = min(30, 17) = **17**
3. **Match Quality**: 5/12 = 42% → **+5** (between 35-50%)
4. **Experience Boost**: 1 year → **+2**

**Final Confidence Score**: 45 + 17 + 5 + 2 = **69**

**Decision**: 69 >= 65 (interview_threshold) → **INTERVIEW**

Actually, for HOLD, we need score between 45-64. Let me fix:

**Inputs** (HOLD example):
- `role_fit_score`: 35
- `matched_count`: 5 out of 12 keywords (42% match)
- `inferred_skills`: 2 skills
- `total_exp_years`: 1 year

**Calculation**:
1. **Base Score**: 35 (from role_fit_score)
2. **Skill Evidence**: min(30, (5×3) + (2×1)) = min(30, 17) = **17**
3. **Match Quality**: 5/12 = 42% → **+5**
4. **Experience Boost**: 1 year → **+2**

**Final Confidence Score**: 35 + 17 + 5 + 2 = **59**

**Decision**: 59 >= 45 (hold_threshold) AND 59 < 65 (interview_threshold) → **HOLD**

---

## 🎯 Decision Thresholds

The confidence score is compared against thresholds to make the decision:

### **Default Thresholds**:
- **INTERVIEW**: Score >= **65**
- **HOLD**: Score >= **45** AND < 65
- **REJECT**: Score < **45**

### **Custom Thresholds**:
- Can be configured per company via `RecruiterQualificationSettings`
- `interview_threshold`: Default 65 (minimum for INTERVIEW)
- `hold_threshold`: Default 45 (minimum for HOLD)
- `use_custom_thresholds`: Boolean flag to enable custom thresholds

---

## 🔍 Key Differences: Confidence Score vs Role Fit Score

| Aspect | Confidence Score | Role Fit Score |
|--------|-----------------|----------------|
| **Purpose** | Hiring decision confidence | Candidate-job match quality |
| **Location** | `LeadQualificationAgent` | `SummarizationAgent` |
| **Components** | Base + Skill Evidence + Match Quality + Experience | Skills Match + Experience Relevance + Experience Years |
| **Max Points** | 100 (can exceed, then capped) | 100 |
| **Used For** | INTERVIEW/HOLD/REJECT decision | Ranking candidates |
| **Calculation** | More complex, includes skill evidence | Simpler, focuses on match percentage |

---

## 📝 Summary

**Confidence Score Formula**:
```
Confidence = Base Score + Skill Evidence (max 30) + Match Quality (max 30) + Experience (max 8)
```

**Key Points**:
1. **Always Calculated**: Confidence score is always calculated, even for very weak candidates (no gating rules)
2. **Base Score**: Uses role_fit_score if available, otherwise calculates from match ratio
3. **Skill Evidence**: Rewards both explicit matches (3x) and inferred skills (1x)
4. **Match Quality**: Bonus points for higher match percentages (0 points if < 35%)
5. **Experience**: Small boost for experienced candidates
6. **Decision**: Based on thresholds (default: 65 for INTERVIEW, 45 for HOLD)
7. **Minimum Score**: Weak candidates can receive scores as low as 1-20%, but never zero

**The confidence score directly determines the hiring decision (INTERVIEW/HOLD/REJECT).**
