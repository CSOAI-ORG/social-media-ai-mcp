# Social Media AI MCP Server

**Content & Engagement Intelligence**

Built by [MEOK AI Labs](https://meok.ai)

---

An MCP server for social media managers and content creators. Schedule posts at optimal times, generate hashtag strategies, analyze engagement metrics, plan content calendars, and get audience growth insights across Instagram, Twitter, LinkedIn, Facebook, and TikTok.

## Tools

| Tool | Description |
|------|-------------|
| `schedule_post` | Schedule posts with optimal timing suggestions per platform |
| `generate_hashtags` | Generate stratified hashtag sets by reach volume |
| `analyze_engagement` | Analyze engagement metrics to identify top-performing content |
| `plan_content_calendar` | Generate multi-week content calendars with topic rotation |
| `get_audience_insights` | Audience analysis with growth projections and content recommendations |

## Quick Start

```bash
pip install social-media-ai-mcp
```

### Claude Desktop

```json
{
  "mcpServers": {
    "social-media-ai": {
      "command": "python",
      "args": ["-m", "server"],
      "cwd": "/path/to/social-media-ai-mcp"
    }
  }
}
```

### Direct Usage

```bash
python server.py
```

## Rate Limits

| Tier | Requests/Hour |
|------|--------------|
| Free | 60 |
| Pro | 5,000 |

## License

MIT - see [LICENSE](LICENSE)

---

*Part of the MEOK AI Labs MCP Marketplace*
