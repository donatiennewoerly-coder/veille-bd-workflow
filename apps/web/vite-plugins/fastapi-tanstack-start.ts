import type { Plugin } from "vite";

/**
 * Sends the dev server's `/api` requests to the FastAPI app on `:3000`, so the web app can call
 * the API same-origin under `vite dev`. The generated client's paths already start with `/api`.
 */
const fastapiProxy: Plugin = {
  name: "fastapi-tanstack-start",
  config: () => ({
    server: {
      proxy: {
        "/api": {
          target: "http://localhost:3000",
          changeOrigin: true,
        },
      },
    },
  }),
};

export default fastapiProxy;
