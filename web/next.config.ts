import type { NextConfig } from "next";

// Site 100% estático: `npm run build` gera a pasta `out/`, que pode ser hospedada em qualquer lugar.
// Se for publicar em um subcaminho (ex.: GitHub Pages em usuario.github.io/repo), defina
// NEXT_PUBLIC_BASE_PATH=/repo antes do build.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  basePath,
  images: { unoptimized: true },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
