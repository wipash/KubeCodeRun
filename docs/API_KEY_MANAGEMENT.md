# API Key Management

The API supports multiple API keys with rate limiting, managed via CLI.

## CLI Commands

```bash
# Create a new API key with rate limits
python scripts/api_key_cli.py create --name "My App" --hourly 1000 --daily 10000

# Create an unlimited key
python scripts/api_key_cli.py create --name "Internal Service"

# List all keys
python scripts/api_key_cli.py list

# Show key details and usage
python scripts/api_key_cli.py show sk-abc12345

# Check current usage
python scripts/api_key_cli.py usage sk-abc12345

# Disable a key
python scripts/api_key_cli.py update sk-abc12345 --disable

# Revoke a key
python scripts/api_key_cli.py revoke sk-abc12345
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MASTER_API_KEY` | Required for CLI operations | (set in .env) |
| `RATE_LIMIT_ENABLED` | Enable per-key rate limiting | `true` |

## Backward Compatibility

- The `API_KEY` environment variable continues to work unchanged
- Env var keys have no rate limits (unlimited)
- Redis-managed keys are additive - they work alongside the env var key

## Rate Limit Headers

When rate limiting is active, responses include:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Maximum requests allowed |
| `X-RateLimit-Remaining` | Remaining requests |
| `X-RateLimit-Reset` | Reset timestamp (ISO format) |
| `X-RateLimit-Period` | Period (hourly/daily/monthly) |

## Architecture

| File | Purpose |
|------|---------|
| `src/models/api_key.py` | ApiKeyRecord, RateLimits dataclasses |
| `src/services/api_key_manager.py` | CRUD and rate limiting |
| `src/services/auth.py` | Validation with manager integration |
| `scripts/api_key_cli.py` | CLI management tool |
