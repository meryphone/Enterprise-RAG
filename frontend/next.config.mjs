import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // Proxy /api/* → FastAPI backend (localhost:8000).
    // Next.js API routes under app/api/ take precedence over these rewrites,
    // so /api/auth/login and /api/auth/logout are handled by route.ts files.
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/:path*",
      },
    ];
  },
  webpack: (config) => {
    const localRuntime = path.resolve(__dirname, 'node_modules/@babel/runtime');
    config.resolve.alias['@babel/runtime'] = localRuntime;
    // Also add local node_modules first in resolution order
    if (!config.resolve.modules) config.resolve.modules = ['node_modules'];
    config.resolve.modules = [
      path.resolve(__dirname, 'node_modules'),
      ...config.resolve.modules.filter(m => m !== path.resolve(__dirname, 'node_modules')),
    ];
    return config;
  },
};

export default nextConfig;
