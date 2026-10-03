import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="mt-16 border-t border-line">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-8 text-sm text-muted sm:flex-row sm:items-start sm:justify-between">
        <p className="max-w-xl">
          Los precios y la disponibilidad cambian: confirma siempre en la tienda antes de comprar. CazaOfertas no es una
          tienda ni vende productos.
        </p>
        <Link href="/como-verificamos" className="font-medium text-ink underline underline-offset-4">
          Cómo verificamos los descuentos
        </Link>
      </div>
    </footer>
  );
}
