# Stage 1: build the React app.  Stage 2: Nginx serves it and proxies /api to the Django container.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# The real API (never the demo mock) behind the same origin: Nginx forwards /api.
ENV VITE_USE_MOCK=false VITE_API_URL=/api
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# The site config is mounted from deploy/nginx/ by docker-compose.prod.yml.
EXPOSE 80 443
