#!/bin/bash

# AI Trading Agent - Diagram Generation Script
# This script converts Mermaid diagrams to SVG format

echo "🎨 AI Trading Agent - Diagram Generation"
echo "========================================"

# Check if mmdc (mermaid-cli) is installed
if ! command -v mmdc &> /dev/null; then
    echo "❌ Error: mermaid-cli (mmdc) is not installed"
    echo "📦 Install it with: npm install -g @mermaid-js/mermaid-cli"
    exit 1
fi

# Create output directory
mkdir -p assets/images/diagrams

echo "📁 Created output directory"

# Convert system architecture diagram to SVG
echo "🔧 Converting system architecture diagram..."
mmdc -i assets/diagrams/system-architecture.mmd -o assets/images/diagrams/system-architecture.svg -p assets/puppeteer-config.json

# Convert workflow diagram to SVG
echo "🔄 Converting workflow diagram..."
mmdc -i assets/diagrams/workflow-flow.mmd -o assets/images/diagrams/workflow-flow.svg -p assets/puppeteer-config.json

echo "✅ All diagrams generated successfully!"
echo ""
echo "📂 Generated files in: assets/images/diagrams/"
echo "   - system-architecture.svg"
echo "   - workflow-flow.svg" 