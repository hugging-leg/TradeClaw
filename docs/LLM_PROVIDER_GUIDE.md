# LLM Provider Configuration Guide

This guide explains how to configure and use different LLM providers with the Trading Agent.

## Supported Providers

### OpenAI (Default)
- **Provider**: OpenAI
- **Models**: GPT-4, GPT-3.5-turbo, GPT-4o, etc.
- **API**: OpenAI API
- **Cost**: Variable pricing based on model and usage

### DeepSeek
- **Provider**: DeepSeek
- **Models**: deepseek-chat, deepseek-coder, etc.
- **API**: DeepSeek API (OpenAI-compatible)
- **Cost**: Generally more cost-effective than OpenAI

## Configuration

### Environment Variables

Set these environment variables in your `.env` file:

```bash
# LLM Provider Selection
LLM_PROVIDER=openai  # or "deepseek"

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o

# DeepSeek Configuration
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_MODEL=deepseek-chat
```

### Configuration Options

#### OpenAI
```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o          # or gpt-4, gpt-3.5-turbo, etc.
```

#### DeepSeek
```bash
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_deepseek_key
DEEPSEEK_MODEL=deepseek-chat  # or deepseek-coder
```

## Getting API Keys

### OpenAI API Key
1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Sign up or log in
3. Navigate to API Keys section
4. Create a new API key
5. Copy the key to your `.env` file

### DeepSeek API Key
1. Go to [DeepSeek Platform](https://platform.deepseek.com/)
2. Sign up or log in
3. Navigate to API Keys section
4. Create a new API key
5. Copy the key to your `.env` file

## Model Recommendations

### For Trading (Recommended)

#### OpenAI
- **GPT-4o**: Best balance of performance and cost
- **GPT-4**: Highest quality reasoning
- **GPT-3.5-turbo**: Most cost-effective

#### DeepSeek
- **deepseek-chat**: General purpose, good for trading analysis
- **deepseek-coder**: Better for technical analysis

### Cost Considerations

| Provider | Model | Cost (per 1M tokens) | Use Case |
|----------|-------|---------------------|----------|
| OpenAI | GPT-4o | $15-30 | Production |
| OpenAI | GPT-4 | $30-60 | High-quality analysis |
| OpenAI | GPT-3.5-turbo | $1-2 | Development/testing |
| DeepSeek | deepseek-chat | $0.14-0.28 | Cost-effective production |

## Usage Examples

### Switch to DeepSeek
```bash
# Update .env file
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_deepseek_key
DEEPSEEK_MODEL=deepseek-chat

# Restart the trading agent
python main.py
```

### Switch to OpenAI
```bash
# Update .env file
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4o

# Restart the trading agent
python main.py
```

## Performance Comparison

### Trading Decision Quality
- **OpenAI GPT-4/4o**: Excellent reasoning, nuanced market analysis
- **DeepSeek**: Good reasoning, cost-effective alternative

### Response Speed
- **OpenAI**: Generally faster API responses
- **DeepSeek**: Competitive response times

### Cost Efficiency
- **DeepSeek**: ~90% less expensive than OpenAI
- **OpenAI**: Higher cost but potentially better quality

## Troubleshooting

### Common Issues

#### "Unknown LLM provider" Error
```
WARNING - Unknown LLM provider: xyz. Defaulting to OpenAI.
```
**Solution**: Check `LLM_PROVIDER` in `.env` file. Valid values: `openai`, `deepseek`

#### DeepSeek Authentication Error
```
ERROR - Failed to initialize Alpaca API: Authentication failed
```
**Solution**: Verify `DEEPSEEK_API_KEY` is correct and account has credits

#### OpenAI Rate Limit
```
ERROR - OpenAI API rate limit exceeded
```
**Solution**: 
- Upgrade OpenAI plan
- Switch to DeepSeek temporarily
- Reduce trading frequency

### Testing Configuration

Run these commands to test your LLM configuration:

```bash
# Test with current configuration
python -c "
from src.agents.trading_workflow import create_llm_client
from config import settings
print(f'LLM Provider: {settings.llm_provider}')
client = create_llm_client()
print(f'Client: {type(client).__name__}')
"
```

## Advanced Configuration

### Custom Models
You can use custom models by updating the configuration:

```bash
# For OpenAI-compatible models
LLM_PROVIDER=openai
OPENAI_MODEL=custom-model-name

# For DeepSeek custom models
LLM_PROVIDER=deepseek
DEEPSEEK_MODEL=custom-deepseek-model
```

### Temperature Control
The trading agent uses `temperature=0.1` for consistent, conservative decisions. This is hardcoded for safety but can be modified in `src/agents/trading_workflow.py`.

## Best Practices

1. **Start with DeepSeek**: More cost-effective for initial testing
2. **Monitor Performance**: Track decision quality and trading results
3. **Budget Management**: Set API spending limits
4. **Fallback Configuration**: Keep both providers configured
5. **Regular Updates**: Update models as new versions become available

## Security

- Never commit API keys to version control
- Use environment variables for all sensitive data
- Regularly rotate API keys
- Monitor API usage for unusual activity
- Set spending limits on provider platforms

## Support

For issues with:
- **OpenAI**: Check [OpenAI Status](https://status.openai.com/)
- **DeepSeek**: Check [DeepSeek Documentation](https://platform.deepseek.com/docs)
- **Trading Agent**: Check logs in `logs/` directory 