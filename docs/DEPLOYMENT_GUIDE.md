# 🚀 Deployment Guide

This guide covers deploying the LLM Trading Agent in production environments with proper security, monitoring, and reliability considerations.

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Production Environment                    │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   Load Balancer │   Web Gateway   │      Application Layer      │
│    (nginx)      │    (FastAPI)    │    (Trading System)         │
└─────────────────┴─────────────────┴─────────────────────────────┘
├─────────────────┬─────────────────┬─────────────────────────────┤
│   Database      │   Cache Layer   │      Message Queue          │
│  (PostgreSQL)   │    (Events)     │      (Message Queue)        │
└─────────────────┴─────────────────┴─────────────────────────────┘
├─────────────────┬─────────────────┬─────────────────────────────┤
│   Monitoring    │     Logging     │       Backup & Recovery     │
│ (Prometheus)    │  (ELK Stack)    │      (S3/BackBlaze)         │
└─────────────────┴─────────────────┴─────────────────────────────┘
```

## 🎯 Deployment Options

### Option 1: Single Server Deployment (Small Scale)

Suitable for:
- Personal trading systems
- Small portfolios (< $100k)
- Testing environments

**Requirements:**
- 4+ CPU cores
- 8+ GB RAM
- 100+ GB SSD storage
- Reliable internet connection

### Option 2: Multi-Server Deployment (Enterprise)

Suitable for:
- Multiple trading strategies
- Large portfolios (> $500k)
- High availability requirements

**Requirements:**
- Load balancer
- Multiple application servers
- Dedicated database server

- Monitoring infrastructure

### Option 3: Cloud Deployment (AWS/GCP/Azure)

Suitable for:
- Scalable requirements
- Global deployment
- Managed services preference

**Services Used:**
- Container orchestration (EKS/GKE/AKS)
- Managed databases (RDS/Cloud SQL)
- Managed cache (ElastiCache/MemoryStore)
- Monitoring (CloudWatch/Stackdriver)

## 🐳 Docker Deployment

### 1. Create Dockerfile

```dockerfile
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 trader && \
    chown -R trader:trader /app
USER trader

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start command
CMD ["python", "main.py"]
```

### 2. Create docker-compose.yml

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env.production
    depends_on:
      - postgres
    restart: unless-stopped
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
    networks:
      - trading-network



  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: trading_agent
      POSTGRES_USER: trader
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    restart: unless-stopped
    networks:
      - trading-network

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - app
    restart: unless-stopped
    networks:
      - trading-network

volumes:
  postgres_data:

networks:
  trading-network:
    driver: bridge
```

### 3. Build and Deploy

```bash
# Build the image
docker-compose build

# Start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f app
```

## ☁️ Kubernetes Deployment

### 1. Create Kubernetes Manifests

**namespace.yaml:**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: trading-system
```

**configmap.yaml:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: trading-config
  namespace: trading-system
data:
  ENVIRONMENT: "production"
  LOG_LEVEL: "INFO"
  REBALANCE_TIME: "09:30"
  MAX_POSITION_SIZE: "0.1"
```

**secret.yaml:**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: trading-secrets
  namespace: trading-system
type: Opaque
stringData:
  ALPACA_API_KEY: "your_key"
  ALPACA_SECRET_KEY: "your_secret"
  OPENAI_API_KEY: "your_key"
  TELEGRAM_BOT_TOKEN: "your_token"
```

**deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: trading-system
  namespace: trading-system
spec:
  replicas: 2
  selector:
    matchLabels:
      app: trading-system
  template:
    metadata:
      labels:
        app: trading-system
    spec:
      containers:
      - name: trading-system
        image: trading-agent:latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: trading-config
        - secretRef:
            name: trading-secrets
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
```

### 2. Deploy to Kubernetes

```bash
# Apply manifests
kubectl apply -f k8s/

# Check deployment
kubectl get pods -n trading-system

# Check logs
kubectl logs -f deployment/trading-system -n trading-system
```

## 🔒 Security Configuration

### 1. Environment Variables

Create `.env.production` with production values:

```bash
# Trading APIs (Production)
ALPACA_API_KEY=prod_api_key
ALPACA_SECRET_KEY=prod_secret_key
ALPACA_BASE_URL=https://api.alpaca.markets  # Live trading
TIINGO_API_KEY=prod_tiingo_key

# OpenAI
OPENAI_API_KEY=prod_openai_key
OPENAI_MODEL=gpt-4o

# Telegram
TELEGRAM_BOT_TOKEN=prod_bot_token
TELEGRAM_CHAT_ID=prod_chat_id

# Database
DATABASE_URL=postgresql://trader:secure_password@postgres:5432/trading_agent



# Security
ENVIRONMENT=production
LOG_LEVEL=WARNING
```

### 2. SSL/TLS Configuration

**nginx.conf:**
```nginx
events {
    worker_connections 1024;
}

http {
    upstream app {
        server app:8000;
    }

    server {
        listen 80;
        server_name yourdomain.com;
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name yourdomain.com;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;

        location / {
            proxy_pass http://app;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

### 3. Firewall Configuration

```bash
# Allow only necessary ports
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw deny incoming
ufw allow outgoing
ufw enable
```

## 📊 Monitoring and Logging

### 1. Prometheus Monitoring

**prometheus.yml:**
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'trading-system'
    static_configs:
      - targets: ['app:8000']
```

### 2. Grafana Dashboard

Create custom dashboards for:
- System metrics (CPU, memory, disk)
- Trading metrics (orders, portfolio value)
- API response times
- Error rates

### 3. Log Aggregation

**filebeat.yml:**
```yaml
filebeat.inputs:
- type: log
  enabled: true
  paths:
    - /app/logs/*.log

output.elasticsearch:
  hosts: ["elasticsearch:9200"]

setup.kibana:
  host: "kibana:5601"
```

## 🔄 CI/CD Pipeline

### 1. GitHub Actions Workflow

**.github/workflows/deploy.yml:**
```yaml
name: Deploy Trading System

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.9
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    - name: Run tests
      run: |
        python -m pytest tests/

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Build and push Docker image
      run: |
        docker build -t trading-agent:${{ github.sha }} .
        docker tag trading-agent:${{ github.sha }} trading-agent:latest
        # Push to registry
    - name: Deploy to production
      run: |
        # Deploy using your preferred method
```

## 🔧 Database Setup

### 1. PostgreSQL Configuration

**init.sql:**
```sql
-- Create database and user
CREATE DATABASE trading_agent;
CREATE USER trader WITH ENCRYPTED PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE trading_agent TO trader;

-- Create tables
\c trading_agent;

CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    side VARCHAR(4) NOT NULL,
    quantity DECIMAL(10,2) NOT NULL,
    price DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio_history (
    id SERIAL PRIMARY KEY,
    equity DECIMAL(15,2) NOT NULL,
    cash DECIMAL(15,2) NOT NULL,
    day_pnl DECIMAL(15,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_created_at ON trades(created_at);
CREATE INDEX idx_portfolio_created_at ON portfolio_history(created_at);
```



## 🔐 Backup and Recovery

### 1. Database Backup

```bash
#!/bin/bash
# backup.sh

DB_NAME="trading_agent"
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup
pg_dump $DB_NAME > $BACKUP_DIR/backup_$DATE.sql

# Compress
gzip $BACKUP_DIR/backup_$DATE.sql

# Upload to S3 (optional)
aws s3 cp $BACKUP_DIR/backup_$DATE.sql.gz s3://your-backup-bucket/

# Clean old backups (keep 30 days)
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +30 -delete
```

### 2. Automated Backup Schedule

**crontab:**
```bash
# Database backup every 6 hours
0 */6 * * * /scripts/backup.sh

# Log rotation
0 1 * * * /usr/sbin/logrotate /etc/logrotate.conf
```

## 🚨 Health Checks and Alerts

### 1. Health Check Endpoint

Add to your application:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check database connection
        # Check API connections
        return {"status": "healthy", "timestamp": datetime.now()}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.get("/ready")
async def readiness_check():
    """Readiness check for load balancer"""
    # Check if system is ready to accept requests
    return {"status": "ready"}
```

### 2. Alerting Rules

**alert_rules.yml:**
```yaml
groups:
- name: trading_system
  rules:
  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
    for: 5m
    annotations:
      summary: "High error rate detected"

  - alert: DatabaseDown
    expr: up{job="postgres"} == 0
    for: 1m
    annotations:
      summary: "Database is down"

  - alert: HighMemoryUsage
    expr: container_memory_usage_bytes / container_spec_memory_limit_bytes > 0.9
    for: 5m
    annotations:
      summary: "High memory usage"
```

## 🎯 Performance Optimization

### 1. Application Tuning

```python
# In main.py
import asyncio
import uvloop

# Use uvloop for better performance
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

# Optimize database connections
DATABASE_POOL_SIZE = 20
DATABASE_MAX_OVERFLOW = 30
```

### 2. Database Optimization

```sql
-- Optimize PostgreSQL
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
SELECT pg_reload_conf();
```



## 📈 Scaling Considerations

### 1. Horizontal Scaling

- Use load balancer (nginx/HAProxy)
- Deploy multiple application instances
- Implement sticky sessions for Telegram bot


### 2. Vertical Scaling

- Monitor resource usage
- Scale CPU/memory as needed
- Use SSD storage for databases
- Optimize garbage collection

### 3. Auto-scaling

```yaml
# Kubernetes HPA
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: trading-system-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: trading-system
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

## 🎉 Deployment Checklist

### Pre-deployment

- [ ] All tests passing
- [ ] Security review completed
- [ ] Backup procedures tested
- [ ] Monitoring configured
- [ ] SSL certificates installed
- [ ] Environment variables configured
- [ ] Database migrations applied

### Deployment

- [ ] Deploy to staging first
- [ ] Run smoke tests
- [ ] Deploy to production
- [ ] Verify health checks
- [ ] Test Telegram bot functionality
- [ ] Verify trading system operation

### Post-deployment

- [ ] Monitor system metrics
- [ ] Check error logs
- [ ] Verify trading operations
- [ ] Test alert systems
- [ ] Document any issues
- [ ] Update runbooks

---

This deployment guide provides a comprehensive approach to deploying the LLM Trading Agent in production environments. Always test thoroughly in staging before deploying to production, and never trade with money you can't afford to lose. 