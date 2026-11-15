FROM node:22-alpine AS deps
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Inlined into the client bundle at build time: the public URL of the API (via the edge proxy).
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
RUN addgroup -S docly && adduser -S docly -G docly
COPY --from=build --chown=docly:docly /app/.next/standalone ./
COPY --from=build --chown=docly:docly /app/.next/static ./.next/static
COPY --from=build --chown=docly:docly /app/public ./public
USER docly
EXPOSE 3000
CMD ["node", "server.js"]
