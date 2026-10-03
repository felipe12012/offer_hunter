// Esqueleto con las mismas proporciones que la grilla real: la página no salta al cargar.
export default function Loading() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-10" aria-busy="true" aria-label="Cargando ofertas">
      <div className="skeleton mb-3 h-12 max-w-xl" />
      <div className="skeleton mb-8 h-5 max-w-2xl" />
      <div className="grid grid-cols-2 border-l border-t border-line md:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: 8 }, (_, index) => (
          <div key={index} className="border-b border-r border-line bg-surface p-3">
            <div className="skeleton aspect-square w-full" />
            <div className="skeleton mt-3 h-4 w-1/3" />
            <div className="skeleton mt-2 h-10 w-full" />
            <div className="skeleton mt-3 h-8 w-1/2" />
          </div>
        ))}
      </div>
    </main>
  );
}
