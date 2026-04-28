import React from 'react';
import { Sparkles } from 'lucide-react';

const SDRComingSoon = ({ icon: Icon, title, description, color = '#a855f7' }) => {
  return (
    <div className="flex flex-col items-center justify-center py-24 px-4 text-center">
      {/* Glow ring */}
      <div
        className="relative flex items-center justify-center w-24 h-24 rounded-full mb-6"
        style={{
          background: `radial-gradient(circle, ${color}22 0%, transparent 70%)`,
          boxShadow: `0 0 40px ${color}33`,
          border: `1.5px solid ${color}30`,
        }}
      >
        {/* Inner circle */}
        <div
          className="flex items-center justify-center w-16 h-16 rounded-full"
          style={{ background: `${color}18`, border: `1px solid ${color}40` }}
        >
          <Icon className="h-7 w-7" style={{ color }} />
        </div>
        {/* Sparkle badge */}
        <div
          className="absolute -top-2 -right-2 w-7 h-7 rounded-full flex items-center justify-center"
          style={{ background: 'linear-gradient(135deg, #f43f5e, #a855f7)', boxShadow: '0 0 10px rgba(244,63,94,0.5)' }}
        >
          <Sparkles className="h-3.5 w-3.5 text-white" />
        </div>
      </div>

      {/* Label chip */}
      <span
        className="text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full mb-4"
        style={{ background: 'rgba(244,63,94,0.12)', color: '#f43f5e', border: '1px solid rgba(244,63,94,0.25)' }}
      >
        Coming Soon
      </span>

      <h3 className="text-xl font-bold text-white mb-2">{title}</h3>
      <p className="text-sm text-gray-500 max-w-md leading-relaxed">{description}</p>

      {/* Animated dots */}
      <div className="flex items-center gap-1.5 mt-8">
        {[0, 1, 2].map(i => (
          <div
            key={i}
            className="w-2 h-2 rounded-full"
            style={{
              background: i === 0 ? '#f43f5e' : i === 1 ? '#a855f7' : '#06b6d4',
              animation: `pulse 1.5s ease-in-out ${i * 0.3}s infinite`,
              opacity: 0.7,
            }}
          />
        ))}
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { transform: scale(1); opacity: 0.5; }
          50% { transform: scale(1.4); opacity: 1; }
        }
      `}</style>
    </div>
  );
};

export default SDRComingSoon;
