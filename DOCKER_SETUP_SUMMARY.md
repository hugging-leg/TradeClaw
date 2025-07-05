# 🐳 Docker Setup Summary

## 📋 Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                LLM Trading Agent                    │
│          (In-Memory Event System)                   │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│                PostgreSQL                           │
│              (Data Storage)                         │
└─────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### 1. Basic Deployment
```bash
# Clone and navigate
git clone <repository>
cd Agent_Trader

# Build and start
docker-compose up -d

# Check status
docker-compose ps
```

## 📁 Project Structure

```
docker/
│   └── postgres/
│       ├── init.sql          # Database initialization
│       └── postgresql.conf   # PostgreSQL configuration

└── src/                      # Application source code
```

## 🐳 Docker Services

| Service | Purpose | Port | Status |
|---------|---------|------|--------|
| **Trading Agent** | Main application | 8000 | Required |
| **PostgreSQL** | Database | 5432 | Required |

## ❌ Removed Components

The following components have been removed in favor of simpler in-memory alternatives:
- Redis (replaced with in-memory event system)
- Complex caching layers
- Distributed event handling

## 🔧 Environment Configuration

Copy and configure your environment:

```bash
cp env.template .env
```

Required configuration:
```bash
# Trading APIs
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
TIINGO_API_KEY=your_key

# LLM Provider
LLM_PROVIDER=openai  # or deepseek
OPENAI_API_KEY=your_key  # if using OpenAI
DEEPSEEK_API_KEY=your_key  # if using DeepSeek

# Telegram
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

# Database
POSTGRES_PASSWORD=secure_password

```

## 🚀 Deployment Commands

### Start Services
```bash
# Start all services
docker-compose up -d

# Start with logs
docker-compose up

# Scale the application
docker-compose up -d --scale app=2
```

### Management
```bash
# View logs
docker-compose logs -f

# Restart application
docker-compose restart app

# Stop services
docker-compose down

# Clean up (removes volumes)
docker-compose down -v
```

### Monitoring
```bash
# Check service status
docker-compose ps

# Monitor resource usage
docker stats

# View application logs
docker-compose logs app

# View database logs
docker-compose logs postgres
```

## 🔍 Troubleshooting

### Common Issues

1. **Application won't start**:
   ```bash
   # Check logs
   docker-compose logs app
   
   # Verify environment
   docker-compose exec app env | grep API
   ```

2. **Database connection issues**:
   ```bash
   # Check database status
   docker-compose logs postgres
   
   # Test connection
   docker-compose exec postgres psql -U trader -d trading_agent
   ```

3. **API authentication errors**:
   - Verify API keys in `.env`
   - Check API key permissions
   - Ensure no trailing spaces in environment variables

### Health Checks
```bash
# Application health
curl http://localhost:8000/health

# Database connection
docker-compose exec postgres pg_isready -U trader
```

## 📊 Performance

### Resource Requirements
- **Minimal**: 512MB RAM, 1 CPU core
- **Recommended**: 1GB RAM, 2 CPU cores
- **Storage**: 5GB minimum for logs and database

### Ports Used
- **Application**: localhost:8000
- **PostgreSQL**: localhost:5432

## 🔄 Updates and Maintenance

### Update Application
```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose build
docker-compose up -d
```

### Backup Database
```bash
# Create backup
docker-compose exec postgres pg_dump -U trader trading_agent > backup.sql

# Restore backup
docker-compose exec -T postgres psql -U trader trading_agent < backup.sql
```

## 📈 Scaling

### Horizontal Scaling
- Deploy multiple application instances
- Use load balancer (nginx)
- Shared database for state

### Monitoring
- Built-in health checks
- Application metrics via logs
- Database monitoring with PostgreSQL tools

---

**Note**: This setup uses in-memory events for simplicity. For distributed deployments, consider implementing database-backed event storage if needed. 