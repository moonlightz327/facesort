import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Build the SPA into the Python package so `facesort gui` can serve it.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../facesort/gui/static",
    emptyOutDir: true,
  },
});
