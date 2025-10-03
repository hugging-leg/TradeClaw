# 🐳 Docker Deployment Guide

## 📋 Overview

This guide covers deploying the LLM Trading Agent using Docker and Docker Compose with an in-memory event system for simplicity and performance.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                LLM Trading Agent                    │
│          (In-Memory Event System)                   │
│                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │   Alpaca    │  │   Tiingo    │  │  Telegram   │  │
│  │     API     │  │     API     │  │     Bot     │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│                PostgreSQL                           │
│              (Data Storage)                         │
└─────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Clone and Setup

```bash
# Clone repository
git clone <repository-url>
cd Agent_Trader

# Copy environment template
cp env.template .env
```

### 2. Configure Environment

Edit `.env` with your API keys:

```bash
# Trading APIs
ALPACA_API_KEY=your_alpaca_api_key
ALPACA_SECRET_KEY=your_alpaca_secret_key
ALPACA_BASE_URL=https://paper-api.alpaca.markets
TIINGO_API_KEY=your_tiingo_api_key

# LLM Provider (choose one)
LLM_PROVIDER=openai  # or deepseek
OPENAI_API_KEY=your_openai_key
# DEEPSEEK_API_KEY=your_deepseek_key

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Database
POSTGRES_PASSWORD=secure_database_password

# Trading Configuration
MAX_POSITION_SIZE=0.1
STOP_LOSS_PERCENTAGE=0.05
TAKE_PROFIT_PERCENTAGE=0.15
REBALANCE_TIME=09:30
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### 3. Deploy

```bash
# Build and start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

## 📁 Project Structure

```
Agent_Trader/
├── docker-compose.yml          # Docker services configuration
├── Dockerfile                  # Application container
├── requirements.txt           # Python dependencies
├── env.template              # Environment template
├── .dockerignore             # Docker build exclusions
└── docker/
    └── postgres/
        ├── init.sql          # Database initialization
        └── postgresql.conf   # PostgreSQL configuration
```

## 🐳 Docker Services

### 1. Trading Agent
- **Image**: Built from local Dockerfile
- **Port**: 8000 (HTTP API)
- **Dependencies**: PostgreSQL
- **Health Check**: Built-in endpoint

### 2. PostgreSQL
- **Image**: postgres:15-alpine
- **Port**: 5432
- **Volume**: Persistent data storage
- **Configuration**: Optimized for trading data

## 🔧 Configuration Details

### Environment Variables

**Required:**
- `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`: Alpaca trading API
- `TIINGO_API_KEY`: News and market data
- `OPENAI_API_KEY` or `DEEPSEEK_API_KEY`: LLM provider
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`: Bot control
- `POSTGRES_PASSWORD`: Database password

**Optional:**
- `LOG_LEVEL`: DEBUG, INFO, WARNING, ERROR (default: INFO)
- `ENVIRONMENT`: development, production (default: production)
- `MAX_POSITION_SIZE`: Max position as fraction (default: 0.1)

### Docker Compose Configuration

```yaml
version: '3.8'

services:
  trading-agent:
    build: .
    container_name: trading-agent
    restart: unless-stopped
    depends_on:
      - postgres
    env_file:
      - .env
    environment:
      - DATABASE_URL=postgresql://trader:${POSTGRES_PASSWORD}@postgres:5432/trading_agent
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
    ports:
      - "8000:8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import sys; sys.exit(0)"]
      interval: 30s
      timeout: 10s
      retries: 3

  postgres:
    image: postgres:15-alpine
    container_name: trading-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: trading_agent
      POSTGRES_USER: trader
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./docker/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U trader -d trading_agent"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  postgres_data:
    driver: local
```

## 🚀 Deployment Commands

### Basic Operations

```bash
# Start all services
docker-compose up -d

# Start with logs
docker-compose up

# Stop services
docker-compose down

# Restart specific service
docker-compose restart trading-agent

# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f trading-agent
```

### Scaling

```bash
# Scale application instances
docker-compose up -d --scale trading-agent=2

# Note: Database cannot be scaled this way
```

### Updates

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose build
docker-compose up -d
```

## 🔍 Monitoring and Health Checks

### Application Health

```bash
# Check service status
docker-compose ps

# Application health endpoint
curl http://localhost:8000/health

# View resource usage
docker stats
```

### Database Health

```bash
# Check database connectivity
docker-compose exec postgres pg_isready -U trader

# Connect to database
docker-compose exec postgres psql -U trader -d trading_agent

# View database logs
docker-compose logs postgres
```

### Log Monitoring

```bash
# Real-time logs
docker-compose logs -f

# Application logs only
docker-compose logs -f trading-agent

# Recent logs
docker-compose logs --tail=100 trading-agent
```

## 🔐 Backup and Recovery

### Database Backup

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup database
docker-compose exec -T postgres pg_dump -U trader trading_agent > $BACKUP_DIR/backup_$DATE.sql

# Compress backup
gzip $BACKUP_DIR/backup_$DATE.sql

echo "Backup created: $BACKUP_DIR/backup_$DATE.sql.gz"
```

### Database Restore

```bash
#!/bin/bash
# restore.sh

BACKUP_FILE=$1

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: ./restore.sh <backup_file.sql>"
    exit 1
fi

# Stop application
docker-compose stop trading-agent

# Restore database
docker-compose exec -T postgres psql -U trader -d trading_agent < $BACKUP_FILE

# Start application
docker-compose start trading-agent

echo "Database restored from: $BACKUP_FILE"
```

### Automated Backups

Add to crontab:

```bash
# Daily backup at 2 AM
0 2 * * * /path/to/Agent_Trader/backup.sh

# Weekly cleanup (keep 30 days)
0 3 * * 0 find /path/to/Agent_Trader/backups -name "backup_*.sql.gz" -mtime +30 -delete
```

## 🚨 Troubleshooting

### Common Issues

1. **Application fails to start**:
   ```bash
   # Check logs
   docker-compose logs trading-agent
   
   # Verify environment variables
   docker-compose exec trading-agent env | grep API
   
   # Check database connection
   docker-compose exec trading-agent python -c "from src.trading_system import TradingSystem; print('OK')"
   ```

2. **Database connection errors**:
   ```bash
   # Check database status
   docker-compose logs postgres
   
   # Verify database is ready
   docker-compose exec postgres pg_isready -U trader
   
   # Check network connectivity
   docker-compose exec trading-agent ping postgres
   ```

3. **API authentication errors**:
   - Verify API keys in `.env` file
   - Check for trailing spaces or special characters
   - Ensure API keys have correct permissions
   - Test APIs individually

4. **Memory issues**:
   ```bash
   # Check resource usage
   docker stats
   
   # Increase Docker memory limit if needed
   # Optimize application settings
   ```

### Debug Mode

Enable debug logging:

```bash
# Set in .env
LOG_LEVEL=DEBUG

# Restart services
docker-compose restart trading-agent

# View debug logs
docker-compose logs -f trading-agent
```

### Container Access

```bash
# Access application container
docker-compose exec trading-agent bash

# Access database container
docker-compose exec postgres bash

# Run commands in container
docker-compose exec trading-agent python -c "from config import settings; print(settings.alpaca_api_key)"
```

## 📊 Performance Optimization

### Resource Requirements

**Minimum:**
- RAM: 512MB
- CPU: 1 core
- Storage: 2GB

**Recommended:**
- RAM: 1GB
- CPU: 2 cores
- Storage: 10GB

### Application Tuning

```bash
# Environment optimizations in .env
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1

# Database optimizations
POSTGRES_SHARED_BUFFERS=256MB
POSTGRES_EFFECTIVE_CACHE_SIZE=1GB
```

### Docker Optimizations

```dockerfile
# In Dockerfile - multi-stage build
FROM python:3.11-slim as builder
# Build dependencies

FROM python:3.11-slim as runtime
# Runtime only
```

## 🔒 Security Best Practices

### Environment Security

- Store sensitive data in `.env` file
- Never commit `.env` to version control
- Use strong database passwords
- Regularly rotate API keys

### Container Security

- Run containers as non-root user
- Use specific image tags, not `latest`
- Regularly update base images
- Limit container resources

### Network Security

- Use Docker internal networks
- Expose only necessary ports
- Consider using reverse proxy
- Implement SSL/TLS in production

## 📈 Production Deployment

### Recommended Setup

```bash
# Production environment variables
ENVIRONMENT=production
LOG_LEVEL=INFO
ALPACA_BASE_URL=https://api.alpaca.markets  # Live trading

# Production compose override
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Load Balancing

For multiple instances, use nginx:

```nginx
upstream trading_app {
    server localhost:8000;
    server localhost:8001;
}

server {
    listen 80;
    location / {
        proxy_pass http://trading_app;
    }
}
```

### Monitoring

- Set up log aggregation
- Monitor resource usage
- Configure alerts for failures
- Regular health checks

## 💡 Tips and Best Practices

1. **Development**: Use paper trading and debug logging
2. **Testing**: Validate all API connections before going live
3. **Production**: Use live trading URLs and minimal logging
4. **Monitoring**: Set up alerts for critical failures
5. **Backups**: Automate daily database backups
6. **Updates**: Test updates in staging environment first

---

**Note**: This deployment uses in-memory events for simplicity and performance. For distributed deployments requiring persistent event storage, consider implementing database-backed event persistence. 