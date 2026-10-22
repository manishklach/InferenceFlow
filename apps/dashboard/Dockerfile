FROM node:22.16.0-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG API_PROXY_URL=http://api:8080
ENV API_PROXY_URL=$API_PROXY_URL
RUN npm run build
EXPOSE 3000
CMD ["npm","start"]
