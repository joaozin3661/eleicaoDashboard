"use client";

import { useEffect } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";
import { APROXIMADA, PRECISAO, fmt } from "@/lib/formato";

export type PontoLocal = {
  id: string;
  lat: number;
  lon: number;
  nome: string;
  bairro: string | null;
  endereco: string | null;
  precisao: string | null;
  votos: number; // votos válidos no local
  vencedor: string; // nome do vencedor no local
  partido: string;
  pct: string; // % do vencedor
  cor: string;
};

/** Valor no percentil `q` (0–1) de uma lista já ordenada. */
const percentil = (ordenado: number[], q: number) => ordenado[Math.min(ordenado.length - 1, Math.floor(q * ordenado.length))];

function Ajustar({ pontos }: { pontos: PontoLocal[] }) {
  const mapa = useMap();
  useEffect(() => {
    if (pontos.length === 0) return;
    // Enquadra o miolo dos pontos (ignora ~3% mais distantes em cada ponta), para um local isolado
    // na zona rural não afastar o mapa. O usuário ainda pode arrastar/afastar para vê-lo.
    let alvo = pontos;
    if (pontos.length >= 30) {
      const lats = pontos.map((p) => p.lat).sort((a, b) => a - b);
      const lons = pontos.map((p) => p.lon).sort((a, b) => a - b);
      const [la0, la1, lo0, lo1] = [percentil(lats, 0.03), percentil(lats, 0.97), percentil(lons, 0.03), percentil(lons, 0.97)];
      alvo = pontos.filter((p) => p.lat >= la0 && p.lat <= la1 && p.lon >= lo0 && p.lon <= lo1);
    }
    const limites = L.latLngBounds(alvo.map((p) => [p.lat, p.lon] as [number, number]));
    mapa.fitBounds(limites, { padding: [30, 30], maxZoom: 15 });
  }, [mapa, pontos]);
  return null;
}

/**
 * Um círculo por local de votação: tamanho = votos válidos, cor = candidato mais votado ali.
 * Pontos de coordenada aproximada aparecem vazados (borda tracejada).
 */
export default function MapaLocais({ pontos }: { pontos: PontoLocal[] }) {
  const maior = Math.max(1, ...pontos.map((p) => p.votos));
  const centro: [number, number] = pontos.length ? [pontos[0].lat, pontos[0].lon] : [-7.5, -43];
  return (
    <MapContainer
      center={centro}
      zoom={11}
      scrollWheelZoom={false}
      className="z-0 h-[460px] w-full rounded-md border border-zinc-200 dark:border-zinc-800"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Ajustar pontos={pontos} />
      {pontos.map((p) => {
        const aprox = !!p.precisao && APROXIMADA.has(p.precisao);
        return (
          <CircleMarker
            key={p.id}
            center={[p.lat, p.lon]}
            radius={4 + 14 * Math.sqrt(p.votos / maior)}
            pathOptions={{
              color: p.cor,
              fillColor: p.cor,
              fillOpacity: aprox ? 0.08 : 0.55,
              weight: aprox ? 2 : 1,
              dashArray: aprox ? "4 3" : undefined,
            }}
          >
            <Popup>
              <div className="space-y-1 text-sm">
                <strong>{p.nome}</strong>
                <div>{[p.bairro, p.endereco].filter(Boolean).join(" · ")}</div>
                <div>
                  {fmt(p.votos)} votos válidos · mais votado: <strong>{p.vencedor}</strong> ({p.partido}, {p.pct})
                </div>
                {p.precisao && (
                  <div className="text-xs text-zinc-500">{PRECISAO[p.precisao] ?? p.precisao}</div>
                )}
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
