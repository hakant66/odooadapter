FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY app ./app
COPY next.config.mjs ./next.config.mjs

EXPOSE 3000

RUN npm run build
CMD ["npm", "start"]
