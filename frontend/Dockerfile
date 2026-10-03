# Development image: Vite dev server with the API proxied to $PARTI_API_URL.
FROM node:22-alpine

WORKDIR /usr/src/app
COPY package*.json ./
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
RUN npm ci

COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
