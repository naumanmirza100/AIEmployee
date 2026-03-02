import React from 'react';

const gridLineOpacity = 0.22;
/** Stronger grid visibility for line/bar/scatter (like pie) */
const gridLineOpacityVisible = 0.42;
/** Graph-paper style: horizontal + vertical grid lines */
const GRID_H = [0, 1, 2, 3, 4, 5];
const GRID_V = [0, 1, 2, 3, 4, 5];
const SimpleBarChart = ({ data, colors, height = 250, title }) => {
  if (!data || Object.keys(data).length === 0) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  }
  const maxValue = Math.max(...Object.values(data), 1);
  const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
  const chartColors = colors || defaultColors;
  const barAreaLeft = 'calc(6rem + 0.75rem)';
  return (
    <div className="w-full space-y-3" style={{ minHeight: `${height}px` }}>
      {title && <h4 className="font-medium text-sm text-foreground mb-4">{title}</h4>}
      <div className="relative w-full">
        {/* Graph-paper grid: horizontal lines (clearly visible) */}
        <div className="absolute top-0 bottom-0 right-0 pointer-events-none flex flex-col justify-between" style={{ left: barAreaLeft }}>
          {GRID_H.map((i) => (
            <div key={`h-${i}`} className="w-full border-t border-border" style={{ opacity: gridLineOpacityVisible }} />
          ))}
        </div>
        {/* Vertical grid lines in bar area (evenly spaced) */}
        <div className="absolute top-0 bottom-0 right-0 pointer-events-none flex" style={{ left: barAreaLeft }}>
          {GRID_V.map((i) => (
            <div key={`v-${i}`} className="flex-1 border-r border-border" style={{ opacity: gridLineOpacityVisible }} />
          ))}
        </div>
        {Object.entries(data).map(([key, value], index) => {
        const percentage = (value / maxValue) * 100;
        return (
          <div key={key} className="flex items-center gap-3 relative z-10">
            <div className="w-24 sm:w-32 text-xs sm:text-sm text-muted-foreground truncate shrink-0" title={key}>{key}</div>
            <div className="flex-1 min-w-0">
              <div className="h-8 bg-muted rounded-md overflow-hidden">
                <div
                  className="h-full flex items-center justify-end pr-2 text-xs font-semibold text-white transition-all duration-500"
                  style={{ width: `${Math.max(percentage, 5)}%`, backgroundColor: chartColors[index % chartColors.length] }}
                >
                  {value > 0 && value}
                </div>
              </div>
            </div>
            <div className="w-12 text-sm font-medium text-right shrink-0">{value}</div>
          </div>
        );
      })}
      </div>
    </div>
  );
};

/** Vertical bar chart: categories on x-axis, bars grow upward. Same data format as horizontal bar. */
const SimpleVerticalBarChart = ({ data, colors, height = 200, title }) => {
  if (!data || Object.keys(data).length === 0) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  }
  const maxValue = Math.max(...Object.values(data), 1);
  const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
  const chartColors = colors || defaultColors;
  const entries = Object.entries(data);
  const barAreaHeight = height * 0.82;
  return (
    <div className="w-full space-y-2">
      {title && <h4 className="font-medium text-sm text-foreground mb-2">{title}</h4>}
      <div className="relative w-full flex items-end justify-around gap-2" style={{ height: `${height}px` }}>
        {/* Graph-paper: horizontal grid lines (clearly visible) */}
        {[20, 40, 60, 80].map((pct) => (
          <div
            key={`h-${pct}`}
            className="absolute left-0 right-0 border-t border-border pointer-events-none"
            style={{ bottom: `${pct}%`, opacity: gridLineOpacityVisible }}
          />
        ))}
        {/* Vertical grid lines */}
        {[20, 40, 60, 80].map((pct) => (
          <div
            key={`v-${pct}`}
            className="absolute top-0 bottom-0 w-px border-l border-border pointer-events-none"
            style={{ left: `${pct}%`, opacity: gridLineOpacityVisible }}
          />
        ))}
        {entries.map(([key, value], index) => {
          const barHeightPx = maxValue > 0 ? (value / maxValue) * barAreaHeight : 0;
          const minBarHeight = value > 0 ? Math.max(barHeightPx, 24) : 0;
          return (
            <div key={key} className="flex-1 min-w-0 flex flex-col items-center justify-end gap-1 relative z-10">
              <div className="w-full flex justify-center" style={{ height: `${barAreaHeight}px` }}>
                <div
                  className="w-full max-w-[40px] rounded-t-md flex items-end justify-center"
                  style={{ height: `${barAreaHeight}px` }}
                >
                  <div
                    className="w-full rounded-t text-xs font-semibold text-white flex items-end justify-center pb-0.5"
                    style={{
                      height: `${minBarHeight}px`,
                      minHeight: value > 0 ? '24px' : 0,
                      backgroundColor: chartColors[index % chartColors.length],
                    }}
                    title={`${key}: ${value}`}
                  >
                    {value > 0 && value}
                  </div>
                </div>
              </div>
              <span className="text-[10px] sm:text-xs text-muted-foreground truncate max-w-full text-center" title={key}>{key}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const SimplePieChart = ({ data, colors, title }) => {
  if (!data || Object.keys(data).length === 0) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  }
  const total = Object.values(data).reduce((sum, val) => sum + val, 0);
  if (total === 0) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  }
  const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
  const chartColors = colors || defaultColors;
  let currentAngle = 0;
  const segments = Object.entries(data).map(([key, value], index) => {
    const percentage = (value / total) * 100;
    const angle = (percentage / 100) * 360;
    const startAngle = currentAngle;
    currentAngle += angle;
    return { key, value, percentage: percentage.toFixed(1), startAngle, angle, color: chartColors[index % chartColors.length] };
  });
  return (
    <div className="w-full flex flex-col items-center gap-4">
      {title && <h4 className="font-medium text-sm text-foreground">{title}</h4>}
      <div className="relative w-48 h-48 sm:w-56 sm:h-56">
        <svg width="100%" height="100%" viewBox="0 0 200 200" className="transform -rotate-90">
          {/* Graph-paper style: grid behind pie */}
          <g stroke="currentColor" strokeOpacity={gridLineOpacity * 0.8} strokeWidth="0.5">
            {[25, 50, 75, 100, 125, 150, 175].map((x) => (
              <line key={`v-${x}`} x1={x} y1={0} x2={x} y2={200} />
            ))}
            {[25, 50, 75, 100, 125, 150, 175].map((y) => (
              <line key={`h-${y}`} x1={0} y1={y} x2={200} y2={y} />
            ))}
          </g>
          {segments.map((segment, index) => {
            const largeArcFlag = segment.angle > 180 ? 1 : 0;
            const x1 = 100 + 90 * Math.cos((segment.startAngle * Math.PI) / 180);
            const y1 = 100 + 90 * Math.sin((segment.startAngle * Math.PI) / 180);
            const x2 = 100 + 90 * Math.cos(((segment.startAngle + segment.angle) * Math.PI) / 180);
            const y2 = 100 + 90 * Math.sin(((segment.startAngle + segment.angle) * Math.PI) / 180);
            return (
              <path
                key={index}
                d={`M 100 100 L ${x1} ${y1} A 90 90 0 ${largeArcFlag} 1 ${x2} ${y2} Z`}
                fill={segment.color}
                stroke="rgba(255,255,255,0.9)"
                strokeWidth="2"
              />
            );
          })}
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center">
            <div className="text-2xl font-bold">{total}</div>
            <div className="text-xs text-muted-foreground">Total</div>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 w-full max-w-xs">
        {segments.map((segment, index) => (
          <div key={index} className="flex items-center gap-2 text-xs sm:text-sm">
            <div className="w-3 h-3 rounded shrink-0" style={{ backgroundColor: segment.color }} />
            <span className="truncate flex-1">{segment.key}</span>
            <span className="font-medium shrink-0">{segment.percentage}%</span>
          </div>
        ))}
      </div>
    </div>
  );
};

const SimpleLineChart = ({ data, color = '#3b82f6', height = 200, title }) => {
  if (!data || data.length === 0) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  }
  const values = data.map(d => d.value || d.count || 0);
  const gradientId = `line-grad-${(title || '').replace(/\s/g, '-')}-${height}-${values.length}`;
  const maxValue = Math.max(...values, 1);
  const labels = data.map(d => d.label || d.date || d.month || '');
  const points = values.map((value, index) => {
    const x = (index / (values.length - 1 || 1)) * 100;
    const y = 100 - (value / maxValue) * 80;
    return `${x},${y}`;
  }).join(' ');
  const areaPoints = `0,100 ${points} 100,100`;
  const horizontalLines = [10, 20, 30, 40, 50, 60, 70, 80, 90];
  const verticalLines = [10, 20, 30, 40, 50, 60, 70, 80, 90];
  return (
    <div className="w-full space-y-2">
      {title && <h4 className="font-medium text-sm text-foreground">{title}</h4>}
      <div className="relative w-full" style={{ height: `${height}px` }}>
        <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
          <defs>
            <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.45" />
              <stop offset="100%" stopColor={color} stopOpacity="0" />
            </linearGradient>
          </defs>
          {/* Graph-paper grid (clearly visible like pie) */}
          {horizontalLines.map((y) => (
            <line key={`h-${y}`} x1="0" y1={y} x2="100" y2={y} stroke="currentColor" strokeOpacity={gridLineOpacityVisible} strokeWidth="0.5" />
          ))}
          {verticalLines.map((x) => (
            <line key={`v-${x}`} x1={x} y1="0" x2={x} y2="100" stroke="currentColor" strokeOpacity={gridLineOpacityVisible} strokeWidth="0.5" />
          ))}
          <polygon points={areaPoints} fill={`url(#${gradientId})`} />
          <polyline points={points} fill="none" stroke={color} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
          {values.map((value, index) => {
            const x = (index / (values.length - 1 || 1)) * 100;
            const y = 100 - (value / maxValue) * 80;
            return <circle key={index} cx={x} cy={y} r="2.5" fill={color} stroke="rgba(255,255,255,0.8)" strokeWidth="0.5" />;
          })}
        </svg>
        <div className="absolute bottom-0 left-0 right-0 flex justify-between text-[10px] text-muted-foreground px-1">
          {labels.length <= 7 ? labels.map((label, i) => <span key={i} className="truncate">{label}</span>) : (
            <><span>{labels[0]}</span><span>{labels[Math.floor(labels.length / 2)]}</span><span>{labels[labels.length - 1]}</span></>
          )}
        </div>
      </div>
    </div>
  );
};

const SimpleAreaChart = ({ data, color = '#3b82f6', height = 200, title }) => (
  <SimpleLineChart data={data} color={color} height={height} title={title} />
);

const SimpleScatterPlot = ({ data, color = '#8b5cf6', height = 200, title }) => {
  if (!data || data.length === 0) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  }
  const xValues = data.map(d => d.x || 0);
  const yValues = data.map(d => d.y || 0);
  const maxX = Math.max(...xValues, 1);
  const maxY = Math.max(...yValues, 1);
  const hLines = [10, 20, 30, 40, 50, 60, 70, 80, 90];
  const vLines = [10, 20, 30, 40, 50, 60, 70, 80, 90];
  return (
    <div className="w-full space-y-2">
      {title && <h4 className="font-medium text-sm text-foreground">{title}</h4>}
      <div className="relative w-full border-l border-b border-muted" style={{ height: `${height}px` }}>
        <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
          {/* Graph-paper grid (clearly visible like pie) */}
          {hLines.map((y) => (
            <line key={`h-${y}`} x1="0" y1={y} x2="100" y2={y} stroke="currentColor" strokeOpacity={gridLineOpacityVisible} strokeWidth="0.5" />
          ))}
          {vLines.map((x) => (
            <line key={`v-${x}`} x1={x} y1="0" x2={x} y2="100" stroke="currentColor" strokeOpacity={gridLineOpacityVisible} strokeWidth="0.5" />
          ))}
          {data.map((point, index) => {
            const x = (point.x / maxX) * 95 + 2;
            const y = 98 - (point.y / maxY) * 95;
            return <circle key={index} cx={x} cy={y} r="2" fill={color} opacity="0.7" />;
          })}
        </svg>
      </div>
    </div>
  );
};

const SimpleHeatMap = ({ data, title }) => {
  if (!data || !data.rows || !data.cols || !data.values) {
    return <div className="flex items-center justify-center h-48 text-muted-foreground">No data available</div>;
  }
  const maxValue = Math.max(...data.values.flat(), 1);
  const getColor = (value) => `rgba(59, 130, 246, ${value / maxValue})`;
  return (
    <div className="w-full space-y-2">
      {title && <h4 className="font-medium text-sm text-foreground">{title}</h4>}
      <div className="w-full overflow-x-auto rounded-md border border-border">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr>
              <th className="p-1 border-b border-r border-border"></th>
              {data.cols.map((col, i) => (
                <th key={i} className="p-1 font-medium truncate max-w-[60px] border-b border-r border-border last:border-r-0">{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                <td className="p-1 font-medium truncate max-w-[80px] border-b border-r border-border">{row}</td>
                {data.values[rowIndex]?.map((value, colIndex) => (
                  <td key={colIndex} className="p-1 text-center border-b border-r border-border last:border-r-0" style={{ backgroundColor: getColor(value) }}>{value}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export function renderChart(chartData) {
  if (!chartData) return null;
  const { type, data, title, color, colors, orientation } = chartData;
  switch (type) {
    case 'bar':
      return orientation === 'vertical'
        ? <SimpleVerticalBarChart data={data} colors={colors} title={title} />
        : <SimpleBarChart data={data} colors={colors} title={title} />;
    case 'pie':
      return <SimplePieChart data={data} colors={colors} title={title} />;
    case 'line':
      return <SimpleLineChart data={data} color={color} title={title} />;
    case 'area':
      return <SimpleAreaChart data={data} color={color} title={title} />;
    case 'scatter':
      return <SimpleScatterPlot data={data} color={color} title={title} />;
    case 'heatmap':
      return <SimpleHeatMap data={data} title={title} />;
    default:
      return <SimpleBarChart data={data} colors={colors} title={title} />;
  }
}

export default renderChart;
