"use client";

// Error amable: no muestra la traza ni detalles de la base de datos.
export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="mx-auto max-w-3xl px-4 py-16" role="alert">
      <h1 className="font-display text-4xl font-bold">No pudimos cargar las ofertas</h1>
      <p className="mt-3 text-lg">
        Hubo un problema al leer los datos. No es algo que hayas hecho tú: prueba de nuevo en unos segundos.
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 border border-ink px-4 py-2 font-semibold hover:bg-ink hover:text-paper"
      >
        Reintentar
      </button>
    </main>
  );
}
