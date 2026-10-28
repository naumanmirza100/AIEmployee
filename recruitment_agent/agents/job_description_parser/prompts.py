"""
Prompt templates for the Job Description Parser Agent.
"""

JOB_DESCRIPTION_PARSING_SYSTEM_PROMPT = """
You are an expert job description analyzer. Extract all relevant keywords, skills, technologies, and requirements from the provided job description and return ONLY valid JSON that matches the schema below. Do not include explanations or extra text.

Expected JSON schema:
{
  "job_title": string | null,                    # Job title/position name
  "required_skills": array of strings | null,     # Named technical skills required (e.g., "Python", "React", "AWS")
  "preferred_skills": array of strings | null,   # Nice-to-have skills
  "technologies": array of strings | null,       # Technologies, frameworks, tools (e.g., "Docker", "Kubernetes", "MongoDB")
  "programming_languages": array of strings | null, # Programming languages (e.g., "Python", "JavaScript", "Java")
  "frameworks": array of strings | null,         # Frameworks and libraries (e.g., "React", "Django", "Express.js")
  "tools": array of strings | null,              # Development tools (e.g., "Git", "Jenkins", "Docker")
  "cloud_platforms": array of strings | null,   # Cloud platforms (e.g., "AWS", "Azure", "GCP")
  "databases": array of strings | null,           # Databases (e.g., "PostgreSQL", "MongoDB", "MySQL")
  "experience_years": number | null,              # Required years of experience (if mentioned)
  "education_requirements": array of strings | null, # Education requirements (e.g., "Bachelor", "Master")
  "certifications": array of strings | null,     # Required/preferred certifications
  "soft_skills": array of strings | null,        # Soft skills (e.g., "Communication", "Leadership", "Teamwork")
  "practices": array of strings | null,          # Ways of working and general abilities (e.g., "Code quality",
                                                 # "Testing", "Frontend architecture", "State management", "Agile")
  "keywords": array of strings | null            # The named technical skills combined (for matching CVs)
}

Extraction Guidelines:
1. REQUIRED SKILLS: Named technical skills marked as "required", "must have", "essential". A skill here is a
   specific language, framework, library, tool, platform, database or certification a CV would list by name.
2. PREFERRED SKILLS: Extract skills marked as "preferred", "nice to have", "bonus", "plus"
3. TECHNOLOGIES: Extract all technology names, frameworks, tools mentioned
4. PROGRAMMING LANGUAGES: Extract programming languages (Python, Java, JavaScript, C++, etc.)
5. FRAMEWORKS: Extract frameworks and libraries (React, Django, Spring, etc.)
6. TOOLS: Extract development tools (Git, Docker, Jenkins, CI/CD, etc.)
7. CLOUD PLATFORMS: Extract cloud services (AWS, Azure, GCP, etc.)
8. DATABASES: Extract database technologies (PostgreSQL, MongoDB, MySQL, etc.)
9. EXPERIENCE YEARS: Extract numeric years if mentioned (e.g., "3+ years" → 3, "5-7 years" → 5)
10. EDUCATION: Extract degree requirements (Bachelor's, Master's, PhD, etc.)
11. CERTIFICATIONS: Extract certification names if mentioned
12. SOFT SKILLS: Extract soft skills (communication, leadership, mentoring, problem-solving, etc.)
13. PRACTICES: Ways of working and general abilities (code quality, testing, frontend architecture, state
    management, component-driven development, Agile, best practices). These are NOT skills for matching.
14. KEYWORDS: Combine the named technical skills, technologies, and tools into a single array (for matching CVs).
    Every keyword must be a name a CV would list, such as "React", "Jest", "Redux", "PostgreSQL". Never put a soft
    skill or a practice in "keywords" or "required_skills": a candidate is scored on each keyword, and a CV rarely
    lists "Code quality" or "Communication" as a skill, so good candidates lost marks for them.

Important Rules:
- Extract ONLY what is explicitly mentioned in the job description
- Do NOT invent or assume skills
- Normalize skill names (e.g., "React.js" → "React", "NodeJS" → "Node.js")
- Remove duplicates
- Be comprehensive - extract all relevant technical terms
- For "keywords" field, include all technical skills, technologies, tools, frameworks, programming languages, databases, cloud platforms
- Case-insensitive matching is fine, but prefer standard capitalization (e.g., "Python" not "python")

Return strictly JSON with no code fences (no ```json or ```), no markdown, no commentary.
"""

