# Development Guide

This document provides detailed instructions for setting up the development environment, installing dependencies, and running tests.

## Setup & Installation

### Prerequisites

- Python 3.11+
- Docker Engine
- Redis
- MinIO (or S3-compatible storage)

### Installation Steps

1. **Clone the repository**

   ```bash
   git clone https://github.com/LibreCodeInterpreter/LibreCodeInterpreter.git
   cd LibreCodeInterpreter
   ```

2. **Create a virtual environment**

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**

   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Start infrastructure services**

   ```bash
   docker-compose up -d
   ```

6. **Run the API server**
   ```bash
   uvicorn src.main:app --reload
   ```

## Testing

For detailed testing instructions, please refer to [TESTING.md](TESTING.md).

### Quick Commands

```bash
# Run unit tests
pytest tests/unit/

# Run integration tests (requires Docker/Redis/MinIO)
pytest tests/integration/

# Run all tests with coverage
pytest --cov=src tests/
```

## Building Docker Images

The API requires language-specific execution images.

```bash
# Build all language execution images
cd docker && ./build-images.sh -p && cd ..

# Build a single language image (e.g., Python)
cd docker && ./build-images.sh -l python && cd ..
```

For more details on container management, see [ARCHITECTURE.md](ARCHITECTURE.md).
