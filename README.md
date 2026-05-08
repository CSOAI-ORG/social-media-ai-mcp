<div align="center">

# Social Media Ai MCP

**Social Media AI MCP Server - Content & Engagement Intelligence**

[![PyPI](https://img.shields.io/pypi/v/meok-social-media-ai-mcp)](https://pypi.org/project/meok-social-media-ai-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MEOK AI Labs](https://img.shields.io/badge/MEOK_AI_Labs-MCP_Server-purple)](https://meok.ai)

</div>

## Overview

Social Media AI MCP Server - Content & Engagement Intelligence
Built by MEOK AI Labs | https://meok.ai

Post scheduling, hashtag generation, engagement analysis,
content calendar planning, and audience insights.

## Tools

| Tool | Description |
|------|-------------|
| `schedule_post` | Schedule a social media post with optimal timing suggestions. |
| `generate_hashtags` | Generate relevant hashtags for a social media post. |
| `analyze_engagement` | Analyze engagement metrics across posts to identify top performers. |
| `plan_content_calendar` | Generate a content calendar with post ideas and optimal scheduling. |
| `get_audience_insights` | Generate audience insights and growth recommendations. |

## Installation

```bash
pip install meok-social-media-ai-mcp
```

## Usage with Claude Desktop

Add to your Claude Desktop MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "social-media-ai": {
      "command": "python",
      "args": ["-m", "meok_social_media_ai_mcp.server"]
    }
  }
}
```

## Usage with FastMCP

```python
from mcp.server.fastmcp import FastMCP

# This server exposes 5 tool(s) via MCP
# See server.py for full implementation
```

## License

MIT © [MEOK AI Labs](https://meok.ai)
