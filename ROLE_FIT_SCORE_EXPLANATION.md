# Role Fit Score Calculation - Detailed Explanation

## Overview
The **role_fit_score** (0-100) is calculated by the `SummarizationAgent` and represents how well a candidate matches a job description based on skills and experience.

**Location**: `recruitment_agent/agents/summarization/summarization_agent.py` → `_compute_fit_score()`

**Note**: The score can be calculated by either:
1. **LLM** (primary) - Uses AI to analyze and score
2. **Rule-based** (fallback) - Uses algorithm when LLM is unavailable

---

## 🎯 Role Fit Score Formula

The role fit score is calculated using **3 components**:

```
Role Fit Score = Skills Match Score (max 85) + Experience Relevance (max 15) + Experience Years Bonus (max 5)
```

**Range**: 0-100 (capped at 100, floored at 0)

---

## 📊 Component Breakdown

### **1. Skills Match Score (0-85 points) - PRIMARY (80-90% weight)**

**Purpose**: Measures how many job keywords match the candidate's skills

**Calculation Process**:

1. **Technology Stack Matching**: Uses comprehensive technology equivalences
   - Example: Job keyword "C#" matches: "C#", ".NET", ".NET Core", "ASP.NET", "Entity Framework"
   - Example: Job keyword "Python" matches: "Python", "Django", "Flask", "FastAPI", "NumPy"
   - Example: Job keyword "React" matches: "React", "React.js", "Next.js", "Redux", "React Native"

2. **Count Matches**: For each job keyword, check if it OR any related technology appears in candidate's skills
   - Uses `skill_matches_keyword()` function from `skill_equivalences.py`
   - Case-insensitive matching
   - Counts unique matches (each keyword counted once)

3. **Calculate Match Percentage**:
   ```
   match_percentage = (matched_keywords / total_keywords) × 100
   ```

4. **Convert to Score (0-85 points)**:
   ```
   If match_percentage >= 90% → 80-85 points
   If match_percentage >= 70% → 60-75 points
   If match_percentage >= 50% → 40-60 points
   If match_percentage >= 30% → 20-40 points
   If match_percentage < 30%  → 0-20 points
   ```

**Example**:
- Job keywords: ["C#", ".NET Core", "SQL Server", "React", "JavaScript"]
- Candidate skills: ["C#", ".NET", "SQL", "React.js", "TypeScript"]
- Matches: 5/5 = 100% → **85 points**

---

### **2. Experience Relevance (0-15 points) - SECONDARY (10-20% weight)**

**Purpose**: Bonus points if job keywords appear in candidate's work experience

**Calculation**:
1. Check all experience entries (role titles + descriptions)
2. Count how many UNIQUE job keywords are found in experience
3. Award bonus points:
   ```
   If 5+ keywords found in experience → +10 to +15 points
   If 3-4 keywords found → +5 to +10 points
   If 1-2 keywords found → +2 to +5 points
   If 0 keywords found → +0 points
   ```

**Example**:
- Job keywords: ["Python", "Django", "PostgreSQL", "AWS"]
- Experience mentions: "Developed Django applications", "Used PostgreSQL database", "Deployed on AWS"
- Keywords found: 3 → **+7 points**

---

### **3. Experience Years Bonus (0-5 points) - TERTIARY**

**Purpose**: Small bonus for candidates with relevant experience

**Calculation**:
```
If total_experience_years >= 5 years → +5 points
If total_experience_years >= 3 years → +3 points
If total_experience_years >= 1 year  → +1 point
If total_experience_years < 1 year  → +0 points
```

**Example**:
- Candidate has 4 years experience → **+3 points**

---

## 🔍 Technology Stack Matching

The system uses **comprehensive technology stack matching** to recognize related technologies:

### **C# / .NET Stack**:
- "C#" matches: "C#", ".NET", ".NET Framework", ".NET Core", "ASP.NET", "Entity Framework", "EF Core"
- "ASP.NET" matches: "ASP.NET", "ASP.NET Core", "ASP.NET MVC", "Web API"

### **Python Stack**:
- "Python" matches: "Python", "Django", "Flask", "FastAPI", "NumPy", "Pandas"
- "Django" matches: "Django", "Django REST Framework", "DRF"

### **JavaScript / Node.js Stack**:
- "JavaScript" matches: "JavaScript", "JS", "Node.js", "React", "Vue", "Angular", "TypeScript"
- "React" matches: "React", "React.js", "Next.js", "Redux", "React Native"
- "Node.js" matches: "Node.js", "Express", "NestJS", "Koa"

### **Java Stack**:
- "Java" matches: "Java", "Spring", "Spring Boot", "Hibernate", "JPA"

### **Cloud & DevOps**:
- "AWS" matches: "AWS", "EC2", "S3", "Lambda", "RDS", "DynamoDB"
- "Docker" matches: "Docker", "Docker Compose", "Containerization"

**Full list**: See `recruitment_agent/skill_equivalences.py`

---

## 📈 Complete Calculation Example

### **Example 1: Strong Match**

**Job Keywords**: ["C#", ".NET Core", "SQL Server", "React", "JavaScript", "Azure"]

**Candidate**:
- Skills: ["C#", ".NET", "ASP.NET", "SQL", "React.js", "TypeScript", "Azure Functions"]
- Experience: "Senior Developer at TechCorp (2020-2023). Built .NET Core APIs, React frontends, Azure deployments"
- Experience Years: 5 years

**Calculation**:
1. **Skills Match**: 
   - "C#" → Matches "C#" ✓
   - ".NET Core" → Matches ".NET" ✓
   - "SQL Server" → Matches "SQL" ✓
   - "React" → Matches "React.js" ✓
   - "JavaScript" → Matches "TypeScript" ✓
   - "Azure" → Matches "Azure Functions" ✓
   - Matches: 6/6 = 100% → **85 points**

2. **Experience Relevance**:
   - Keywords found in experience: ".NET Core", "React", "Azure" = 3 keywords
   - Bonus: **+7 points**

3. **Experience Years**:
   - 5 years → **+5 points**

**Final Role Fit Score**: 85 + 7 + 5 = **97**

---

### **Example 2: Moderate Match**

**Job Keywords**: ["Python", "Django", "PostgreSQL", "AWS", "Docker"]

**Candidate**:
- Skills: ["Python", "Flask", "MySQL", "AWS"]
- Experience: "Developer at Startup (2021-2023). Built Flask APIs, deployed on AWS"
- Experience Years: 2 years

**Calculation**:
1. **Skills Match**:
   - "Python" → Matches "Python" ✓
   - "Django" → Matches "Flask" (Python framework) ✓
   - "PostgreSQL" → Matches "MySQL" (SQL database) ✓
   - "AWS" → Matches "AWS" ✓
   - "Docker" → No match ✗
   - Matches: 4/5 = 80% → **70 points**

2. **Experience Relevance**:
   - Keywords found: "Flask" (Django equivalent), "AWS" = 2 keywords
   - Bonus: **+4 points**

3. **Experience Years**:
   - 2 years → **+1 point**

**Final Role Fit Score**: 70 + 4 + 1 = **75**

---

### **Example 3: Weak Match**

**Job Keywords**: ["Java", "Spring Boot", "Kubernetes", "MongoDB"]

**Candidate**:
- Skills: ["JavaScript", "Node.js", "React", "MySQL"]
- Experience: "Frontend Developer (2022-2023). Built React applications"
- Experience Years: 1 year

**Calculation**:
1. **Skills Match**:
   - "Java" → No match (JavaScript ≠ Java) ✗
   - "Spring Boot" → No match ✗
   - "Kubernetes" → No match ✗
   - "MongoDB" → No match (MySQL ≠ MongoDB) ✗
   - Matches: 0/4 = 0% → **5 points**

2. **Experience Relevance**:
   - Keywords found: 0
   - Bonus: **+0 points**

3. **Experience Years**:
   - 1 year → **+1 point**

**Final Role Fit Score**: 5 + 0 + 1 = **6**

---

## 🔄 LLM vs Rule-Based Calculation

### **LLM Calculation** (Primary):
- Uses AI to analyze CV and job keywords
- Can understand context and nuances
- Follows same general formula but with AI intelligence
- Validated against rule-based score for accuracy

### **Rule-Based Calculation** (Fallback):
- Uses exact algorithm described above
- More predictable and consistent
- Used when LLM is unavailable or fails
- Always available as backup

**Both methods aim for the same result**, but LLM can be more intelligent about edge cases.

---

## ⚠️ Important Notes

1. **Skills are PRIMARY**: 80-90% of the score comes from skills matching
2. **Experience is SECONDARY**: Only adds bonus points (10-20% weight)
3. **Certifications DON'T MATTER**: Completely ignored in scoring
4. **Education DON'T MATTER**: Not considered in role_fit_score
5. **Technology Equivalences**: System recognizes related technologies (C# = .NET, Python = Django, etc.)
6. **No Job Keywords**: If no job keywords provided, evaluates based on skill depth only (0-85 points)

---

## 📝 Summary

**Role Fit Score Formula**:
```
Score = Skills Match (0-85) + Experience Relevance (0-15) + Experience Years (0-5)
```

**Key Points**:
1. **Primary Factor**: Skills matching using technology stack equivalences (85 points max)
2. **Secondary Factor**: Experience relevance bonus (15 points max)
3. **Tertiary Factor**: Experience years bonus (5 points max)
4. **Technology Matching**: Recognizes related technologies (C# = .NET, Python = Django, etc.)
5. **Range**: 0-100 (capped at 100)

**The role fit score is used for ranking candidates and determining their suitability for a role.**
