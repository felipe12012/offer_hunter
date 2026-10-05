import { describe, expect, it } from "vitest";

import { availability, COARSE_END_MINUTES, endMinutes, FINE_END_MINUTES, FINE_MIN_DISCOUNT } from "./live";

const NOW = Date.parse("2026-10-05T12:00:00Z");
const ago = (minutes: number) => new Date(NOW - minutes * 60_000).toISOString();

describe("availability", () => {
  it("una oferta de 50 % o más se da por terminada con más de una hora sin verse", () => {
    expect(availability({ web_discount_pct: 60, last_seen_at: ago(20) }, NOW).ended).toBe(false);
    expect(availability({ web_discount_pct: 60, last_seen_at: ago(FINE_END_MINUTES) }, NOW).ended).toBe(false);
    expect(availability({ web_discount_pct: 60, last_seen_at: ago(FINE_END_MINUTES + 1) }, NOW).ended).toBe(true);
  });

  it("el resto se refresca cada hora: tiene más margen antes de darse por terminado", () => {
    expect(availability({ web_discount_pct: 10, last_seen_at: ago(100) }, NOW).ended).toBe(false);
    expect(availability({ web_discount_pct: 10, last_seen_at: ago(COARSE_END_MINUTES + 1) }, NOW).ended).toBe(true);
  });

  it("el límite depende del descuento justo en el umbral", () => {
    expect(endMinutes(FINE_MIN_DISCOUNT)).toBe(FINE_END_MINUTES);
    expect(endMinutes(FINE_MIN_DISCOUNT - 0.1)).toBe(COARSE_END_MINUTES);
  });

  it("devuelve los minutos sin verse", () => {
    expect(availability({ web_discount_pct: 0, last_seen_at: ago(37) }, NOW).minutes).toBe(37);
  });

  it("una fecha ilegible cuenta como terminada, no como vigente", () => {
    expect(availability({ web_discount_pct: 0, last_seen_at: "no es una fecha" }, NOW).ended).toBe(true);
  });

  it("una fecha del futuro (reloj distinto) no rompe nada", () => {
    expect(availability({ web_discount_pct: 80, last_seen_at: ago(-5) }, NOW)).toEqual({ ended: false, minutes: 0 });
  });
});
