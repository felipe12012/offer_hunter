import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-16">
      <h1 className="font-display text-4xl font-bold">No encontramos esa página</h1>
      <p className="mt-3 text-lg">El producto no existe o el enlace está incompleto.</p>
      <Link href="/" className="mt-6 inline-block border border-ink px-4 py-2 font-semibold hover:bg-ink hover:text-paper">
        Ir al inicio
      </Link>
    </main>
  );
}
