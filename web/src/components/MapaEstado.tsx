"use client";

import { useEffect } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useRouter } from "next/navigation";
import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap } from "react-leaflet";
import { fmt } from "@/lib/formato";

export type Bolha = {
  cd: number;
  nome: string;
  lat: number;
  lon: number;
  aptos: number;
  cor: string;
  /** 0 a 1: quão forte é a cor (usado nos modos que mostram uma proporção) */
  intensidade: number;
  /** texto do tooltip, depois do nome */
  detalhe: string;
};

function Ajustar({ bolhas }: { bolhas: Bolha[] }) {
  const mapa = useMap();
  useEffect(() => {
    if (bolhas.length === 0) return;
    mapa.fitBounds(L.latLngBounds(bolhas.map((b) => [b.lat, b.lon] as [number, number])), { padding: [24, 24] });
  }, [mapa, bolhas]);
  return null;
}

/** Uma bolha por município, no centro dos seus locais de votação. Clicar abre o município. */
export default function MapaEstado({ bolhas }: { bolhas: Bolha[] }) {
  const router = useRouter();
  const maior = Math.max(1, ...bolhas.map((b) => b.aptos));
  // bolhas maiores primeiro, para as pequenas não ficarem escondidas atrás delas
  const ordenadas = [...bolhas].sort((a, b) => b.aptos - a.aptos);
  return (
    <MapContainer
      center={[-7.2, -43]}
      zoom={6}
      scrollWheelZoom={false}
      className="z-0 h-[520px] w-full rounded-md border border-zinc-200 dark:border-zinc-800"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Ajustar bolhas={bolhas} />
      {ordenadas.map((b) => (
        <CircleMarker
          key={b.cd}
          center={[b.lat, b.lon]}
          radius={4 + 20 * Math.sqrt(b.aptos / maior)}
          pathOptions={{ color: b.cor, fillColor: b.cor, fillOpacity: 0.12 + 0.78 * b.intensidade, weight: 1 }}
          eventHandlers={{ click: () => router.push(`/municipio/${b.cd}/`) }}
        >
          <Tooltip>
            <strong>{b.nome}</strong>
            <br />
            {b.detalhe}
            <br />
            {fmt(b.aptos)} eleitores aptos
          </Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
