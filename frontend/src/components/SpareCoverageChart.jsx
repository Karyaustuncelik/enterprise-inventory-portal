import { forwardRef, useMemo } from "react";

const HIGH_THRESHOLD = 0.05;
const COLOR_STOPS = [
  { id: "optimum", color: "#7ed957", label: "Optimum Spare" },
  { id: "high", color: "var(--accent)", label: "High Spare" },
];

function classifyRatio(value) {
  if (value === null || value === undefined) return null;
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return null;
  const clamped = Math.max(0, Math.min(1, numeric));
  return clamped > HIGH_THRESHOLD ? COLOR_STOPS[1] : COLOR_STOPS[0];
}

const SpareCoverageChart = forwardRef(function SpareCoverageChart(
  { data = [], onExportVisuals, summary },
  ref,
) {
  const bars = useMemo(() => {
    return [...data]
      .map((item) => ({
        id: item.id,
        name: item.name ?? item.id,
        value: Number(item.value ?? item.ratio ?? 0) || 0,
      }))
      .sort((a, b) => b.value - a.value);
  }, [data]);

  const maxValue = 1;
  const chartHeight = 240;
  const chartWidth = 420;
  const padding = { top: 24, right: 16, bottom: 48, left: 50 };
  const innerWidth = chartWidth - padding.left - padding.right;
  const innerHeight = chartHeight - padding.top - padding.bottom;
  const gap = 12;
  const barWidth = bars.length ? Math.max(18, (innerWidth - gap * (bars.length - 1)) / bars.length) : 0;

  return (
    <div className="coverage-card" ref={ref}>
      <div className="coverage-card-header">
        <div>
          <span className="coverage-eyebrow">Spare coverage</span>
          <h3 className="coverage-title">Regional bar view</h3>
        </div>
        <div className="coverage-actions">
          <button type="button" className="ghost-button" onClick={onExportVisuals}>
            Export chart
          </button>
        </div>
      </div>
      {summary ? (
        <div className="coverage-summary">
          <span className="coverage-summary-value">{summary.value}</span>
          <span className="coverage-summary-label">{summary.label}</span>
          {summary.note ? (
            <span className="coverage-summary-note">{summary.note}</span>
          ) : null}
        </div>
      ) : null}
      <div className="coverage-chart" aria-label="Spare coverage by country bar chart">
        <svg width="100%" height={chartHeight} viewBox={`0 0 ${chartWidth} ${chartHeight}`} role="img">
          {/* y-axis guide */}
          {[0, 0.25, 0.5, 0.75, 1].map((t) => {
            const y = padding.top + innerHeight * (1 - t);
            return (
              <g key={t}>
                <line
                  x1={padding.left}
                  x2={chartWidth - padding.right}
                  y1={y}
                  y2={y}
                  stroke="rgba(31,35,40,0.08)"
                  strokeWidth="1"
                />
                <text
                  x={padding.left - 10}
                  y={y + 4}
                  textAnchor="end"
                  fontSize="10"
                  fill="rgba(74, 83, 98, 0.78)"
                >
                  {`${Math.round(t * 100)}%`}
                </text>
              </g>
            );
          })}
          {/* bars */}
          {bars.map((bar, index) => {
            const height = (bar.value / maxValue) * innerHeight;
            const x = padding.left + index * (barWidth + gap);
            const y = padding.top + innerHeight - height;
            const stop = classifyRatio(bar.value);
            return (
              <g key={bar.id} transform={`translate(${x}, ${y})`}>
                <rect
                  width={barWidth}
                  height={height}
                  rx="6"
                  fill={stop?.color ?? "var(--accent)"}
                />
                <text
                  x={barWidth / 2}
                  y={height + 16}
                  textAnchor="middle"
                  fontSize="10"
                  fill="rgba(74, 83, 98, 0.82)"
                >
                  {bar.id}
                </text>
                <text
                  x={barWidth / 2}
                  y={-6}
                  textAnchor="middle"
                  fontSize="10"
                  fill="var(--accent)"
                  fontWeight="600"
                >
                  {`${(bar.value * 100).toFixed(1)}%`}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="coverage-legend">
        {COLOR_STOPS.map((stop) => (
          <span key={stop.id} className="coverage-legend-item">
            <span className="coverage-legend-swatch" style={{ backgroundColor: stop.color }} />
            {stop.label}
          </span>
        ))}
      </div>
    </div>
  );
});

export default SpareCoverageChart;
