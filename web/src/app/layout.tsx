import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import Busca from "@/components/Busca";
import { eleicaoAtual, lerIndex } from "@/lib/dados";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Eleições 2026 no Piauí",
  description:
    "Resultados das eleições de 2026 no Piauí por município, zona eleitoral e local de votação, com mapa. Dados abertos do TSE.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const { ano, turno } = eleicaoAtual(await lerIndex());
  return (
    // suppressHydrationWarning: extensões de navegador (ex.: modo escuro) alteram os atributos de <html>
    // antes do React carregar, o que gera um aviso falso de hidratação em desenvolvimento.
    <html lang="pt-BR" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`} suppressHydrationWarning>
      <body className="flex min-h-full flex-col">
        <header className="border-b border-zinc-200 dark:border-zinc-800">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3">
            <Link href="/" className="text-lg font-semibold">
              Eleições {ano} · Piauí <span className="text-sm font-normal text-zinc-500">· {turno}º turno</span>
            </Link>
            <Busca ano={ano} turno={turno} />
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
        <footer className="border-t border-zinc-200 py-6 text-sm text-zinc-500 dark:border-zinc-800">
          <div className="mx-auto max-w-6xl space-y-1 px-4">
            <p>
              Fonte:{" "}
              <a className="underline" href="https://dadosabertos.tse.jus.br" target="_blank" rel="noreferrer">
                TSE — Portal de Dados Abertos
              </a>
              . Projeto independente, sem vínculo com o TSE. Os números podem divergir da divulgação oficial.
            </p>
            <p>Mapas © colaboradores do OpenStreetMap.</p>
          </div>
        </footer>
      </body>
    </html>
  );
}
