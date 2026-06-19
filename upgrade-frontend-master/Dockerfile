# Use Node.js as base image
FROM node:18-alpine

# Set the working directory
WORKDIR /app

# Copy package.json and package-lock.json
COPY package.json package-lock.json ./

# Install dependencies
RUN npm install

# Copy the entire project
COPY . .

# Build the Next.js app
RUN npm run build

# Expose the port (use the port that Next.js is set to run on)
EXPOSE 8080

# Set the environment variable for the port (optional, but ensures PORT is set)
ENV PORT=8080

# Start the Next.js app
CMD ["npm", "run", "start"]
