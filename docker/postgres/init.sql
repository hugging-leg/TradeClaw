-- Trading Agent Database Initialization Script

-- Create database extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create trading-related tables
CREATE TABLE IF NOT EXISTS positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    market_value DECIMAL(20, 2) NOT NULL,
    avg_entry_price DECIMAL(20, 8) NOT NULL,
    unrealized_pnl DECIMAL(20, 2) NOT NULL,
    side VARCHAR(5) NOT NULL CHECK (side IN ('long', 'short')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol)
);

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(10) NOT NULL,
    side VARCHAR(4) NOT NULL CHECK (side IN ('buy', 'sell')),
    order_type VARCHAR(20) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8),
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    time_in_force VARCHAR(10) NOT NULL DEFAULT 'day',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    alpaca_order_id VARCHAR(100),
    filled_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trading_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(10) NOT NULL,
    action VARCHAR(10) NOT NULL CHECK (action IN ('buy', 'sell', 'hold')),
    quantity DECIMAL(20, 8),
    confidence DECIMAL(3, 2),
    reasoning TEXT,
    market_data JSONB,
    news_sentiment JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    total_value DECIMAL(20, 2) NOT NULL,
    cash DECIMAL(20, 2) NOT NULL,
    positions_value DECIMAL(20, 2) NOT NULL,
    day_pnl DECIMAL(20, 2) NOT NULL,
    total_pnl DECIMAL(20, 2) NOT NULL,
    positions JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(50) NOT NULL,
    data JSONB NOT NULL,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS news_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    url VARCHAR(1000),
    source VARCHAR(100),
    symbols VARCHAR(100)[],
    sentiment DECIMAL(3, 2),
    published_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(url)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_trading_decisions_symbol ON trading_decisions(symbol);
CREATE INDEX IF NOT EXISTS idx_trading_decisions_created_at ON trading_decisions(created_at);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_created_at ON portfolio_snapshots(created_at);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_processed ON events(processed);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);
CREATE INDEX IF NOT EXISTS idx_news_items_symbols ON news_items USING GIN(symbols);
CREATE INDEX IF NOT EXISTS idx_news_items_published_at ON news_items(published_at);

-- Create update triggers for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_positions_updated_at BEFORE UPDATE ON positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_orders_updated_at BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create views for common queries
CREATE OR REPLACE VIEW active_positions AS
SELECT * FROM positions WHERE quantity != 0;

CREATE OR REPLACE VIEW open_orders AS
SELECT * FROM orders WHERE status IN ('pending', 'submitted', 'partially_filled');

CREATE OR REPLACE VIEW recent_decisions AS
SELECT * FROM trading_decisions WHERE created_at >= CURRENT_DATE - INTERVAL '7 days';

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO trader;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO trader;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO trader; 