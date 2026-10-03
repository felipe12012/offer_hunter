import type { Metadata, Viewport } from "next";
import { Barlow_Condensed, Public_Sans } from "next/font/google";

import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";

import "./globals.css";

// Barlow Condensed: rótulo de tienda para precios y titulares. Public Sans: texto.
const barlow = Barlow_Condensed({
  variable: "--font-barlow",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  display: "swap",
});

const publicSans = Public_Sans({
  variable: "--font-public",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "CazaOfertas: descuentos con el precio comprobado",
    template: "%s | CazaOfertas",
  },
  description:
    "Seguimos el precio de miles de productos en tiendas chilenas y marcamos los descuentos que bajaron de verdad.",
  // Sin indexar hasta que el equipo lo apruebe.
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f5f7" },
    { media: "(prefers-color-scheme: dark)", color: "#0d1320" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-CL" className={`${barlow.variable} ${publicSans.variable}`}>
      <body className="flex min-h-screen flex-col">
        <a
          href="#contenido"
          className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:bg-surface focus:px-3 focus:py-2"
        >
          Saltar al contenido
        </a>
        <SiteHeader />
        <div id="contenido" className="flex-1">
          {children}
        </div>
        <SiteFooter />
      </body>
    </html>
  );
}
