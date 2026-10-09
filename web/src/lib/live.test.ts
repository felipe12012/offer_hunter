import { describe, expect, it } from "vitest";

import { availability, ENDED_MINUTES, referenceTime, staleMinutes } from "./live";

const NOW = Date.parse("2026-10-05T12:00:00Z");
const ago = (minutes: number) => new Date(NOW - minutes * 60_000).toISOString();

describe("availability", () => {
  it("un producto que no vemos desde hace una o dos horas NO se da por terminado (puede haber salido del listado)", () => {
    expect(availability({ last_seen_at: ago(20) }, NOW).ended).toBe(false);
    expect(availability({ last_seen_at: ago(60) }, NOW).ended).toBe(false);
    expect(availability({ last_seen_at: ago(150) }, NOW).ended).toBe(false);
  });

  it("solo tras muchas horas sin verse se da por terminado", () => {
    expect(availability({ last_seen_at: ago(ENDED_MINUTES) }, NOW).ended).toBe(false);
    expect(availability({ last_seen_at: ago(ENDED_MINUTES + 1) }, NOW).ended).toBe(true);
  });

  it("devuelve los minutos sin verse", () => {
    expect(availability({ last_seen_at: ago(37) }, NOW).minutes).toBe(37);
  });

  it("una fecha ilegible cuenta como terminada, no como vigente", () => {
    expect(availability({ last_seen_at: "no es una fecha" }, NOW).ended).toBe(true);
  });

  it("una fecha del futuro (reloj distinto) no rompe nada", () => {
    expect(availability({ last_seen_at: ago(-5) }, NOW)).toEqual({ ended: false, minutes: 0 });
  });
});

describe("referencia al último escaneo", () => {
  const now = Date.parse("2026-10-09T15:00:00Z");

  it("sin escaneo reciente la referencia es la del último que funcionó, no 'ahora'", () => {
    expect(referenceTime("2026-10-09T07:00:00Z", now)).toBe(Date.parse("2026-10-09T07:00:00Z"));
    expect(staleMinutes(referenceTime("2026-10-09T07:00:00Z", now), now)).toBe(480);
  });

  it("nunca es del futuro y sin dato vale 'ahora'", () => {
    expect(referenceTime("2026-10-10T00:00:00Z", now)).toBe(now);
    expect(referenceTime(null, now)).toBe(now);
    expect(referenceTime("basura", now)).toBe(now);
  });

  it("un producto visto 3 h antes del último escaneo sigue vivo aunque hoy lleve 11 h sin verse", () => {
    const reference = referenceTime("2026-10-09T07:00:00Z", now);
    expect(availability({ last_seen_at: "2026-10-09T04:00:00Z" }, reference).ended).toBe(false);
    expect(availability({ last_seen_at: "2026-10-09T04:00:00Z" }, now).ended).toBe(true);
  });
});
