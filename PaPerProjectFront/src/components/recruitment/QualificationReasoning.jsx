import React, { useState } from 'react';

/**
 * Component to display qualification reasoning in a readable, formatted way
 */
const QualificationReasoning = ({ 
  reasoning, 
  exactMatchedSkills = [],
  relatedMatchedSkills = [],
  missingSkills = [],
  inferredSkills = []
}) => {
  const [expandedSections, setExpandedSections] = useState({});
  
  if (!reasoning) return null;
  
  const toggleExpand = (sectionKey) => {
    setExpandedSections(prev => ({
      ...prev,
      [sectionKey]: !prev[sectionKey]
    }));
  };
  
  // Helper to parse and render expandable skill lists
  const renderExpandableSkills = (line, sectionKey, fullSkillList, hasEmoji) => {
    // Check if line has "(+n more)" pattern
    const morePattern = /\((\+(\d+)\s+more)\)/;
    const match = line.match(morePattern);
    
    if (!match || !fullSkillList || fullSkillList.length === 0) {
      return null; // No expandable content
    }
    
    const isExpanded = expandedSections[sectionKey];
    
    // Extract the part before "(+n more)" and preserve formatting
    const beforeMore = line.substring(0, line.indexOf(match[0]));
    const afterMore = line.substring(line.indexOf(match[0]) + match[0].length);
    
    // Parse bold parts
    const parseBoldParts = (text) => {
      const parts = text.split(/(\*\*.*?\*\*)/g);
      return parts.map((part, pIdx) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return (
            <span key={pIdx} className="font-semibold text-foreground">
              {part.replace(/\*\*/g, '')}
            </span>
          );
        }
        return <span key={pIdx}>{part}</span>;
      });
    };
    
    return (
      <div key={sectionKey} className={hasEmoji ? "flex items-start gap-2" : ""}>
        <div className="flex-1">
          <div className="flex items-start gap-2 flex-wrap">
            {parseBoldParts(beforeMore)}
            {!isExpanded && (
              <button
                onClick={() => toggleExpand(sectionKey)}
                className="text-primary hover:text-primary/80 underline cursor-pointer text-sm font-medium"
              >
                {match[0]}
              </button>
            )}
            {afterMore && <span>{afterMore}</span>}
          </div>
          {isExpanded && (
            <div className="mt-2 ml-4 space-y-1">
              <div className="text-sm text-muted-foreground">
                {fullSkillList.map((skill, idx) => (
                  <span key={idx}>
                    {skill}
                    {idx < fullSkillList.length - 1 && ', '}
                  </span>
                ))}
              </div>
              <button
                onClick={() => toggleExpand(sectionKey)}
                className="text-primary hover:text-primary/80 underline cursor-pointer text-xs mt-1"
              >
                Show less
              </button>
            </div>
          )}
        </div>
      </div>
    );
  };

  // Handle both array and string formats
  const reasoningLines = Array.isArray(reasoning) 
    ? reasoning 
    : (typeof reasoning === 'string' ? reasoning.split('\n').filter(l => l.trim()) : []);

  if (reasoningLines.length === 0) return null;

  return (
    <div>
      <h4 className="font-semibold mb-2">Qualification Reasoning</h4>
      <div className="text-sm text-muted-foreground space-y-1.5 bg-muted/50 p-4 rounded-md border">
        {reasoningLines.map((line, idx) => {
          if (!line || line.trim() === '') {
            return <div key={idx} className="h-2" />; // Empty line spacer
          }

          const trimmedLine = line.trim();
          
          // Section header (starts and ends with **)
          if (trimmedLine.startsWith('**') && trimmedLine.endsWith('**')) {
            return (
              <div key={idx} className="font-semibold text-foreground mt-3 mb-1.5 first:mt-0 text-base">
                {trimmedLine.replace(/\*\*/g, '')}
              </div>
            );
          }

          // Check for emoji indicators
          const hasEmoji = /^[✅⏸️❌🟢🟡🔴💡⚠️🚨📅✓]/.test(trimmedLine);
          const hasBold = line.includes('**');

          // Line with bold text - check for expandable skill lists
          if (hasBold) {
            // Check for skill list patterns
            let fullSkillList = null;
            let sectionKey = null;
            
            if (trimmedLine.includes('**Exact Matches:**')) {
              fullSkillList = exactMatchedSkills;
              sectionKey = `exact-${idx}`;
            } else if (trimmedLine.includes('**Related Matches:**')) {
              fullSkillList = relatedMatchedSkills;
              sectionKey = `related-${idx}`;
            } else if (trimmedLine.includes('**Missing Skills:**')) {
              fullSkillList = missingSkills;
              sectionKey = `missing-${idx}`;
            } else if (trimmedLine.includes('**Inferred Skills:**')) {
              fullSkillList = inferredSkills;
              sectionKey = `inferred-${idx}`;
            } else if (trimmedLine.includes('**Matched Skills:**')) {
              // Fallback for old format - combine exact and related
              fullSkillList = [...exactMatchedSkills, ...relatedMatchedSkills];
              sectionKey = `matched-${idx}`;
            }
            
            // If it's an expandable skill list, render it specially
            if (fullSkillList && fullSkillList.length > 0 && line.includes('(+')) {
              const expandableContent = renderExpandableSkills(line, sectionKey, fullSkillList, hasEmoji);
              if (expandableContent) {
                return expandableContent;
              }
            }
            
            // Regular bold text rendering
            const parts = line.split(/(\*\*.*?\*\*)/g);
            return (
              <div key={idx} className={hasEmoji ? "flex items-start gap-2" : ""}>
                {parts.map((part, pIdx) => {
                  if (part.startsWith('**') && part.endsWith('**')) {
                    return (
                      <span key={pIdx} className="font-semibold text-foreground">
                        {part.replace(/\*\*/g, '')}
                      </span>
                    );
                  }
                  return <span key={pIdx}>{part}</span>;
                })}
              </div>
            );
          }

          // Bullet point (starts with •)
          if (trimmedLine.startsWith('•')) {
            return (
              <div key={idx} className="ml-4 text-muted-foreground flex items-start gap-2">
                <span className="mt-0.5">•</span>
                <span>{trimmedLine.substring(1).trim()}</span>
              </div>
            );
          }

          // Regular line with emoji
          if (hasEmoji) {
            return (
              <div key={idx} className="flex items-start gap-2">
                <span>{line}</span>
              </div>
            );
          }

          // Regular line
          return <div key={idx}>{line}</div>;
        })}
      </div>
    </div>
  );
};

export default QualificationReasoning;
