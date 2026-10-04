import Link from "next/link";

export function SiteHeader({ q = "" }: { q?: string }) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-paper/95 backdrop-blur supports-[backdrop-filter]:bg-paper/85">
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:gap-6">
        <Link href="/" className="font-display text-2xl font-bold leading-none tracking-tight sm:text-3xl" aria-label="CazaOfertas, inicio">
          Caza<span className="text-verified">Ofertas</span>
        </Link>

        <form action="/" method="get" role="search" className="flex min-w-0 flex-1 items-center">
          <label htmlFor="busqueda" className="sr-only">
            Buscar productos
          </label>
          <input
            id="busqueda"
            name="q"
            type="search"
            defaultValue={q}
            maxLength={60}
            placeholder="Buscar"
            autoComplete="off"
            className="h-11 w-full min-w-0 border border-line bg-surface px-3 text-base placeholder:text-muted focus:border-ink"
          />
          <button
            type="submit"
            className="h-11 shrink-0 border border-ink bg-ink px-4 font-semibold text-paper hover:opacity-90"
          >
            Buscar
          </button>
        </form>

        <nav aria-label="Principal" className="hidden shrink-0 items-center gap-5 md:flex">
          <Link href="/cyber" className="font-semibold text-verified underline-offset-4 hover:underline">
            Cyber
          </Link>
          <Link href="/como-verificamos" className="font-medium underline-offset-4 hover:underline">
            Cómo verificamos
          </Link>
        </nav>
      </div>
    </header>
  );
}
