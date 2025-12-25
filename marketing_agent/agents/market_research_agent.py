"""
Market & Competitive Research Agent
Continuously analyzes market trends, customer behavior, and competitor activities
to identify opportunities, risks, and positioning strategies.
"""

from .marketing_base_agent import MarketingBaseAgent
from typing import Dict, Optional, List
from marketing_agent.models import MarketResearch
from django.contrib.auth.models import User
import json
from datetime import datetime


class MarketResearchAgent(MarketingBaseAgent):
    """
    Market & Competitive Research Agent
    
    This agent:
    - Analyzes market trends and opportunities
    - Tracks competitor activities and strategies
    - Identifies customer behavior patterns
    - Discovers market opportunities and threats
    - Generates positioning strategies
    - Stores research findings for use by Q&A and other agents
    
    This is Phase 2 - feeds insights into Q&A agent and other marketing agents.
    """
    
    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Market & Competitive Research Agent for a marketing system.
        Your role is to:
        1. Analyze market trends and identify opportunities
        2. Research competitor activities and strategies
        3. Understand customer behavior patterns
        4. Identify market risks and threats
        5. Suggest positioning strategies
        6. Provide actionable market intelligence
        
        Always provide data-driven insights, identify key trends, and suggest actionable strategies.
        Be specific, analytical, and strategic in your research findings."""
    
    def process(self, research_type: str, topic: str, user_id: int, 
                additional_context: Optional[Dict] = None) -> Dict:
        """
        Main entry point - conducts market research
        
        Args:
            research_type (str): Type of research (market_trend, competitor, customer_behavior, opportunity, threat)
            topic (str): Research topic/question
            user_id (int): User ID for storing research
            additional_context (Dict): Optional context (competitor names, industry, etc.)
            
        Returns:
            Dict: Research findings with insights
        """
        self.log_action("Conducting market research", {
            "type": research_type,
            "topic": topic[:100]
        })
        
        # Generate research insights using AI
        research_findings = self._conduct_research(research_type, topic, additional_context)
        
        # Store research in database
        try:
            user = User.objects.get(id=user_id)
            market_research = MarketResearch.objects.create(
                research_type=research_type,
                topic=topic,
                findings=research_findings.get('findings', {}),
                insights=research_findings.get('insights', ''),
                source_urls=research_findings.get('source_urls', []),
                created_by=user
            )
            
            research_id = market_research.id
        except User.DoesNotExist:
            research_id = None
            self.log_action("Warning: User not found, research not saved", {"user_id": user_id})
        
        return {
            'success': True,
            'research_id': research_id,
            'research_type': research_type,
            'topic': topic,
            'findings': research_findings.get('findings', {}),
            'insights': research_findings.get('insights', ''),
            'opportunities': research_findings.get('opportunities', []),
            'risks': research_findings.get('risks', []),
            'recommendations': research_findings.get('recommendations', []),
            'source_urls': research_findings.get('source_urls', [])
        }
    
    def _conduct_research(self, research_type: str, topic: str, 
                         additional_context: Optional[Dict] = None) -> Dict:
        """
        Conduct research using AI - analyzes market, competitors, trends, etc.
        
        Args:
            research_type (str): Type of research
            topic (str): Research topic
            additional_context (Dict): Additional context (competitors, industry, etc.)
            
        Returns:
            Dict: Structured research findings
        """
        # Build research prompt based on type
        prompt = self._build_research_prompt(research_type, topic, additional_context)
        
        # Get AI-generated research
        try:
            research_response = self._call_llm_for_reasoning(
                prompt,
                self.system_prompt,
                temperature=0.5,  # Slightly higher for creative insights
                max_tokens=2000
            )
        except Exception as e:
            self.log_action("Error generating research", {"error": str(e)})
            research_response = f"Research analysis encountered an error: {str(e)}"
        
        # Parse and structure findings
        findings = self._parse_research_response(research_type, research_response, additional_context)
        
        return findings
    
    def _build_research_prompt(self, research_type: str, topic: str, 
                               additional_context: Optional[Dict] = None) -> str:
        """Build research prompt based on type"""
        
        base_prompt = f"Research Topic: {topic}\n\n"
        
        if additional_context:
            context_str = "\n=== IMPORTANT: ADDITIONAL CONTEXT PROVIDED ===\n"
            context_str += "You MUST analyze and reference the following specific context in your research:\n\n"
            
            # Handle competitors (both singular and plural)
            competitors = None
            if 'competitors' in additional_context:
                competitors = additional_context['competitors']
            elif 'competitor' in additional_context:
                competitors = additional_context['competitor']
            
            if competitors:
                if isinstance(competitors, list):
                    competitor_list = ', '.join(str(c) for c in competitors)
                    competitor_count = len(competitors)
                else:
                    competitor_list = str(competitors)
                    competitor_count = 1
                
                context_str += f"🔍 SPECIFIC COMPETITORS/WEBSITES PROVIDED ({competitor_count} total):\n"
                if isinstance(competitors, list):
                    for i, comp in enumerate(competitors, 1):
                        context_str += f"   {i}. {comp}\n"
                else:
                    context_str += f"   1. {competitors}\n"
                context_str += "\n"
                context_str += "⚠️ CRITICAL REQUIREMENTS FOR YOUR ANALYSIS:\n"
                context_str += "   1. You MUST analyze EACH competitor/website individually\n"
                context_str += "   2. You MUST provide direct comparisons between these specific competitors\n"
                context_str += "   3. Your analysis should be SPECIFIC to these competitors, not generic market analysis\n"
                context_str += "   4. Structure your response clearly: Individual Analysis → Direct Comparison → Insights\n"
                context_str += "   5. Use clear headers and bullet points - make it EASY TO READ and UNDERSTAND\n\n"
            
            # Handle other known fields
            if 'industry' in additional_context:
                context_str += f"🏭 Industry Context: {additional_context['industry']}\n\n"
            if 'geographic_region' in additional_context:
                context_str += f"🌍 Geographic Region: {additional_context['geographic_region']}\n\n"
            
            # Handle any other context fields dynamically
            known_fields = {'competitors', 'competitor', 'industry', 'geographic_region'}
            for key, value in additional_context.items():
                if key not in known_fields:
                    if isinstance(value, (list, dict)):
                        context_str += f"📋 {key.replace('_', ' ').title()}: {json.dumps(value, indent=2)}\n\n"
                    else:
                        context_str += f"📋 {key.replace('_', ' ').title()}: {value}\n\n"
            
            context_str += "=== END OF ADDITIONAL CONTEXT ===\n\n"
            context_str += "📌 FORMATTING REQUIREMENTS:\n"
            context_str += "   - Use clear section headers with ## or ### markdown formatting\n"
            context_str += "   - Use markdown tables for comparisons (use | and - to create tables)\n"
            context_str += "   - Use bullet points (• or -) for lists\n"
            context_str += "   - Use bold (**text**) for emphasis on key points\n"
            context_str += "   - Use horizontal dividers (---) between major sections\n"
            context_str += "   - Add a CONCLUSION/SUMMARY section at the end summarizing key findings\n"
            context_str += "   - Keep paragraphs short (2-3 sentences max)\n"
            context_str += "   - Make comparisons explicit using tables or side-by-side formatting\n"
            context_str += "   - Prioritize clarity and readability over length\n\n"
            
            base_prompt += context_str
        
        if research_type == 'market_trend':
            # Check if specific competitors were provided
            has_specific_competitors = additional_context and ('competitors' in additional_context or 'competitor' in additional_context)
            
            if has_specific_competitors:
                prompt = f"""{base_prompt}
📈 MARKET TREND ANALYSIS INSTRUCTIONS:

You have been provided with SPECIFIC competitor websites. Analyze market trends in the context of these competitors.

---

## 📊 SECTION 1: MARKET TRENDS AFFECTING PROVIDED COMPETITORS

Create a MARKDOWN TABLE showing how trends affect each competitor:

| Market Trend | Impact on Competitor 1 | Impact on Competitor 2 | Trend Favoring |
|-------------|----------------------|----------------------|----------------|
| [Trend 1] | [Impact] | [Impact] | [Which competitor] |
| [Trend 2] | [Impact] | [Impact] | [Which competitor] |
| [Trend 3] | [Impact] | [Impact] | [Which competitor] |

**Trend Analysis:**
• **Trend 1**: [How it impacts competitor landscape]
• **Trend 2**: [How it impacts competitor landscape]
• **Trend 3**: [How it impacts competitor landscape]

**Competitors Best Positioned for Trends:**
• **Competitor 1**: [Which trends favor them and why]
• **Competitor 2**: [Which trends favor them and why]

---

## 🌐 SECTION 2: CURRENT & EMERGING MARKET TRENDS

**Current Market Trends:**
• **[Trend Name]**: [Description and significance]
• **[Trend Name]**: [Description and significance]
• **[Trend Name]**: [Description and significance]

**Emerging Trends & Opportunities:**
• **[Emerging Trend]**: [Description and potential impact]
• **[Emerging Trend]**: [Description and potential impact]

**Market Size & Growth Potential:**
• Current Market Size: [Estimate]
• Growth Rate: [Percentage or description]
• Growth Potential: [High/Medium/Low and reasoning]

---

## 🎯 SECTION 3: MARKET DRIVERS & PREDICTIONS

**Key Market Drivers:**
Create a table or list:

| Driver | Impact | Timeframe |
|--------|--------|-----------|
| [Driver 1] | [Impact description] | [Short/Medium/Long term] |
| [Driver 2] | [Impact description] | [Short/Medium/Long term] |

**Future Market Predictions:**
• **Short-term (6-12 months)**: [Predictions]
• **Medium-term (1-2 years)**: [Predictions]
• **Long-term (3+ years)**: [Predictions]

**How Trends Affect Competitive Positioning:**
• [Analysis of competitive dynamics]
• [How positioning should adapt]

---

## 💡 SECTION 4: ACTIONABLE MARKETING STRATEGY INSIGHTS

Based on trends and competitor analysis:

1. **Marketing Strategy Insight 1**: [Recommendation] - [Rationale based on trends]
2. **Marketing Strategy Insight 2**: [Recommendation] - [Rationale based on trends]
3. **Marketing Strategy Insight 3**: [Recommendation] - [Rationale based on trends]

**Trend-Based Opportunities:**
• [Opportunity 1]: [How to leverage trend]
• [Opportunity 2]: [How to leverage trend]

---

## 📝 CONCLUSION & SUMMARY

Provide a concise summary (2-3 paragraphs):
• Most significant market trends affecting the industry
• How trends are impacting the specific competitors analyzed
• Top 2-3 marketing strategy recommendations based on trends
• Clear strategic takeaway

---

⚠️ FORMATTING: Use markdown tables for trend comparisons, bullet points, section headers (##), and dividers (---). Include CONCLUSION section.

🚨 **CRITICAL**: The CONCLUSION section MUST be the ABSOLUTE LAST section. Do NOT add any content, lists, sections, or information after the CONCLUSION ends. Your response must end immediately after the conclusion summary."""
            else:
                prompt = f"""{base_prompt}
---

## 📈 MARKET TREND ANALYSIS

### Current Market Trends
• **Trend 1**: [Description and significance]
• **Trend 2**: [Description and significance]
• **Trend 3**: [Description and significance]

### Emerging Trends & Opportunities
• [Emerging trend 1]: [Description and potential]
• [Emerging trend 2]: [Description and potential]

### Market Size & Growth Potential
• **Current Market Size**: [Estimate]
• **Growth Rate**: [Percentage or description]
• **Growth Potential**: [High/Medium/Low]

### Key Market Drivers

| Driver | Impact | Timeframe |
|--------|--------|-----------|
| [Driver 1] | [Impact] | Short/Med/Long term |
| [Driver 2] | [Impact] | Short/Med/Long term |

### Future Market Predictions
• **Short-term (6-12 months)**: [Predictions]
• **Medium-term (1-2 years)**: [Predictions]
• **Long-term (3+ years)**: [Predictions]

### Actionable Marketing Strategy Insights
1. **[Insight 1]**: [Recommendation based on trends]
2. **[Insight 2]**: [Recommendation based on trends]
3. **[Insight 3]**: [Recommendation based on trends]

---

## 📝 CONCLUSION & SUMMARY

Provide a concise summary (2-3 paragraphs) of key trends and strategic recommendations.

---

⚠️ FORMATTING: Use markdown tables, bullet points, section headers (##), and dividers (---). Include CONCLUSION section.

🚨 **CRITICAL**: The CONCLUSION section MUST be the ABSOLUTE LAST section. Do NOT add any content, lists, sections, or information after the CONCLUSION ends. Your response must end immediately after the conclusion summary."""
        
        elif research_type == 'competitor':
            # Check if specific competitors were provided
            has_specific_competitors = additional_context and ('competitors' in additional_context or 'competitor' in additional_context)
            
            if has_specific_competitors:
                # Structured format for specific competitor analysis
                prompt = f"""{base_prompt}
🔍 COMPETITIVE ANALYSIS INSTRUCTIONS:

You have been provided with SPECIFIC competitor websites to analyze. Your response MUST follow this exact structure with PROPER FORMATTING:

---

## 📊 SECTION 1: COMPETITOR-BY-COMPETITOR ANALYSIS

For EACH competitor website provided, analyze using this structure:

### [Competitor Name/URL]
**Website Overview:**
[Brief description of main focus/positioning]

**Key Features:**
• Feature 1
• Feature 2
• Feature 3

**Pricing Model:**
[How they price their services]

**Target Audience:**
[Who they target]

**Strengths:**
• Strength 1
• Strength 2

**Weaknesses:**
• Weakness 1
• Weakness 2

---

## 🔄 SECTION 2: DIRECT COMPARISON

Create a MARKDOWN TABLE comparing the competitors side-by-side:

| Aspect | Competitor 1 | Competitor 2 | Winner/Notes |
|--------|-------------|-------------|--------------|
| Pricing | [Info] | [Info] | [Comparison] |
| Key Features | [Info] | [Info] | [Comparison] |
| Target Market | [Info] | [Info] | [Comparison] |
| Strengths | [Info] | [Info] | [Comparison] |
| Weaknesses | [Info] | [Info] | [Comparison] |
| Market Position | [Info] | [Info] | [Comparison] |

**Key Differences:**
• [Difference 1]
• [Difference 2]
• [Difference 3]

**Which Competitor is Stronger In:**
• **Competitor 1**: [Areas where they excel]
• **Competitor 2**: [Areas where they excel]

---

## 💡 SECTION 3: KEY INSIGHTS & OPPORTUNITIES

**Market Gaps Identified:**
• Gap 1: [Description]
• Gap 2: [Description]

**What's Working:**
• [Strategy/Feature that works well]
• [Strategy/Feature that works well]

**What's Not Working:**
• [Strategy/Feature that's weak]
• [Strategy/Feature that's weak]

**Opportunities:**
• Opportunity 1: [Description and potential]
• Opportunity 2: [Description and potential]

---

## 🎯 SECTION 4: RECOMMENDATIONS

Provide 3-5 clear, actionable recommendations:

1. **Recommendation 1**: [What to do] - [Why and expected impact]
2. **Recommendation 2**: [What to do] - [Why and expected impact]
3. **Recommendation 3**: [What to do] - [Why and expected impact]

---

## 📝 CONCLUSION & SUMMARY

Provide a concise summary (2-3 paragraphs) that:
• Summarizes the key findings from your analysis
• Highlights the most important competitive insights
• Emphasizes the top 2-3 actionable recommendations
• Provides a clear takeaway for decision-making

---

⚠️ FORMATTING REQUIREMENTS:

🚨 **CRITICAL**: The CONCLUSION section MUST be the ABSOLUTE LAST section. Do NOT add any content, lists, sections, or information after the CONCLUSION ends. Your response must end immediately after the conclusion summary.
- Use markdown tables (| Column | Column |) for comparisons
- Use ## for major sections, ### for subsections
- Use bullet points (•) for lists
- Use **bold** for emphasis
- Use --- for section dividers
- Keep paragraphs SHORT (2-3 sentences)
- Include the CONCLUSION section at the end
- Make it VISUALLY EASY to scan and understand"""
            else:
                # Generic competitor analysis when no specific competitors provided
                prompt = f"""{base_prompt}
---

## 🔍 COMPETITIVE ANALYSIS

Conduct comprehensive competitive analysis following this structure:

### Main Competitors
• [Competitor 1]: [Brief description]
• [Competitor 2]: [Brief description]
• [Competitor 3]: [Brief description]

### Competitor Strategies & Positioning
Create a comparison table:

| Competitor | Strategy | Positioning | Market Approach |
|-----------|----------|-------------|----------------|
| [Name] | [Strategy] | [Positioning] | [Approach] |
| [Name] | [Strategy] | [Positioning] | [Approach] |

### Competitive Strengths & Weaknesses
• **Strengths**: [Key competitive advantages]
• **Weaknesses**: [Key competitive disadvantages]

### Market Positioning & Differentiation
• [Positioning strategy 1]
• [Positioning strategy 2]

### Competitive Opportunities & Gaps
• Opportunity 1: [Description]
• Opportunity 2: [Description]

### Recommended Competitive Positioning Strategies
1. **[Strategy 1]**: [Description and rationale]
2. **[Strategy 2]**: [Description and rationale]
3. **[Strategy 3]**: [Description and rationale]

---

## 📝 CONCLUSION & SUMMARY

Provide a concise summary (2-3 paragraphs) of key findings and recommendations.

---

⚠️ FORMATTING: Use markdown tables, bullet points, section headers (##), and dividers (---). Include CONCLUSION section.

🚨 **CRITICAL**: The CONCLUSION section MUST be the ABSOLUTE LAST section. Do NOT add any content, lists, sections, or information after the CONCLUSION ends. Your response must end immediately after the conclusion summary."""
        
        elif research_type == 'customer_behavior':
            # Check if specific competitors were provided
            has_specific_competitors = additional_context and ('competitors' in additional_context or 'competitor' in additional_context)
            
            if has_specific_competitors:
                prompt = f"""{base_prompt}
👥 CUSTOMER BEHAVIOR ANALYSIS INSTRUCTIONS:

You have been provided with SPECIFIC competitor websites. Analyze customer behavior patterns for users of these specific platforms.

---

## 👤 SECTION 1: CUSTOMER BEHAVIOR ANALYSIS FOR PROVIDED COMPETITORS

For EACH competitor website, analyze:

### [Competitor Name/URL]
**Customer Segments:**
• [Segment 1]: [Description]
• [Segment 2]: [Description]

**Buying Patterns & Preferences:**
• Pattern 1: [Description]
• Pattern 2: [Description]

**Pain Points Addressed:**
• [Pain point 1]
• [Pain point 2]

**Customer Interaction:**
• [How customers interact with platform]

---

## 🔄 SECTION 2: COMPARATIVE CUSTOMER BEHAVIOR

Create a MARKDOWN TABLE comparing customer behavior:

| Behavior Aspect | Competitor 1 | Competitor 2 | Insights |
|----------------|-------------|-------------|----------|
| Primary Customer Segment | [Info] | [Info] | [Comparison] |
| Buying Pattern | [Info] | [Info] | [Comparison] |
| Engagement Level | [Info] | [Info] | [Comparison] |
| Pain Points Addressed | [Info] | [Info] | [Comparison] |
| Customer Loyalty | [Info] | [Info] | [Comparison] |

**Key Behavioral Differences:**
• **Competitor 1 customers**: [Behavior characteristics]
• **Competitor 2 customers**: [Behavior characteristics]

**Which Platform's Customers Are More Engaged:**
[Analysis and reasoning]

---

## 💡 SECTION 3: KEY INSIGHTS

**Customer Segments & Personas:**
[Detailed personas specific to these platforms]

**Common Buying Behaviors:**
• [Behavior pattern 1]
• [Behavior pattern 2]
• [Behavior pattern 3]

**Customer Pain Points:**
• [Pain point 1 and how it's addressed/not addressed]
• [Pain point 2 and how it's addressed/not addressed]

**Customer Journey Insights:**
• Awareness: [How customers discover these platforms]
• Consideration: [Decision factors]
• Purchase: [Purchase triggers]
• Retention: [What keeps customers]

---

## 📢 SECTION 4: MARKETING MESSAGING RECOMMENDATIONS

Based on customer behavior analysis:

1. **Messaging Strategy 1**: [Recommendation] - [Rationale based on behavior]
2. **Messaging Strategy 2**: [Recommendation] - [Rationale based on behavior]
3. **Messaging Strategy 3**: [Recommendation] - [Rationale based on behavior]

---

## 📝 CONCLUSION & SUMMARY

Provide a concise summary (2-3 paragraphs):
• Key customer behavior insights from the analysis
• Most important differences between competitor customer bases
• Top 2-3 marketing messaging recommendations
• Clear takeaway for marketing strategy

---

⚠️ FORMATTING: Use markdown tables, bullet points, section headers (##), and dividers (---). Include CONCLUSION section.

🚨 **CRITICAL**: The CONCLUSION section MUST be the ABSOLUTE LAST section. Do NOT add any content, lists, sections, or information after the CONCLUSION ends. Your response must end immediately after the conclusion summary."""
            else:
                prompt = f"""{base_prompt}
---

## 👥 CUSTOMER BEHAVIOR ANALYSIS

### Customer Segments & Personas
• **Segment 1**: [Description]
• **Segment 2**: [Description]

### Buying Behaviors & Patterns
• Pattern 1: [Description]
• Pattern 2: [Description]
• Pattern 3: [Description]

### Customer Pain Points & Needs
• [Pain point 1]
• [Pain point 2]
• [Pain point 3]

### Customer Journey Insights
• **Awareness**: [Insights]
• **Consideration**: [Insights]
• **Purchase**: [Insights]
• **Retention**: [Insights]

### Behavioral Trends
• [Trend 1]
• [Trend 2]
• [Trend 3]

### Marketing Messaging Recommendations
1. **[Recommendation 1]**: [Description]
2. **[Recommendation 2]**: [Description]
3. **[Recommendation 3]**: [Description]

---

## 📝 CONCLUSION & SUMMARY

Provide a concise summary (2-3 paragraphs) of key customer behavior insights and recommendations.

---

⚠️ FORMATTING: Use bullet points, section headers (##), and dividers (---). Include CONCLUSION section.

🚨 **CRITICAL**: The CONCLUSION section MUST be the ABSOLUTE LAST section. Do NOT add any content, lists, sections, or information after the CONCLUSION ends. Your response must end immediately after the conclusion summary."""
        
        elif research_type == 'opportunity':
            # Check if specific competitors were provided
            has_specific_competitors = additional_context and ('competitors' in additional_context or 'competitor' in additional_context)
            
            if has_specific_competitors:
                prompt = f"""{base_prompt}
💡 OPPORTUNITY ANALYSIS INSTRUCTIONS:

You have been provided with SPECIFIC competitor websites. Identify opportunities by analyzing gaps and weaknesses in these competitors.

---

## 🔍 SECTION 1: OPPORTUNITIES FROM COMPETITOR ANALYSIS

Based on the provided competitors, identify gaps for EACH competitor:

### [Competitor Name/URL]
**Gaps in Offerings:**
• [Gap 1]: [Description and opportunity]
• [Gap 2]: [Description and opportunity]

**Unaddressed Customer Needs:**
• [Need 1]: [How it's not being met]
• [Need 2]: [How it's not being met]

**Missing Features/Services:**
• [Feature 1]: [Opportunity it presents]
• [Feature 2]: [Opportunity it presents]

**Pricing/Positioning Opportunities:**
• [Opportunity 1]
• [Opportunity 2]

---

## 📊 SECTION 2: MARKET GAPS & UNMET NEEDS

Create a MARKDOWN TABLE summarizing opportunities:

| Opportunity Type | Gap/Need | Opportunity | Potential Impact |
|-----------------|----------|-------------|------------------|
| Feature Gap | [Gap description] | [Opportunity] | High/Med/Low |
| Service Gap | [Gap description] | [Opportunity] | High/Med/Low |
| Pricing Gap | [Gap description] | [Opportunity] | High/Med/Low |
| Positioning Gap | [Gap description] | [Opportunity] | High/Med/Low |

**Key Unmet Needs:**
• [Need 1]: [Why it's unmet and opportunity]
• [Need 2]: [Why it's unmet and opportunity]

**Differentiation Opportunities:**
• [Opportunity 1]: [How to differentiate]
• [Opportunity 2]: [How to differentiate]

---

## 📈 SECTION 3: GROWTH OPPORTUNITIES

For each major opportunity:

### Opportunity 1: [Name]
- **Growth Potential**: [High/Medium/Low]
- **Estimated ROI**: [Estimate or range]
- **Feasibility**: [Easy/Medium/Difficult]
- **Entry Strategy**: [How to pursue this]
- **Required Resources**: [What's needed]

### Opportunity 2: [Name]
- **Growth Potential**: [High/Medium/Low]
- **Estimated ROI**: [Estimate or range]
- **Feasibility**: [Easy/Medium/Difficult]
- **Entry Strategy**: [How to pursue this]
- **Required Resources**: [What's needed]

---

## 🎯 SECTION 4: PRIORITIZED RECOMMENDATIONS

Rank opportunities by priority:

**🔥 HIGH PRIORITY (Immediate Action)**
1. **[Opportunity Name]**: [Why high priority]
   - Action: [What to do]
   - Expected Impact: [Expected results]

2. **[Opportunity Name]**: [Why high priority]
   - Action: [What to do]
   - Expected Impact: [Expected results]

**⭐ MEDIUM PRIORITY (Short-term)**
3. **[Opportunity Name]**: [Action items]

4. **[Opportunity Name]**: [Action items]

**💡 LOW PRIORITY (Long-term)**
5. **[Opportunity Name]**: [Action items]

---

## 📝 CONCLUSION & SUMMARY

Provide a concise summary (2-3 paragraphs):
• Top 3 opportunities with highest potential
• Key gaps and unmet needs identified
• Recommended priority order for pursuing opportunities
• Clear action plan takeaway

---

⚠️ FORMATTING: Use markdown tables, bullet points, section headers (##), and dividers (---). Include CONCLUSION section.

🚨 **CRITICAL**: The CONCLUSION section MUST be the ABSOLUTE LAST section. Do NOT add any content, lists, sections, or information after the CONCLUSION ends. Your response must end immediately after the conclusion summary."""
            else:
                prompt = f"""{base_prompt}
---

## 💡 OPPORTUNITY ANALYSIS

### Market Opportunities

Create an opportunities table:

| Opportunity | Market Gap/Need | Growth Potential | Estimated ROI | Feasibility | Priority |
|------------|----------------|------------------|---------------|-------------|----------|
| [Opp 1] | [Gap] | High/Med/Low | [Estimate] | Easy/Med/Diff | High/Med/Low |
| [Opp 2] | [Gap] | High/Med/Low | [Estimate] | Easy/Med/Diff | High/Med/Low |

### Market Gaps & Unmet Needs
• Gap 1: [Description]
• Gap 2: [Description]
• Unmet Need 1: [Description]

### Entry Strategies
• **For [Opportunity 1]**: [Strategy description]
• **For [Opportunity 2]**: [Strategy description]

### Required Resources & Capabilities
• [Resource 1]: [Description]
• [Capability 1]: [Description]

### Prioritized Opportunity Recommendations
**🔥 HIGH PRIORITY**
1. **[Opportunity]**: [Action items and rationale]

**⭐ MEDIUM PRIORITY**
2. **[Opportunity]**: [Action items and rationale]

**💡 LOW PRIORITY**
3. **[Opportunity]**: [Action items and rationale]

---

## 📝 CONCLUSION & SUMMARY

Provide a concise summary (2-3 paragraphs) of top opportunities and recommended priorities.

---

⚠️ FORMATTING: Use markdown tables, bullet points, section headers (##), and dividers (---). Include CONCLUSION section.

🚨 **CRITICAL**: The CONCLUSION section MUST be the ABSOLUTE LAST section. Do NOT add any content, lists, sections, or information after the CONCLUSION ends. Your response must end immediately after the conclusion summary."""
        
        elif research_type == 'threat':
            # Check if specific competitors were provided
            has_specific_competitors = additional_context and ('competitors' in additional_context or 'competitor' in additional_context)
            
            if has_specific_competitors:
                prompt = f"""{base_prompt}
⚠️ RISK & THREAT ANALYSIS INSTRUCTIONS:

You have been provided with SPECIFIC competitor websites. Analyze threats and risks in relation to these specific competitors and the overall market.

---

## 🎯 SECTION 1: THREATS FROM SPECIFIC COMPETITORS

For EACH competitor provided:

### [Competitor Name/URL]
**Competitive Threats Posed:**
• [Threat 1]: [Description and impact]
• [Threat 2]: [Description and impact]

**Competitive Advantages:**
• [Advantage 1]: [How it threatens others]
• [Advantage 2]: [How it threatens others]

**Market Position Strength:**
[Assessment of their market position and threat level]

---

## 📊 SECTION 2: COMPARATIVE THREAT ASSESSMENT

Create a MARKDOWN TABLE comparing threat levels:

| Competitor | Threat Level | Key Threats | Market Position Risk | Overall Risk Score |
|-----------|-------------|-------------|---------------------|-------------------|
| Competitor 1 | High/Medium/Low | [Threats] | [Risk level] | [Score] |
| Competitor 2 | High/Medium/Low | [Threats] | [Risk level] | [Score] |

**Biggest Threat:**
**Winner**: [Which competitor] - [Why they pose the biggest threat]

**Market Share & Positioning Risks:**
• [Risk 1]
• [Risk 2]

---

## 🌍 SECTION 3: GENERAL MARKET THREATS

Create a MARKDOWN TABLE for market threats:

| Threat | Severity | Probability | Impact on Business/Marketing | Priority |
|--------|----------|------------|------------------------------|----------|
| [Threat 1] | High/Med/Low | High/Med/Low | [Impact description] | High/Med/Low |
| [Threat 2] | High/Med/Low | High/Med/Low | [Impact description] | High/Med/Low |
| [Threat 3] | High/Med/Low | High/Med/Low | [Impact description] | High/Med/Low |

**Top Priority Threats:**
1. **[Threat Name]**: [Why it's a priority]
2. **[Threat Name]**: [Why it's a priority]

---

## 🛡️ SECTION 4: MITIGATION STRATEGIES

For each high-priority threat, provide mitigation:

1. **Mitigation for [Threat Name]**:
   - **Action**: [What to do]
   - **Expected Impact**: [How it reduces risk]
   - **Timeline**: [When to implement]

2. **Mitigation for [Threat Name]**:
   - **Action**: [What to do]
   - **Expected Impact**: [How it reduces risk]
   - **Timeline**: [When to implement]

---

## ⚠️ SECTION 5: EARLY WARNING INDICATORS & RECOMMENDATIONS

**Early Warning Indicators to Monitor:**
• [Indicator 1]: [What it signals]
• [Indicator 2]: [What it signals]
• [Indicator 3]: [What it signals]

**Risk Management Recommendations:**
1. [Recommendation 1]
2. [Recommendation 2]
3. [Recommendation 3]

---

## 📝 CONCLUSION & SUMMARY

Provide a concise summary (2-3 paragraphs):
• Most critical threats identified (from competitors and market)
• Top 3 threats requiring immediate attention
• Key mitigation strategies to prioritize
• Clear risk management takeaway

---

⚠️ FORMATTING: Use markdown tables for threat comparisons, bullet points, section headers (##), and dividers (---). Include CONCLUSION section."""
            else:
                prompt = f"""{base_prompt}
---

## ⚠️ RISK & THREAT ANALYSIS

### Current & Emerging Threats

Create a threat assessment table:

| Threat | Severity | Probability | Impact on Business/Marketing | Priority |
|--------|----------|------------|------------------------------|----------|
| [Threat 1] | High/Med/Low | High/Med/Low | [Impact] | High/Med/Low |
| [Threat 2] | High/Med/Low | High/Med/Low | [Impact] | High/Med/Low |
| [Threat 3] | High/Med/Low | High/Med/Low | [Impact] | High/Med/Low |

### Top Priority Threats
1. **[Threat Name]**: [Why it's a priority]
2. **[Threat Name]**: [Why it's a priority]

### Mitigation Strategies
1. **For [Threat Name]**:
   - Action: [What to do]
   - Expected Impact: [How it reduces risk]
2. **For [Threat Name]**:
   - Action: [What to do]
   - Expected Impact: [How it reduces risk]

### Early Warning Indicators
• [Indicator 1]: [What it signals]
• [Indicator 2]: [What it signals]

### Risk Management Recommendations
1. [Recommendation 1]
2. [Recommendation 2]
3. [Recommendation 3]

---

## 📝 CONCLUSION & SUMMARY

Provide a concise summary (2-3 paragraphs) of critical threats and key mitigation strategies.

---

⚠️ FORMATTING: Use markdown tables, bullet points, section headers (##), and dividers (---). Include CONCLUSION section.

🚨 **CRITICAL**: The CONCLUSION section MUST be the ABSOLUTE LAST section. Do NOT add any content, lists, sections, or information after the CONCLUSION ends. Your response must end immediately after the conclusion summary."""
        
        else:
            # Generic research
            prompt = f"""{base_prompt}
---

## 🔍 COMPREHENSIVE MARKET RESEARCH

### Key Findings & Insights
• Finding 1: [Description]
• Finding 2: [Description]
• Finding 3: [Description]

### Market Analysis
• [Analysis point 1]
• [Analysis point 2]
• [Analysis point 3]

### Opportunities & Threats

**Opportunities:**
• [Opportunity 1]
• [Opportunity 2]

**Threats:**
• [Threat 1]
• [Threat 2]

### Strategic Recommendations
1. **[Recommendation 1]**: [Description and rationale]
2. **[Recommendation 2]**: [Description and rationale]
3. **[Recommendation 3]**: [Description and rationale]

### Actionable Next Steps
• Step 1: [Action item]
• Step 2: [Action item]
• Step 3: [Action item]

---

## 📝 CONCLUSION & SUMMARY

Provide a concise summary (2-3 paragraphs) of key findings, opportunities, threats, and recommended actions.

---

⚠️ FORMATTING: Use bullet points, section headers (##), and dividers (---). Include CONCLUSION section.

🚨 **CRITICAL**: The CONCLUSION section MUST be the ABSOLUTE LAST section. Do NOT add any content, lists, sections, or information after the CONCLUSION ends. Your response must end immediately after the conclusion summary."""
        
        return prompt
    
    def _parse_research_response(self, research_type: str, response: str, 
                                 additional_context: Optional[Dict] = None) -> Dict:
        """
        Parse AI research response into structured findings
        
        Args:
            research_type (str): Type of research
            response (str): AI-generated research text
            additional_context (Dict): Additional context
            
        Returns:
            Dict: Structured findings
        """
        # Extract key information from response
        findings = {
            'raw_response': response,
            'research_type': research_type,
            'analyzed_at': datetime.now().isoformat()
        }
        
        # Use the full formatted response as insights (already includes all sections, conclusion, etc.)
        # Trim response to end at conclusion section to avoid duplicate content after conclusion
        insights = response
        
        # Find the conclusion section and ensure we stop there (or shortly after if conclusion content exists)
        conclusion_markers = [
            '## 📝 CONCLUSION & SUMMARY',
            '## 📝 CONCLUSION',
            '## CONCLUSION & SUMMARY',
            '## CONCLUSION'
        ]
        
        for marker in conclusion_markers:
            if marker in insights:
                # Find the position of the conclusion marker
                conclusion_index = insights.find(marker)
                if conclusion_index != -1:
                    # Extract everything from start to conclusion section
                    # Then look for where conclusion ends - it should be the last section
                    conclusion_section = insights[conclusion_index:]
                    lines = conclusion_section.split('\n')
                    
                    # Find where conclusion content ends (look for next major section or excessive content)
                    # Conclusion should typically be 2-4 paragraphs, so limit to ~1000 chars after marker
                    # or until we hit another ## section (not ###)
                    end_index = len(conclusion_section)
                    
                    for i, line in enumerate(lines):
                        # Skip the conclusion header and a few lines after it
                        if i > 10:
                            line_stripped = line.strip()
                            # If we hit another major section header, stop there
                            if line_stripped.startswith('## ') and not line_stripped.startswith('### '):
                                end_index = len('\n'.join(lines[:i]))
                                break
                            # If we've gone too far (more than ~1500 chars), stop
                            if len('\n'.join(lines[:i])) > 1500:
                                end_index = len('\n'.join(lines[:i-5]))  # Back up a few lines
                                break
                    
                    # Trim to conclusion only
                    insights = insights[:conclusion_index] + conclusion_section[:end_index].rstrip()
                    break
        
        # Return empty arrays for backwards compatibility, but these won't be displayed
        # since the frontend uses the insights field which contains the full formatted response
        opportunities = []
        risks = []
        recommendations = []
        
        return {
            'findings': findings,
            'insights': insights,
            'opportunities': opportunities[:10],  # Limit to top 10
            'risks': risks[:10],  # Limit to top 10
            'recommendations': recommendations[:10],  # Limit to top 10
            'source_urls': []  # Can be populated if we add web scraping/API integration
        }
    
    def research_market_trends(self, topic: str, user_id: int, 
                              industry: Optional[str] = None) -> Dict:
        """
        Research market trends for a specific topic
        
        Args:
            topic (str): Topic to research (e.g., "AI marketing tools", "e-commerce trends")
            user_id (int): User ID
            industry (str): Optional industry context
            
        Returns:
            Dict: Market trend research findings
        """
        context = {}
        if industry:
            context['industry'] = industry
        
        return self.process('market_trend', topic, user_id, context)
    
    def analyze_competitors(self, topic: str, user_id: int, 
                           competitor_names: Optional[List[str]] = None) -> Dict:
        """
        Analyze competitors for a specific topic/market
        
        Args:
            topic (str): Market/product category to analyze
            user_id (int): User ID
            competitor_names (List[str]): Optional list of specific competitors
            
        Returns:
            Dict: Competitive analysis findings
        """
        context = {}
        if competitor_names:
            context['competitors'] = competitor_names
        
        return self.process('competitor', topic, user_id, context)
    
    def analyze_customer_behavior(self, topic: str, user_id: int,
                                 customer_segments: Optional[List[str]] = None) -> Dict:
        """
        Analyze customer behavior patterns
        
        Args:
            topic (str): Behavior topic (e.g., "purchasing behavior", "product preferences")
            user_id (int): User ID
            customer_segments (List[str]): Optional customer segments
            
        Returns:
            Dict: Customer behavior analysis findings
        """
        context = {}
        if customer_segments:
            context['customer_segments'] = customer_segments
        
        return self.process('customer_behavior', topic, user_id, context)
    
    def identify_opportunities(self, topic: str, user_id: int,
                              market_context: Optional[Dict] = None) -> Dict:
        """
        Identify market opportunities
        
        Args:
            topic (str): Opportunity area to explore
            user_id (int): User ID
            market_context (Dict): Optional market context (industry, region, etc.)
            
        Returns:
            Dict: Opportunity analysis findings
        """
        return self.process('opportunity', topic, user_id, market_context)
    
    def identify_risks(self, topic: str, user_id: int,
                      market_context: Optional[Dict] = None) -> Dict:
        """
        Identify market risks and threats
        
        Args:
            topic (str): Risk area to analyze
            user_id (int): User ID
            market_context (Dict): Optional market context
            
        Returns:
            Dict: Risk analysis findings
        """
        return self.process('threat', topic, user_id, market_context)

