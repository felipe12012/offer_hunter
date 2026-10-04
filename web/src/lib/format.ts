import { GROUP_LABELS, SUBCATEGORIES } from "./taxonomy";

const CLP = new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 });

export function clp(amount: number): string {
  return CLP.format(Math.round(amount));
}

export function agoFrom(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "sin datos";
  const time = Date.parse(iso);
  if (Number.isNaN(time)) return "sin datos";
  const minutes = Math.max(0, Math.round((now - time) / 60_000));
  if (minutes < 1) return "hace un momento";
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `hace ${hours} ${hours === 1 ? "hora" : "horas"}`;
  const days = Math.round(hours / 24);
  return `hace ${days} ${days === 1 ? "día" : "días"}`;
}

const SHORT_DATE = new Intl.DateTimeFormat("es-CL", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "America/Santiago",
});

export function shortDate(iso: string): string {
  return SHORT_DATE.format(new Date(iso));
}

const STORE_NAMES: Record<string, string> = {
  falabella: "Falabella",
  sodimac: "Sodimac",
  hites: "Hites",
  ahumada: "Ahumada",
  vans: "Vans",
  crocs: "Crocs",
  merrell: "Merrell",
  salomon: "Salomon",
  hushpuppies: "Hush Puppies",
  asics: "Asics",
  reebok: "Reebok",
  converse: "Converse",
  puma: "Puma",
  newbalance: "New Balance",
  fila: "Fila",
  skechers: "Skechers",
  salcobrand: "Salcobrand",
  cruzverde: "Cruz Verde",
  lapolar: "La Polar",
  tricot: "Tricot",
  tusmascotas: "Tus Mascotas",
  laikamascotas: "Laika Mascotas",
  nike: "Nike",
  paris: "Paris",
  ripley: "Ripley",
  tottus: "Tottus",
};

export function storeName(slug: string): string {
  return STORE_NAMES[slug] ?? slug.charAt(0).toUpperCase() + slug.slice(1);
}

export function groupName(slug: string): string {
  return GROUP_LABELS[slug] ?? slug;
}

export function subName(group: string, sub: string): string {
  return SUBCATEGORIES[group]?.[sub] ?? sub;
}

/** Una oferta que no se ve desde hace más de `hours` ya no está a la venta. */
export function isStale(iso: string, hours: number, now: number = Date.now()): boolean {
  const time = Date.parse(iso);
  return Number.isNaN(time) || now - time > hours * 3_600_000;
}
