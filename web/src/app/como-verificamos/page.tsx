import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Cómo verificamos los descuentos" };

export default function HowWeVerify() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-10 sm:py-14">
      <h1 className="font-display text-4xl font-bold leading-tight sm:text-5xl">Cómo verificamos los descuentos</h1>
      <p className="mt-4 text-lg leading-relaxed">
        Muchas tiendas muestran un precio “normal” tachado que casi nunca se cobró. Así el descuento parece enorme aunque
        el precio de siempre sea el de oferta. Por eso no nos fiamos del porcentaje que anuncia la tienda: guardamos el
        precio de cada producto cada vez que lo revisamos y comparamos con lo que vimos antes.
      </p>

      <h2 className="mt-10 font-display text-2xl font-semibold">Cuándo un descuento lleva el sello ✓ Verificada</h2>
      <ul className="mt-3 flex flex-col gap-3 leading-relaxed">
        <li className="border border-verified bg-verified-bg px-4 py-3">
          <strong>El precio normal es real.</strong> Registramos el producto a un precio cercano al “normal” que muestra
          la tienda (a menos de un 5 % de diferencia). Si lo vimos a ese precio, el ahorro es cierto.
        </li>
        <li className="border border-verified bg-verified-bg px-4 py-3">
          <strong>Bajó contra su propio historial.</strong> El precio actual está al menos 10 % por debajo del más bajo
          que habíamos visto antes.
        </li>
      </ul>
      <p className="mt-4 leading-relaxed">
        El porcentaje grande que ves en la etiqueta es siempre el verificado: el que podemos respaldar con nuestro
        historial.
      </p>

      <h2 className="mt-10 font-display text-2xl font-semibold">Qué significa “Sin verificar”</h2>
      <p className="mt-3 leading-relaxed">
        La tienda anuncia un descuento, pero todavía no tenemos historial que lo respalde: por ejemplo, porque empezamos a
        seguir el producto hace poco. No quiere decir que sea falso, solo que no podemos comprobarlo. Estas ofertas
        aparecen con la etiqueta gris “anuncia” y siempre después de las verificadas.
      </p>

      <h2 className="mt-10 font-display text-2xl font-semibold">Lo que no podemos garantizar</h2>
      <ul className="mt-3 list-disc space-y-2 pl-6 leading-relaxed">
        <li>
          El historial es reciente, así que hoy son pocos los productos verificados. Mejora con los días, a medida que
          vemos cambiar los precios.
        </li>
        <li>Un descuento muy grande (80 % o más) también puede ser un error de precio de la tienda.</li>
        <li>No sabemos si queda stock ni el precio final con envío o cuotas. Confirma siempre en la tienda.</li>
        <li>Revisamos los precios cada pocos minutos, pero pueden cambiar entre una revisión y otra.</li>
      </ul>

      <Link href="/" className="mt-10 inline-block border border-ink px-5 py-2.5 font-semibold hover:bg-ink hover:text-paper">
        Ver las ofertas
      </Link>
    </main>
  );
}
