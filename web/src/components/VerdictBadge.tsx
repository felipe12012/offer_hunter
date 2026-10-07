import type { Verdict } from "@/lib/verdict";

/** Veredicto del historial en una etiqueta corta. El color nunca es la única señal: lleva texto y símbolo. */
export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const symbol = verdict.tone === "ok" ? "★" : verdict.tone === "warn" ? "!" : "?";
  const tone =
    verdict.tone === "ok"
      ? "border-verified bg-verified-bg"
      : verdict.tone === "warn"
        ? "border-[var(--tier-gran)] bg-claim-bg"
        : "border-line";
  return (
    <span className={`inline-flex items-center gap-1 border px-2 py-0.5 text-xs font-semibold ${tone}`} title={verdict.detail}>
      <span aria-hidden="true">{symbol}</span> {verdict.label}
    </span>
  );
}
