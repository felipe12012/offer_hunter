import { MAX_PAGE, PAGE_SIZE } from "./filters";

export function totalPages(total: number, pageSize: number = PAGE_SIZE): number {
  return Math.min(Math.max(Math.ceil(total / pageSize), 1), MAX_PAGE);
}

/** Números de página a mostrar: primera, última y una ventana alrededor de la actual; null = "…". */
export function pageWindow(current: number, total: number, around = 2): (number | null)[] {
  const pages = new Set<number>([1, total]);
  for (let p = current - around; p <= current + around; p++) if (p >= 1 && p <= total) pages.add(p);
  const sorted = [...pages].sort((a, b) => a - b);
  const result: (number | null)[] = [];
  sorted.forEach((page, index) => {
    if (index > 0 && page - sorted[index - 1] > 1) result.push(null);
    result.push(page);
  });
  return result;
}
