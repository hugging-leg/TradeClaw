# Assets Directory

This directory contains project assets including diagrams and images.

## 📁 Directory Structure

```
assets/
├── diagrams/                    # Mermaid source files
│   ├── system-architecture.mmd
│   └── workflow-flow.mmd
└── images/
    └── diagrams/                # Generated diagram images
        ├── system-architecture.svg
        └── workflow-flow.svg
```

## 🎨 Diagrams

### Source Files (`assets/diagrams/`)
- `system-architecture.mmd` - Complete system architecture diagram
- `workflow-flow.mmd` - Workflow process diagram

### Generated Images (`assets/images/diagrams/`)
- SVG files for crisp vector graphics and web display

## 🔧 Generation

Run the generation scripts to create SVG images from Mermaid source files:

```bash
# Linux/macOS
./scripts/generate-diagrams.sh

# Windows
scripts\generate-diagrams.bat
``` 