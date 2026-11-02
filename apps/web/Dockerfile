FROM node:22-alpine AS dependencies
WORKDIR /workspace
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/package.json
# The lockfile also lists the desktop app; its manifest must exist, but only the web app is installed here.
COPY apps/desktop/package.json ./apps/desktop/package.json
RUN pnpm install --frozen-lockfile --no-optional --filter @nexus/web...

FROM node:22-alpine AS builder
WORKDIR /workspace
RUN corepack enable
ENV NEXT_TELEMETRY_DISABLED=1 \
    OTEL_SDK_DISABLED=true \
    CREWAI_DISABLE_TELEMETRY=true
ARG NEXT_PUBLIC_NEXUS_API_WS_URL=ws://localhost:8000
ENV NEXT_PUBLIC_NEXUS_API_WS_URL=$NEXT_PUBLIC_NEXUS_API_WS_URL
COPY --from=dependencies /workspace/node_modules ./node_modules
COPY --from=dependencies /workspace/apps/web/node_modules ./apps/web/node_modules
COPY . .
WORKDIR /workspace/apps/web
RUN node ../../scripts/check-npm-licenses.mjs && pnpm build

FROM node:22-alpine AS runner
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    OTEL_SDK_DISABLED=true \
    CREWAI_DISABLE_TELEMETRY=true
WORKDIR /workspace
COPY --from=builder --chown=node:node /workspace/apps/web/.next/standalone ./
COPY --from=builder --chown=node:node /workspace/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=node:node /workspace/apps/web/public ./apps/web/public
USER node
WORKDIR /workspace/apps/web
EXPOSE 3000
CMD ["sh", "-c", "HOSTNAME=0.0.0.0 exec node server.js"]
