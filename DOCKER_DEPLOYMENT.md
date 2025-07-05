# Docker Deployment Guide

This guide explains how to deploy the LLM Trading Agent using Docker and Docker Compose.

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- At least 4GB RAM
- At least 10GB free disk space

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
   # Basic deployment (trading agent, Redis, PostgreSQL)
   docker-compose up -d
   
   # With monitoring (adds Prometheus and Grafana)
   docker-compose --profile monitoring up -d
   
   # Production deployment (adds Nginx reverse proxy)
   docker-compose --profile production up -d
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

# Database Passwords
POSTGRES_PASSWORD=secure_postgres_password
REDIS_PASSWORD=secure_redis_password

# Optional Monitoring
GRAFANA_PASSWORD=grafana_admin_password
```

### Service Profiles

The docker-compose.yml includes different service profiles:

- **Default**: Core services (trading-agent, redis, postgres)
- **production**: Adds Nginx reverse proxy
- **monitoring**: Adds Prometheus and Grafana

## Service Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Network                           │
│                                                             │
│  ┌─────────────┐    ┌─────────────────┐    ┌─────────────┐ │
│  │    Nginx    │    │  Trading Agent  │    │   Redis     │ │
│  │   (proxy)   │◄──►│   (main app)    │◄──►│  (events)   │ │
│  │    :80/443  │    │      :8000      │    │    :6379    │ │
│  └─────────────┘    └─────────────────┘    └─────────────┘ │
│                             │                              │
│                             ▼                              │
│  ┌─────────────┐    ┌─────────────────┐    ┌─────────────┐ │
│  │  Grafana    │    │   PostgreSQL    │    │ Prometheus  │ │
│  │ (dashboard) │    │   (database)    │    │ (metrics)   │ │
│  │    :3000    │    │      :5432      │    │    :9090    │ │
│  └─────────────┘    └─────────────────┘    └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Deployment Commands

### Basic Deployment
```bash
# Start core services
docker-compose up -d

# View logs
docker-compose logs -f trading-agent

# Stop services
docker-compose down
```

### Production Deployment
```bash
# Start with reverse proxy
docker-compose --profile production up -d

# Scale trading agent (if needed)
docker-compose --profile production up -d --scale trading-agent=2

# Update services
docker-compose --profile production pull
docker-compose --profile production up -d
```

### Monitoring Deployment
```bash
# Start with monitoring
docker-compose --profile monitoring up -d

# Access Grafana
# URL: http://localhost:3000
# Username: admin
# Password: <GRAFANA_PASSWORD from .env>

# Access Prometheus
# URL: http://localhost:9090
```

## Volume Management

The system uses Docker volumes for data persistence:

- `postgres_data`: Database files
- `redis_data`: Redis persistence
- `prometheus_data`: Metrics data
- `grafana_data`: Dashboard configuration

### Backup Data
```bash
# Backup PostgreSQL
docker exec trading-postgres pg_dump -U trader trading_agent > backup.sql

# Backup Redis
docker exec trading-redis redis-cli SAVE
docker cp trading-redis:/data/dump.rdb ./redis_backup.rdb

# List all volumes
docker volume ls
```

### Restore Data
```bash
# Restore PostgreSQL
docker exec -i trading-postgres psql -U trader trading_agent < backup.sql

# Restore Redis
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

3. **Redis connection issues**:
   ```bash
   # Check Redis logs
   docker-compose logs redis
   
   # Test connection
   docker exec -it trading-redis redis-cli ping
   ```

4. **Out of memory**:
   ```bash
   # Check resource usage
   docker stats
   
   # Increase memory limits in docker-compose.yml
   ```

### Debug Mode

Enable debug mode for detailed logging:

```bash
# Set LOG_LEVEL=DEBUG in .env
echo "LOG_LEVEL=DEBUG" >> .env

# Restart services
docker-compose restart trading-agent
```

## Security Considerations

1. **Use strong passwords** for all services
2. **Enable SSL/TLS** for production deployments
3. **Configure firewall** rules to restrict access
4. **Regular security updates**:
   ```bash
   # Update base images
   docker-compose pull
   docker-compose up -d
   ```

## Performance Tuning

### Resource Limits
```yaml
# Add to docker-compose.yml services
deploy:
  resources:
    limits:
      cpus: '0.5'
      memory: 512M
    reservations:
      cpus: '0.25'
      memory: 256M
```

### Database Optimization
```bash
# Tune PostgreSQL settings in docker/postgres/postgresql.conf
shared_buffers = 256MB
effective_cache_size = 1GB
```

## Scaling

### Horizontal Scaling
```bash
# Scale trading agent
docker-compose up -d --scale trading-agent=3

# Use load balancer
docker-compose --profile production up -d
```

### Vertical Scaling
```bash
# Increase resource limits
# Edit docker-compose.yml memory and CPU limits
```

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

## Monitoring and Alerting

### Grafana Dashboards
- System metrics (CPU, memory, disk)
- Trading performance
- Database performance
- Redis metrics

### Prometheus Alerts
- High error rates
- System resource usage
- Database connection issues
- Trading anomalies

## Support

For issues and questions:
1. Check the logs: `docker-compose logs`
2. Review the troubleshooting section
3. Check the main documentation
4. Submit an issue with log files and configuration details 