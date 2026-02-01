# BiasBreaker Backend

A backend service for the BiasBreaker project that helps detect and mitigate bias in AI systems.

## Prerequisites

- Node.js (v14 or higher)
- npm or yarn
- Git

## Installation

```bash
# Clone the repository
git clone https://github.com/drjayaswal/biasbreaker-backend.git

# Navigate to the project directory
cd biasbreaker-backend

# Install dependencies
npm install
```

## Environment Setup

```bash
# Create a .env file
cp .env.example .env

# Update .env with your configuration
```

## Running the Backend

```bash
# Development mode
npm run dev

# Production mode
npm run build
npm start
```

## Git Workflow

To stage all changes for a commit:
```bash
git add .
```

To commit changes with a message:
```bash
git commit -m "describe your changes"
```

## Docker Deployment

To build and push the Docker image providing the Google Client ID, use:
## Platform Dependent MAC
```bash
docker build -t dhruv2k3/biasbreaker-backend:latest .
```
## Platform Independent MAC
```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t dhruv2k3/biasbreaker-backend:latest \
  --push .
```

To test locally:
```bash
docker run -p 5000:5000 dhruv2k3/biasbreaker-backend
```

To push to Docker Hub:
```bash
docker push dhruv2k3/biasbreaker-backend:latest
```

To run via docker-compose:
```bash
docker compose pull
docker compose up -d
```

## API Documentation

Visit `http://localhost:5000/docs` for API endpoints documentation.

## Contributing

Contributions are welcome. Please follow the existing code style and submit pull requests to the main branch.
