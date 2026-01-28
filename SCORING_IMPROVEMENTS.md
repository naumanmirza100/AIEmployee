# CV Scoring & API Optimization Improvements

## Summary
This document outlines the improvements made to the recruitment agent system to:
1. **Improve score accuracy** (role_fit_score and confidence_score)
2. **Handle Groq API key expiration** gracefully
3. **Minimize API calls** while maintaining accuracy

---

## 🎯 Key Improvements

### 1. **Enhanced Score Calculation Accuracy**

#### **Improved `role_fit_score` Algorithm**
- **Location**: `recruitment_agent/agents/summarization/summarization_agent.py` → `_compute_fit_score()`
- **Changes**:
  - More granular scoring based on match percentage
  - Better distribution: 0-100 scale with proper ranges
  - **Primary (85 pts)**: Skills matching with technology stack equivalences
  - **Secondary (15 pts)**: Experience relevance (keywords in experience descriptions)
  - **Tertiary (5 pts)**: Experience years boost

#### **Scoring Breakdown**:
```
Match Ratio >= 90%  → 85 points (excellent match)
Match Ratio >= 75%  → 70-79 points (very good match)
Match Ratio >= 60%  → 55-69 points (good match)
Match Ratio >= 45%  → 40-54 points (moderate match)
Match Ratio >= 30%  → 25-39 points (fair match)
Match Ratio >= 15%  → 10-24 points (weak match)
Match Ratio < 15%   → 0-9 points (poor match)
```

#### **Experience Relevance Bonus**:
- 5+ keywords in experience → +15 pts
- 3+ keywords in experience → +10 pts
- 1+ keyword in experience → +5 pts

#### **Experience Years Boost**:
- 5+ years → +5 pts
- 3+ years → +3 pts
- 1+ years → +1 pt

---

### 2. **LLM-First Approach with Score Validation**

#### **LLM as Primary Method**
- **LLM is PRIMARY**: Full LLM analysis for all summarization tasks
- **Rule-Based is FALLBACK**: Only used if LLM fails or API key expires
- **Score Validation**: LLM scores are validated against actual skill match percentage
- **Auto-Correction**: If LLM score doesn't match skill match %, it's automatically corrected

#### **LLM-First Summarization Flow**:
```python
1. Try LLM summarization (PRIMARY - full analysis)
   - Generates candidate_summary, role_fit_score, key_skills, etc.
   - Uses comprehensive prompt with technology stack matching
2. Validate LLM scores against actual skill match percentage
   - If score is inaccurate, recalculate using improved rule-based method
   - Mark as "llm_validated" if corrected, "llm" if accurate
3. FALLBACK: Rule-based calculation (only if LLM fails)
   - Used when API key expires or LLM unavailable
   - Marked as "rule_based_fallback"
```

#### **Score Validation Logic**:
- Compares LLM score to actual skill match percentage
- If 90%+ match but score < 70 → Auto-correct
- If 75%+ match but score < 55 → Auto-correct
- If 60%+ match but score < 40 → Auto-correct
- Ensures scores always reflect actual candidate fit

---

### 3. **Groq API Key Expiration Handling**

#### **Enhanced GroqClient**
- **Location**: `recruitment_agent/core.py`
- **Features**:
  - Detects API key expiration (401/403 errors)
  - Detects rate limits (429 errors)
  - Raises `GroqClientError` with `is_auth_error` flag
  - Clear error messages for debugging

#### **Error Handling in Agents**:

**CV Parser**:
- Detects API key expiration during parsing
- Returns clear error message to user
- Prevents partial processing

**Summarization Agent**:
- Detects API key expiration during LLM summarization
- Disables LLM for current session
- Falls back to rule-based calculation
- No interruption to CV processing

**Job Description Parser**:
- Detects API key expiration
- Logs error clearly
- Allows fallback to manual keywords

**API View**:
- Catches API key expiration errors
- Returns HTTP 503 with clear message
- Guides user to update API key

---

### 4. **Improved Confidence Score (Qualification)**

The `confidence_score` from `LeadQualificationAgent` remains accurate:
- Uses same skill matching with equivalences
- Validates against match percentage
- Gating rules prevent false positives
- Custom thresholds supported per company

---

## 📊 Score Accuracy Improvements

### **Before**:
- LLM-based scoring was sometimes inconsistent
- Scores sometimes didn't match skill match percentage
- Example: 12/13 keywords matched → score of 11 (incorrect!)

### **After**:
- LLM-first approach with intelligent analysis
- Score validation ensures accuracy
- Auto-correction if LLM score doesn't match reality
- Example: 12/13 keywords matched (92%) → LLM score validated/corrected to 85+ (correct!)
- Technology stack equivalences properly recognized in LLM prompt

---

## 🔄 Flow Changes

### **Flow**:
```
CV Upload → Parse (Groq) → Summarize (Groq LLM) → [Validate Scores] → Enrich → Qualify → Rank
           [API Call 1]    [API Call 2]              [Auto-correct if needed]
           
FALLBACK (if LLM fails):
CV Upload → Parse (Groq) → Summarize (Rule-based) → Enrich → Qualify → Rank
           [API Call 1]    [NO API CALL - Fallback]
```

### **Benefits**:
1. **Intelligent**: LLM provides comprehensive analysis
2. **Accurate**: Score validation ensures correctness
3. **Resilient**: Falls back to rule-based if API fails
4. **Validated**: Auto-correction ensures scores match reality

---

## 🛡️ Error Handling

### **API Key Expiration Scenarios**:

1. **During CV Parsing**:
   - Error caught immediately
   - Returns HTTP 503 with clear message
   - User can update API key and retry

2. **During LLM Summarization**:
   - Error caught gracefully
   - LLM disabled for session
   - Processing continues with rule-based fallback
   - No interruption to user

3. **During Job Description Parsing**:
   - Error logged
   - Falls back to manual keywords if provided
   - Processing continues

---

## 📝 Configuration

### **Environment Variables**:
- `GROQ_REC_API_KEY`: Primary API key for recruitment agent
- `GROQ_API_KEY`: Fallback API key
- `GROQ_MODEL`: Model to use (default: llama-3.1-8b-instant)

### **Settings**:
- LLM is primary method (automatic)
- Score validation ensures accuracy
- If API key expires, system falls back to rule-based
- No configuration needed - works out of the box

---

## ✅ Testing Recommendations

1. **Test Score Accuracy**:
   - Upload CVs with known skill matches
   - Verify scores match expected ranges
   - Check that 90%+ match gives 85+ score

2. **Test API Key Expiration**:
   - Use invalid API key
   - Verify graceful error handling
   - Confirm rule-based results still work

3. **Test Score Validation**:
   - Upload CVs with known skill matches
   - Verify LLM scores are validated/corrected if inaccurate
   - Confirm fallback works if API key expires

---

## 🎯 Results

### **Accuracy**:
- ✅ LLM provides intelligent analysis
- ✅ Score validation ensures accuracy
- ✅ Auto-correction prevents inaccurate scores
- ✅ Technology stack equivalences properly recognized

### **Efficiency**:
- ✅ LLM-first approach for intelligent analysis
- ✅ Score validation ensures accuracy
- ✅ Graceful fallback if API fails
- ✅ Auto-correction prevents inaccurate scores

### **Reliability**:
- ✅ Graceful handling of API key expiration
- ✅ System continues working even if API fails
- ✅ Clear error messages for debugging

---

## 📚 Files Modified

1. `recruitment_agent/core.py` - Enhanced GroqClient error handling
2. `recruitment_agent/agents/summarization/summarization_agent.py` - LLM-first approach with score validation
3. `recruitment_agent/agents/cv_parser/cv_parser_agent.py` - Error handling for API expiration
4. `recruitment_agent/agents/job_description_parser/job_description_parser_agent.py` - Error handling
5. `api/views/recruitment_agent.py` - Error handling in API endpoints

---

## 🚀 Next Steps (Optional)

1. **Caching**: Job descriptions already cached in database (keywords_json)
2. **Batch Processing**: Could optimize further for bulk CV processing
3. **Monitoring**: Add metrics for API call counts and success rates
