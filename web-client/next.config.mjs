/** @type {import('next').NextConfig} */
const nextConfig = {
  // The MCP stdio client and the Anthropic SDK are server-only Node modules.
  // Keep them external so Next doesn't try to bundle them into the route.
  serverExternalPackages: ["@modelcontextprotocol/sdk", "@anthropic-ai/sdk"],
};

export default nextConfig;
