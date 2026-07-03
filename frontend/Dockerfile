# --- Build stage ---
FROM node:20-slim AS build
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# --- Serve stage ---
# nginx instead of a plain static server (`serve`) so the API/websocket can
# be reverse-proxied on the same origin as the SPA -- see nginx.conf. Keeps
# the frontend build free of any baked-in backend hostname (src/lib/api.ts
# falls back to window.location.origin).
FROM nginx:alpine AS serve

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 4173
