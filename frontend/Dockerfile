# --- Build stage ---
FROM node:20-slim AS build
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
# Public reCAPTCHA v2 site key (not a secret -- it's meant to ship in
# frontend JS) -- baked in at build time since Vite only ever reads
# import.meta.env.VITE_* at build, never at runtime. Empty by default:
# LoginPage.tsx only renders the widget when this is set, so build/login
# keep working unchanged until the key pair is provisioned for
# forgehub.darckware.net.
ARG VITE_RECAPTCHA_SITE_KEY=""
ENV VITE_RECAPTCHA_SITE_KEY=$VITE_RECAPTCHA_SITE_KEY
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
