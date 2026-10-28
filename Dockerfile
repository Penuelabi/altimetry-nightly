# API server for Cloud Run. Build context is the repo root (npm workspaces).
FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production
COPY package.json package-lock.json .npmrc ./
COPY packages/core/package.json packages/core/
COPY server/package.json server/
COPY apps/pwa/package.json apps/pwa/
RUN npm ci --omit=dev -w server -w packages/core --include-workspace-root=false
COPY packages/core packages/core
COPY server server
USER node
ENV PORT=8080
CMD ["node", "--import", "tsx", "server/src/index.ts"]
