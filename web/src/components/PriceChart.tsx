import { buildChart } from "@/lib/chart";
import { clp, shortDate } from "@/lib/format";
import type { PricePoint } from "@/lib/types";

/** Historial de precios: SVG propio (sin librerías), línea escalonada. */
export function PriceChart({ points, endAt }: { points: PricePoint[]; endAt?: string }) {
  const chart = buildChart(points, { endAt });

  if (points.length === 0) {
    return <p className="text-muted">Todavía no hay precios registrados para este producto.</p>;
  }

  const first = points[0];
  const last = points[points.length - 1];
  const summary =
    points.length === 1
      ? `Un solo precio registrado: ${clp(first.price)} el ${shortDate(first.observed_at)}.`
      : `Historial de ${points.length} cambios de precio, de ${clp(first.price)} el ${shortDate(first.observed_at)} a ${clp(last.price)} el ${shortDate(last.observed_at)}.`;

  return (
    <figure>
      <svg
        viewBox={`0 0 ${chart.width} ${chart.height}`}
        role="img"
        aria-label={summary}
        className="h-auto w-full max-w-2xl"
      >
        {chart.ticks.map((tick) => (
          <g key={tick.price}>
            <line x1={chart.left} x2={chart.width - chart.right} y1={tick.y} y2={tick.y} stroke="var(--line)" strokeWidth={1.5} />
            <text x={chart.left - 8} y={tick.y + 6} textAnchor="end" fontSize={20} fill="var(--muted)">
              {clp(tick.price)}
            </text>
          </g>
        ))}
        {chart.listPath ? (
          <path d={chart.listPath} fill="none" stroke="var(--muted)" strokeWidth={2.5} strokeDasharray="8 6" />
        ) : null}
        {chart.pricePath ? (
          <path d={chart.pricePath} fill="none" stroke="var(--ink)" strokeWidth={4} strokeLinejoin="round" />
        ) : null}
        {chart.dots.map((dot) => (
          <circle key={dot.at} cx={dot.x} cy={dot.y} r={7} fill="var(--surface)" stroke="var(--ink)" strokeWidth={4}>
            <title>{`${clp(dot.price)} · ${shortDate(dot.at)}`}</title>
          </circle>
        ))}
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted">
        <span>
          <span aria-hidden="true" className="mr-1.5 inline-block h-0.5 w-5 bg-ink align-middle" />
          Precio
        </span>
        {chart.listPath ? (
          <span>
            <span aria-hidden="true" className="mr-1.5 inline-block w-5 border-t-2 border-dashed border-muted align-middle" />
            Precio normal que muestra la tienda
          </span>
        ) : null}
      </figcaption>
      {points.length === 1 ? (
        <p className="mt-2 text-sm text-muted">Aún no hay variaciones registradas: solo hemos visto este precio.</p>
      ) : null}
    </figure>
  );
}
