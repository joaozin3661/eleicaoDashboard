"use client";

import { useState } from "react";
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";

type Props<T> = {
  dados: T[];
  colunas: ColumnDef<T, any>[]; // eslint-disable-line @typescript-eslint/no-explicit-any
  placeholderBusca?: string;
  porPagina?: number;
  filtroInicial?: string;
};

/** Tabela com busca, ordenação por coluna e paginação (TanStack Table). */
export default function Tabela<T>({ dados, colunas, placeholderBusca = "Buscar…", porPagina = 15, filtroInicial = "" }: Props<T>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [filtro, setFiltro] = useState(filtroInicial);

  const tabela = useReactTable({
    data: dados,
    columns: colunas,
    state: { sorting, globalFilter: filtro },
    onSortingChange: setSorting,
    onGlobalFilterChange: setFiltro,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: porPagina } },
  });

  const { pageIndex } = tabela.getState().pagination;
  const total = tabela.getFilteredRowModel().rows.length;

  return (
    <div className="space-y-3">
      <input
        value={filtro}
        onChange={(e) => setFiltro(e.target.value)}
        placeholder={placeholderBusca}
        aria-label={placeholderBusca}
        className="w-full rounded-md border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700 sm:w-80"
      />
      <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-50 text-xs uppercase text-zinc-500 dark:bg-zinc-900">
            {tabela.getHeaderGroups().map((grupo) => (
              <tr key={grupo.id}>
                {grupo.headers.map((h) => {
                  const ordem = h.column.getIsSorted();
                  return (
                    <th
                      key={h.id}
                      onClick={h.column.getToggleSortingHandler()}
                      className="cursor-pointer select-none whitespace-nowrap px-3 py-2 font-medium"
                      aria-sort={ordem === "asc" ? "ascending" : ordem === "desc" ? "descending" : "none"}
                    >
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {ordem === "asc" ? " ▲" : ordem === "desc" ? " ▼" : ""}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {tabela.getRowModel().rows.map((linha) => (
              <tr key={linha.id} className="border-t border-zinc-100 dark:border-zinc-800">
                {linha.getVisibleCells().map((c) => (
                  <td key={c.id} className="px-3 py-2 align-top">
                    {flexRender(c.column.columnDef.cell, c.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {total === 0 && (
              <tr>
                <td colSpan={colunas.length} className="px-3 py-6 text-center text-zinc-500">
                  Nada encontrado.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between text-sm text-zinc-500">
        <span>
          {total} {total === 1 ? "linha" : "linhas"}
        </span>
        {tabela.getPageCount() > 1 && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => tabela.previousPage()}
              disabled={!tabela.getCanPreviousPage()}
              className="rounded border border-zinc-300 px-2 py-1 disabled:opacity-40 dark:border-zinc-700"
            >
              Anterior
            </button>
            <span>
              {pageIndex + 1} / {tabela.getPageCount()}
            </span>
            <button
              onClick={() => tabela.nextPage()}
              disabled={!tabela.getCanNextPage()}
              className="rounded border border-zinc-300 px-2 py-1 disabled:opacity-40 dark:border-zinc-700"
            >
              Próxima
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
