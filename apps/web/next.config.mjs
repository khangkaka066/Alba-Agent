/** @type {import('next').NextConfig} */
const nextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  output: "standalone",
  images: { unoptimized: true },
};

export default nextConfig;
