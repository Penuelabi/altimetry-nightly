# API server (+ admin dashboard at /admin) for Cloud Run. Build context is the repo root (npm workspaces).
FROM node:22-slim AS dashboard
WORKDIR /app
COPY package.json package-lock.json .npmrc tsconfig.base.json ./
COPY packages/core/package.json packages/core/
COPY server/package.json server/
COPY apps/pwa/package.json apps/pwa/
COPY apps/dashboard/package.json apps/dashboard/
RUN npm ci -w apps/dashboard -w packages/core --include-workspace-root=false
COPY packages/core packages/core
COPY apps/pwa/src/theme.css apps/pwa/src/theme.css
COPY apps/dashboard apps/dashboard
RUN cd apps/dashboard && npx vite build

FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production
COPY package.json package-lock.json .npmrc ./
COPY packages/core/package.json packages/core/
COPY server/package.json server/
COPY apps/pwa/package.json apps/pwa/
COPY apps/dashboard/package.json apps/dashboard/
RUN npm ci --omit=dev -w server -w packages/core --include-workspace-root=false
COPY packages/core packages/core
COPY server server
COPY --from=dashboard /app/apps/dashboard/dist apps/dashboard/dist
USER node
ENV PORT=8080
CMD ["node", "--import", "tsx", "server/src/index.ts"]
