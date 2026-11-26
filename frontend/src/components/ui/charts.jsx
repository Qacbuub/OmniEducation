function NoData({ height = 160 }) {
  return (
    <div className="muted" style={{ height, display: "grid", placeItems: "center", fontSize: "var(--fs-sm)" }}>
      No data yet
    </div>
  );
}

/**
 * Lightweight, dependency-free SVG charts in OmniTeckno colours.
 * Each chart has an accessible title and a visually hidden data table for screen readers.
 */

function SrTable({ caption, data, format = (v) => v }) {
  return (
    <table className="sr-only">
      <caption>{caption}</caption>
      <tbody>{data.map((d) => <tr key={d.label}><th scope="row">{d.label}</th><td>{format(d.value)}</td></tr>)}</tbody>
    </table>
  );
}

/** Round an axis maximum so its 4 gridline steps are "nice" numbers (5, 10, 15, 25, 50, 100…). */
const niceMax = (v, steps = 4) => {
  const raw = (v || 1) / steps;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / mag;
  const step = (n <= 1 ? 1 : n <= 1.5 ? 1.5 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
  return step * steps;
};

export function BarChart({ data, title, height = 220, format = (v) => v, color = "var(--brand)", max: maxProp }) {
  if (!data?.length) return <NoData height={height} />;
  const W = 560, H = height, pad = { t: 16, r: 8, b: 28, l: 40 };
  const max = maxProp ?? niceMax(Math.max(...data.map((d) => d.value)));
  const innerW = W - pad.l - pad.r, innerH = H - pad.t - pad.b;
  const bw = innerW / data.length;
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <figure style={{ margin: 0 }}>
      <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title}>
        {ticks.map((t) => {
          const y = pad.t + innerH * (1 - t);
          return (
            <g key={t}>
              <line x1={pad.l} x2={W - pad.r} y1={y} y2={y} stroke="var(--border)" />
              <text x={pad.l - 8} y={y + 4} textAnchor="end">{format(Math.round(max * t))}</text>
            </g>
          );
        })}
        {data.map((d, i) => {
          const h = (d.value / max) * innerH;
          const x = pad.l + i * bw + bw * 0.2;
          return (
            <g key={d.label}>
              <rect x={x} y={pad.t + innerH - h} width={bw * 0.6} height={h} rx="4" fill={color}>
                <title>{`${d.label}: ${format(d.value)}`}</title>
              </rect>
              <text x={x + bw * 0.3} y={H - 8} textAnchor="middle">{d.label}</text>
            </g>
          );
        })}
      </svg>
      <SrTable caption={title} data={data} format={format} />
    </figure>
  );
}

export function LineChart({ data, title, height = 220, min, max, format = (v) => v }) {
  if (!data?.length) return <NoData height={height} />;
  const W = 560, H = height, pad = { t: 16, r: 12, b: 28, l: 40 };
  const vals = data.map((d) => d.value);
  const lo = min ?? Math.floor(Math.min(...vals) - 2);
  const hi = max ?? Math.ceil(Math.max(...vals) + 2);
  const innerW = W - pad.l - pad.r, innerH = H - pad.t - pad.b;
  const x = (i) => pad.l + (data.length === 1 ? innerW / 2 : (i / (data.length - 1)) * innerW);
  const y = (v) => pad.t + innerH * (1 - (v - lo) / (hi - lo));
  const path = data.map((d, i) => `${i ? "L" : "M"}${x(i)},${y(d.value)}`).join(" ");
  const area = `${path} L${x(data.length - 1)},${pad.t + innerH} L${x(0)},${pad.t + innerH} Z`;
  const ticks = [0, 0.5, 1].map((t) => lo + (hi - lo) * t);
  return (
    <figure style={{ margin: 0 }}>
      <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title}>
        <defs>
          <linearGradient id="lc-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#00AEFF" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#00AEFF" stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="var(--border)" />
            <text x={pad.l - 8} y={y(t) + 4} textAnchor="end">{format(Math.round(t))}</text>
          </g>
        ))}
        <path d={area} fill="url(#lc-fill)" />
        <path d={path} fill="none" stroke="var(--brand)" strokeWidth="2.5" strokeLinejoin="round" />
        {data.map((d, i) => (
          <g key={d.label}>
            <circle cx={x(i)} cy={y(d.value)} r="4" fill="var(--black)" stroke="var(--brand)" strokeWidth="2">
              <title>{`${d.label}: ${format(d.value)}`}</title>
            </circle>
            <text x={x(i)} y={H - 8} textAnchor="middle">{d.label}</text>
          </g>
        ))}
      </svg>
      <SrTable caption={title} data={data} format={format} />
    </figure>
  );
}

/** Horizontal progress bars - good for capacity / share-of-total views. */
export function HBarList({ data, format = (v) => v, maxValue }) {
  if (!data?.length) return <NoData />;
  const max = maxValue ?? Math.max(...data.map((d) => d.capacity ?? d.value));
  return (
    <div className="hbar">
      {data.map((d) => {
        const total = d.capacity ?? max;
        const pct = Math.min(100, (d.value / total) * 100);
        const full = d.capacity && d.value >= d.capacity;
        return (
          <div className="hbar__row" key={d.label}>
            <span title={d.label} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.label}</span>
            <div className="hbar__track" role="progressbar" aria-label={d.label}
              aria-valuenow={d.value} aria-valuemin={0} aria-valuemax={total}>
              <div className="hbar__fill" style={{ width: `${pct}%`, background: full ? "var(--black)" : undefined }} />
            </div>
            <span className="hbar__value">{d.capacity ? `${d.value}/${d.capacity}` : format(d.value)}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Donut for a 2–4 part split (e.g. collected vs outstanding). */
export function Donut({ data, title, format = (v) => v, colors = ["#00AEFF", "#000000", "#8A94A3", "#CDD5DF"] }) {
  const sum = data.reduce((s, d) => s + Number(d.value), 0);
  if (!sum) return <NoData />;
  const total = sum;
  const R = 70, C = 2 * Math.PI * R;
  let offset = 0;
  const pct = Math.round((Number(data[0].value) / total) * 100);
  return (
    <figure style={{ margin: 0, display: "flex", alignItems: "center", gap: 24, flexWrap: "wrap" }}>
      <svg viewBox="0 0 180 180" width="160" height="160" role="img" aria-label={title}>
        <g transform="rotate(-90 90 90)">
          {data.map((d, i) => {
            const len = (Number(d.value) / total) * C;
            const el = (
              <circle key={d.label} cx="90" cy="90" r={R} fill="none" stroke={colors[i]} strokeWidth="22"
                strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-offset}>
                <title>{`${d.label}: ${format(d.value)}`}</title>
              </circle>
            );
            offset += len;
            return el;
          })}
        </g>
        <text x="90" y="88" textAnchor="middle" style={{ fontSize: 26, fontWeight: 800, fill: "var(--text)" }}>{pct}%</text>
        <text x="90" y="108" textAnchor="middle" style={{ fontSize: 11, fill: "var(--text-muted)" }}>{data[0].label.toLowerCase()}</text>
      </svg>
      <figcaption className="stack" style={{ gap: 10 }}>
        {data.map((d, i) => (
          <div key={d.label} style={{ fontSize: "var(--fs-sm)" }}>
            <span className="legend__swatch" style={{ background: colors[i] }} />
            <span className="muted">{d.label}</span>
            <div style={{ fontWeight: 700, marginLeft: 16 }}>{format(d.value)}</div>
          </div>
        ))}
      </figcaption>
    </figure>
  );
}
