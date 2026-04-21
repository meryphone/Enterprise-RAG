import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  swcMinify: false,
  webpack: (config) => {
    config.resolve.alias['@babel/runtime'] = path.resolve(__dirname, 'node_modules/@babel/runtime');
    return config;
  },
};

export default nextConfig;
