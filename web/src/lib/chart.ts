import type { PricePoint } from "./types";

export type ChartDot = { x: number; y: number; price: number; at: string };

export type Chart = {
  /** Una sola observación: no hay línea que dibujar. */
  single: boolean;
  width: number;
  height: number;
  pricePath: string;
  listPath: string;
  dots: ChartDot[];
  ticks: { y: number; price: number }[];
  yMin: number;
  yMax: number;
  left: number;
  right: number;
};

type Options = { width?: number; height?: number; left?: number; right?: number; top?: number; bottom?: number; endAt?: string };

/**
 * Serie de precios como línea escalonada (el precio se mantiene hasta que cambia).
 * Pura: sin DOM ni fechas actuales; `endAt` extiende el último precio hasta "ahora".
 */
export function buildChart(points: PricePoint[], opts: Options = {}): Chart {
  const width = opts.width ?? 640;
  const height = opts.height ?? 260;
  const left = opts.left ?? 100;
  const right = opts.right ?? 16;
  const top = opts.top ?? 16;
  const bottom = opts.bottom ?? 20;

  const sorted = [...points].sort((a, b) => Date.parse(a.observed_at) - Date.parse(b.observed_at));
  const prices = sorted.flatMap((p) => [p.price, ...(p.list_price && p.list_price > 0 ? [p.list_price] : [])]);
  if (sorted.length === 0 || prices.length === 0) {
    return { single: true, width, height, pricePath: "", listPath: "", dots: [], ticks: [], yMin: 0, yMax: 0, left, right };
  }

  let yMin = Math.min(...prices);
  let yMax = Math.max(...prices);
  if (yMin === yMax) {
    yMin = yMin * 0.9;
    yMax = yMax * 1.1;
  } else {
    const pad = (yMax - yMin) * 0.1;
    yMin = Math.max(0, yMin - pad);
    yMax = yMax + pad;
  }

  const t0 = Date.parse(sorted[0].observed_at);
  const tEnd = Math.max(Date.parse(opts.endAt ?? sorted[sorted.length - 1].observed_at), Date.parse(sorted[sorted.length - 1].observed_at));
  const span = Math.max(tEnd - t0, 1);

  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const X = (t: number) => (sorted.length === 1 ? left + plotW / 2 : left + ((t - t0) / span) * plotW);
  const Y = (price: number) => top + (1 - (price - yMin) / (yMax - yMin)) * plotH;
  const r = (n: number) => Math.round(n * 10) / 10;

  const step = (value: (p: PricePoint) => number | null): string => {
    let path = "";
    let last: number | null = null;
    sorted.forEach((p) => {
      const v = value(p);
      if (v === null) return;
      const x = X(Date.parse(p.observed_at));
      path += last === null ? `M${r(x)} ${r(Y(v))}` : `H${r(x)}V${r(Y(v))}`;
      last = v;
    });
    if (last !== null && sorted.length > 1) path += `H${r(left + plotW)}`;
    return path;
  };

  const dots = sorted.map((p) => ({ x: r(X(Date.parse(p.observed_at))), y: r(Y(p.price)), price: p.price, at: p.observed_at }));
  const tickPrices = [yMin + (yMax - yMin) * 0.1, (yMin + yMax) / 2, yMax - (yMax - yMin) * 0.1];

  return {
    single: sorted.length === 1,
    width,
    height,
    pricePath: step((p) => p.price),
    listPath: step((p) => (p.list_price && p.list_price > 0 ? p.list_price : null)),
    dots,
    ticks: tickPrices.map((price) => ({ y: r(Y(price)), price: Math.round(price) })),
    yMin,
    yMax,
    left,
    right,
  };
}
