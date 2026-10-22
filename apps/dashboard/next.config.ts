import type { NextConfig } from "next";
const config: NextConfig = {
  async rewrites() {
    // Public application routes only; management and worker routes never cross this proxy.
    return ["v1/:path*", "auth/:path*"].map((path) => ({
      source: `/api/${path}`,
      destination: `${process.env.API_PROXY_URL || "http://127.0.0.1:8080"}/${path}`,
    }));
  },
};
export default config;
