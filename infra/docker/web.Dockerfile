FROM node:22-slim AS base

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web /app

EXPOSE 3000

CMD ["npm", "run", "dev"]
