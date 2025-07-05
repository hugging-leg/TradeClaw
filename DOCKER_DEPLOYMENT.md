# Docker Deployment Guide

This guide explains how to deploy the LLM Trading Agent using Docker and Docker Compose.

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- At least 2GB RAM
- At least 5GB free disk space

## Quick Start

1. **Clone and setup environment**:
   ```bash
   git clone <repository-url>
   cd Agent_Trader
   cp env.template .env
   ```

2. **Configure environment variables**:
   Edit `.env` file with your API keys and configuration

3. **Start the services**:
   ```bash
   # Basic deployment (trading agent + PostgreSQL, no Redis)
   docker-compose up -d
   
   # With Redis (for distributed events and caching)
   docker-compose --profile redis up -d
   ```

4. **Check service status**:
   ```bash
   docker-compose ps
   docker-compose logs -f trading-agent
   ```

## Configuration

### Environment Variables

Copy `env.template` to `.env` and configure:

```bash
# Required API Keys
ALPACA_API_KEY=your_alpaca_api_key
ALPACA_SECRET_KEY=your_alpaca_secret_key
TIINGO_API_KEY=your_tiingo_api_key
OPENAI_API_KEY=your_openai_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Database Configuration
POSTGRES_PASSWORD=secure_postgres_password

# Redis Configuration (Optional)
REDIS_URL=redis://redis:6379/0
REDIS_PASSWORD=secure_redis_password
USE_REDIS=true  # Set to false to use in-memory events
```

### Service Profiles

The docker-compose.yml includes different service profiles:

- **Default**: Core services (trading-agent, postgres)
- **redis**: Adds Redis for distributed events and caching

## Service Architecture

### Basic Deployment (Default)
```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Network                           │
│                                                             │
│       ┌─────────────────────────────────────────────┐       │
│       │              Trading Agent                  │       │
│       │            (main application)               │       │
│       │                  :8000                      │       │
│       └─────────────────────┬───────────────────────┘       │
│                             │                               │
│                             ▼                               │
│       ┌─────────────────────────────────────────────┐       │
│       │              PostgreSQL                     │       │
│       │              (database)                     │       │
│       │                :5432                        │       │
│       └─────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### With Redis Profile
```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Network                           │
│                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐ │
│  │  Trading Agent  │    │     Redis       │    │ PostgreSQL  │ │
│  │  (main app)     │◄──►│   (events)      │    │ (database)  │ │
│  │     :8000       │    │    :6379        │    │   :5432     │ │
│  └─────────────────┘    └─────────────────┘    └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Deployment Commands

### Basic Deployment
```bash
# Start core services (Trading Agent + PostgreSQL)
docker-compose up -d

# View logs
docker-compose logs -f trading-agent

# Stop services
docker-compose down
```

### With Redis
```bash
# Start with Redis for distributed events
docker-compose --profile redis up -d

# View all logs
docker-compose --profile redis logs -f

# Stop services
docker-compose --profile redis down
```

## Volume Management

The system uses Docker volumes for data persistence:

- `postgres_data`: Database files
- `redis_data`: Redis persistence (when using Redis profile)

### Backup Data
```bash
# Backup PostgreSQL
docker exec trading-postgres pg_dump -U trader trading_agent > backup.sql

# Backup Redis (only when using Redis profile)
docker exec trading-redis redis-cli SAVE
docker cp trading-redis:/data/dump.rdb ./redis_backup.rdb

# List all volumes
docker volume ls
```

### Restore Data
```bash
# Restore PostgreSQL
docker exec -i trading-postgres psql -U trader trading_agent < backup.sql

# Restore Redis (only when using Redis profile)
docker cp ./redis_backup.rdb trading-redis:/data/dump.rdb
docker restart trading-redis
```

## Health Checks

All services include health checks:

```bash
# Check service health
docker-compose ps

# View health check logs
docker inspect trading-agent | grep -A 10 Health
```

## Troubleshooting

### Common Issues

1. **Service won't start**:
   ```bash
   # Check logs
   docker-compose logs service-name
   
   # Check environment variables
   docker-compose config
   ```

2. **Database connection issues**:
   ```bash
   # Check PostgreSQL logs
   docker-compose logs postgres
   
   # Test connection
   docker exec -it trading-postgres psql -U trader -d trading_agent
   ```

3. **Redis connection issues** (when using Redis profile):
   ```bash
   # Check Redis logs
   docker-compose --profile redis logs redis
   
   # Test connection
   docker exec -it trading-redis redis-cli ping
   ```

4. **Events not working**:
   ```bash
   # Check USE_REDIS environment variable
   docker-compose exec trading-agent env | grep USE_REDIS
   
   # Check Redis URL if using Redis
   docker-compose exec trading-agent env | grep REDIS_URL
   ```

### Debug Mode

Enable debug mode for detailed logging:

```bash
# Set LOG_LEVEL=DEBUG in .env
echo "LOG_LEVEL=DEBUG" >> .env

# Restart services
docker-compose restart trading-agent

# For Redis profile
docker-compose --profile redis restart trading-agent
```

## Security Considerations

1. **Use strong passwords** for database and Redis
2. **Secure environment variables** in .env file
3. **Configure firewall** rules to restrict access
4. **Regular security updates**:
   ```bash
   # Update base images
   docker-compose pull
   docker-compose up -d
   ```
5. **Network isolation** - services communicate through Docker internal network



## Maintenance

### Regular Tasks
```bash
# Weekly: Update images
docker-compose pull
docker-compose up -d

# Monthly: Clean up unused data
docker system prune -a

# Backup important data
docker exec trading-postgres pg_dump -U trader trading_agent > backup_$(date +%Y%m%d).sql
```

### Log Rotation
```bash
# Configure in docker-compose.yml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

## Performance Tuning

### Resource Usage
- **Basic**: ~500MB RAM, minimal CPU
- **With Redis**: ~1GB RAM, moderate CPU

### Database Optimization
The PostgreSQL configuration is already optimized for trading workloads. You can further tune settings in `docker/postgres/postgresql.conf`.

## Accessing the Application

- **Trading Agent**: http://localhost:8000
- **PostgreSQL**: localhost:5432 (for database access)
- **Redis**: localhost:6379 (when using Redis profile)

## Differences Between Deployment Options

### Basic Deployment (Default)
- ✅ **All trading functionality**
- ✅ **AI decision making**
- ✅ **Telegram bot**
- ✅ **Data persistence**
- ✅ **In-memory events**
- ❌ **No distributed events**
- ❌ **No event history**

### With Redis Profile
- ✅ **All basic features**
- ✅ **Distributed events**
- ✅ **Event history**
- ✅ **Better performance for multiple instances**
- ✅ **Caching capabilities**

## When to Use Each Option

### Use Basic Deployment When:
- Development/testing
- Single instance deployment
- Limited resources
- Simple setup preferred

### Use Redis Profile When:
- Production deployment
- Need event history
- Multiple instances
- Better performance requirements

## Support

For issues and questions:
1. Check the logs: 
   - Basic: `docker-compose logs`
   - With Redis: `docker-compose --profile redis logs`
2. Review the troubleshooting section
3. Check the main documentation
4. Submit an issue with log files and configuration details

## Migration Between Deployment Options

### From Basic to Redis Profile
```bash
# Stop current deployment
docker-compose down

# Start with Redis
docker-compose --profile redis up -d

# Data is preserved (PostgreSQL volume is shared)
```

### From Redis Profile to Basic
```bash
# Stop Redis deployment
docker-compose --profile redis down

# Start basic deployment
docker-compose up -d

# Update environment variables if needed
# Set USE_REDIS=false in .env
``` 