import type { NextConfig } from "next";

// A fully static site: `next build` writes plain HTML, CSS and JS to out/.
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  // Don't write AGENTS.md / CLAUDE.md into the project on `next dev`.
  agentRules: false,
};

export default nextConfig;
