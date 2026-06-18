"""Seed builtin templates

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-01-20 10:05:00.000000

"""
from typing import Sequence, Union
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Built-in templates data
BUILTIN_TEMPLATES = [
    {
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "Email Summarizer with AI",
        "short_description": "Summarize incoming emails and send digests to Slack",
        "description": "Automatically summarize your emails using AI and send a daily digest to Slack. This workflow triggers on a daily schedule (9 AM), fetches recent emails from Gmail, uses OpenAI GPT to summarize key points, and sends a formatted summary to your Slack channel.",
        "category": "Communication",
        "tags": ["email", "slack", "ai", "summarization", "productivity"],
        "icon": "Mail",
        "difficulty": "beginner",
        "estimated_setup_minutes": 10,
        "is_featured": True,
        "required_connections": ["OPENAI", "GMAIL_OAUTH", "SLACK"],
        "graph_definition": {
            "nodes": [
                {"id": "trigger-1", "type": "scheduleTriggerNode", "position": {"x": 100, "y": 200}, "data": {"schedule_type": "cron", "cron_preset": "daily_9am", "timezone": "UTC", "enabled": True}},
                {"id": "gmail-1", "type": "gmailNode", "position": {"x": 350, "y": 200}, "data": {"action": "list", "query": "is:unread newer_than:1d", "max_results": 20}},
                {"id": "openai-1", "type": "openaiNode", "position": {"x": 600, "y": 200}, "data": {"model": "gpt-4o-mini", "prompt": "Summarize these emails into a concise daily digest:\\n\\n{{gmail-1.emails}}", "system_prompt": "You are an executive assistant creating email digests.", "max_tokens": 1000}},
                {"id": "slack-1", "type": "slackNode", "position": {"x": 850, "y": 200}, "data": {"action": "send_message", "channel": "#daily-digest", "message": "Daily Email Digest\\n\\n{{openai-1.content}}"}}
            ],
            "edges": [
                {"id": "e1", "source": "trigger-1", "target": "gmail-1"},
                {"id": "e2", "source": "gmail-1", "target": "openai-1"},
                {"id": "e3", "source": "openai-1", "target": "slack-1"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },
    {
        "id": "00000000-0000-0000-0000-000000000002",
        "name": "AI Content Generator",
        "short_description": "Generate blog posts, social media content, or marketing copy",
        "description": "Generate high-quality content using AI with customizable prompts. Takes a topic and content type as input, uses Claude to research and outline, uses GPT to write polished content, and outputs formatted content ready for publishing.",
        "category": "Marketing",
        "tags": ["content", "ai", "writing", "marketing", "blog"],
        "icon": "PenTool",
        "difficulty": "beginner",
        "estimated_setup_minutes": 5,
        "is_featured": True,
        "required_connections": ["OPENAI", "ANTHROPIC"],
        "graph_definition": {
            "nodes": [
                {"id": "start-1", "type": "startNode", "position": {"x": 100, "y": 200}, "data": {}},
                {"id": "anthropic-1", "type": "anthropicNode", "position": {"x": 350, "y": 200}, "data": {"model": "claude-3-5-sonnet-20241022", "prompt": "Create a detailed outline for a {{initial_input.content_type}} about: {{initial_input.topic}}", "system_prompt": "You are a content strategist.", "max_tokens": 1000}},
                {"id": "openai-1", "type": "openaiNode", "position": {"x": 600, "y": 200}, "data": {"model": "gpt-4o", "prompt": "Write a complete {{initial_input.content_type}} based on this outline:\\n\\n{{anthropic-1.content}}", "system_prompt": "You are an expert content writer.", "max_tokens": 2000}}
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "anthropic-1"},
                {"id": "e2", "source": "anthropic-1", "target": "openai-1"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },
    {
        "id": "00000000-0000-0000-0000-000000000003",
        "name": "AI Customer Support Agent",
        "short_description": "Intelligent support agent with RAG and human escalation",
        "description": "Build an intelligent customer support agent powered by RAG. Receives customer queries, searches your knowledge base using RAG, generates contextual responses with AI, and routes complex issues to human agents.",
        "category": "Customer Support",
        "tags": ["support", "rag", "ai", "chatbot", "customer-service"],
        "icon": "MessageCircle",
        "difficulty": "intermediate",
        "estimated_setup_minutes": 20,
        "is_featured": True,
        "required_connections": ["OPENAI"],
        "graph_definition": {
            "nodes": [
                {"id": "start-1", "type": "startNode", "position": {"x": 100, "y": 200}, "data": {}},
                {"id": "rag-1", "type": "ragNode", "position": {"x": 350, "y": 200}, "data": {"action": "query", "query": "{{initial_input.question}}", "top_k": 5}},
                {"id": "router-1", "type": "routerNode", "position": {"x": 600, "y": 200}, "data": {"routing_logic": "ai", "routes": [{"name": "auto_respond", "description": "Query can be answered"}, {"name": "escalate", "description": "Complex issue"}]}},
                {"id": "openai-1", "type": "openaiNode", "position": {"x": 850, "y": 100}, "data": {"model": "gpt-4o-mini", "prompt": "Answer the customer question using this context:\\n\\n{{rag-1.results}}", "max_tokens": 500}}
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "rag-1"},
                {"id": "e2", "source": "rag-1", "target": "router-1"},
                {"id": "e3", "source": "router-1", "target": "openai-1", "sourceHandle": "auto_respond"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },
    {
        "id": "00000000-0000-0000-0000-000000000004",
        "name": "Web Research Agent",
        "short_description": "Research any topic using AI and web search",
        "description": "Conduct comprehensive research on any topic. Takes a research question as input, uses Perplexity for real-time web search, synthesizes findings with GPT, and outputs a structured research report.",
        "category": "AI Automation",
        "tags": ["research", "web-search", "ai", "perplexity", "analysis"],
        "icon": "Search",
        "difficulty": "beginner",
        "estimated_setup_minutes": 5,
        "is_featured": True,
        "required_connections": ["PERPLEXITY", "OPENAI"],
        "graph_definition": {
            "nodes": [
                {"id": "start-1", "type": "startNode", "position": {"x": 100, "y": 200}, "data": {}},
                {"id": "perplexity-1", "type": "perplexityNode", "position": {"x": 350, "y": 200}, "data": {"model": "sonar-pro", "prompt": "{{initial_input.question}}", "search_recency": "week"}},
                {"id": "openai-1", "type": "openaiNode", "position": {"x": 600, "y": 200}, "data": {"model": "gpt-4o", "prompt": "Create a comprehensive report based on this research:\\n\\n{{perplexity-1.content}}", "max_tokens": 2000}}
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "perplexity-1"},
                {"id": "e2", "source": "perplexity-1", "target": "openai-1"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },
    {
        "id": "00000000-0000-0000-0000-000000000005",
        "name": "Hello World - Getting Started",
        "short_description": "A simple workflow to learn the basics",
        "description": "The simplest possible workflow to get started. Starts with a trigger, uses AI to generate a greeting, and outputs the result. Perfect for learning how workflows work.",
        "category": "Getting Started",
        "tags": ["beginner", "tutorial", "hello-world"],
        "icon": "Zap",
        "difficulty": "beginner",
        "estimated_setup_minutes": 2,
        "is_featured": True,
        "required_connections": ["OPENAI"],
        "graph_definition": {
            "nodes": [
                {"id": "start-1", "type": "startNode", "position": {"x": 100, "y": 200}, "data": {}},
                {"id": "openai-1", "type": "openaiNode", "position": {"x": 350, "y": 200}, "data": {"model": "gpt-4o-mini", "prompt": "Say hello to {{initial_input.name | default: 'World'}} in a creative way!", "system_prompt": "You are a friendly assistant.", "max_tokens": 100}}
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "openai-1"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },
    {
        "id": "00000000-0000-0000-0000-000000000006",
        "name": "YouTube Video Summarizer",
        "short_description": "Summarize any YouTube video with AI",
        "description": "Get AI summaries of YouTube videos. Takes a YouTube URL as input, extracts video transcript, generates a comprehensive summary with key points and takeaways.",
        "category": "Productivity",
        "tags": ["youtube", "video", "summary", "ai", "content"],
        "icon": "Youtube",
        "difficulty": "beginner",
        "estimated_setup_minutes": 5,
        "is_featured": False,
        "required_connections": ["OPENAI"],
        "graph_definition": {
            "nodes": [
                {"id": "start-1", "type": "startNode", "position": {"x": 100, "y": 200}, "data": {}},
                {"id": "youtube-1", "type": "youTubeNode", "position": {"x": 350, "y": 200}, "data": {"action": "get_transcript", "video_url": "{{initial_input.video_url}}"}},
                {"id": "openai-1", "type": "openaiNode", "position": {"x": 600, "y": 200}, "data": {"model": "gpt-4o-mini", "prompt": "Summarize this video transcript:\\n\\n{{youtube-1.transcript}}", "max_tokens": 1000}}
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "youtube-1"},
                {"id": "e2", "source": "youtube-1", "target": "openai-1"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },
    {
        "id": "00000000-0000-0000-0000-000000000007",
        "name": "Document Analyzer",
        "short_description": "Extract and analyze text from documents and images",
        "description": "Process documents using OCR and AI analysis. Accepts document URL or upload, extracts text using Mistral OCR, analyzes content with AI, and outputs structured data.",
        "category": "Data Processing",
        "tags": ["ocr", "document", "extraction", "mistral", "analysis"],
        "icon": "FileText",
        "difficulty": "intermediate",
        "estimated_setup_minutes": 10,
        "is_featured": False,
        "required_connections": ["MISTRAL", "OPENAI"],
        "graph_definition": {
            "nodes": [
                {"id": "start-1", "type": "startNode", "position": {"x": 100, "y": 200}, "data": {}},
                {"id": "mistral-1", "type": "mistralParseNode", "position": {"x": 350, "y": 200}, "data": {"input_method": "url", "document_url": "{{initial_input.document_url}}", "output_format": "markdown"}},
                {"id": "openai-1", "type": "openaiNode", "position": {"x": 600, "y": 200}, "data": {"model": "gpt-4o", "prompt": "Analyze this document and extract key information:\\n\\n{{mistral-1.content}}", "json_mode": True, "max_tokens": 1500}}
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "mistral-1"},
                {"id": "e2", "source": "mistral-1", "target": "openai-1"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },
    {
        "id": "00000000-0000-0000-0000-000000000008",
        "name": "Spreadsheet Data Processor",
        "short_description": "Process and transform spreadsheet data with AI",
        "description": "Automate spreadsheet data processing with AI assistance. Reads data from Google Sheets, processes/transforms data with code, uses AI for data analysis or enrichment, and writes results back.",
        "category": "Data Processing",
        "tags": ["data", "spreadsheet", "automation", "google-sheets"],
        "icon": "Table",
        "difficulty": "intermediate",
        "estimated_setup_minutes": 15,
        "is_featured": False,
        "required_connections": ["GOOGLE", "OPENAI"],
        "graph_definition": {
            "nodes": [
                {"id": "start-1", "type": "startNode", "position": {"x": 100, "y": 200}, "data": {}},
                {"id": "sheets-read", "type": "googleSheetsNode", "position": {"x": 350, "y": 200}, "data": {"action": "read", "spreadsheet_id": "{{initial_input.spreadsheet_id}}", "range": "Sheet1!A:Z"}},
                {"id": "code-1", "type": "codeExecutionNode", "position": {"x": 600, "y": 200}, "data": {"language": "python", "code": "data = inputs.get('sheets-read', {}).get('data', [])\\noutput = {'processed_rows': len(data), 'data': data}"}},
                {"id": "openai-1", "type": "openaiNode", "position": {"x": 850, "y": 200}, "data": {"model": "gpt-4o-mini", "prompt": "Analyze this data:\\n\\n{{code-1.data}}", "max_tokens": 1000}}
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "sheets-read"},
                {"id": "e2", "source": "sheets-read", "target": "code-1"},
                {"id": "e3", "source": "code-1", "target": "openai-1"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },
    {
        "id": "00000000-0000-0000-0000-000000000009",
        "name": "Multi-Model AI Comparison",
        "short_description": "Compare responses from multiple AI models in parallel",
        "description": "Run the same prompt through multiple AI models simultaneously. Sends a prompt to GPT, Claude, and Gemini in parallel, collects all responses, and compares/summarizes the differences.",
        "category": "AI Automation",
        "tags": ["ai", "comparison", "parallel", "testing", "models"],
        "icon": "GitBranch",
        "difficulty": "intermediate",
        "estimated_setup_minutes": 10,
        "is_featured": False,
        "required_connections": ["OPENAI", "ANTHROPIC", "GOOGLE"],
        "graph_definition": {
            "nodes": [
                {"id": "start-1", "type": "startNode", "position": {"x": 100, "y": 250}, "data": {}},
                {"id": "parallel-1", "type": "parallelNode", "position": {"x": 350, "y": 250}, "data": {"wait_for_all": True}},
                {"id": "openai-1", "type": "openaiNode", "position": {"x": 600, "y": 100}, "data": {"model": "gpt-4o-mini", "prompt": "{{initial_input.prompt}}", "max_tokens": 500}},
                {"id": "anthropic-1", "type": "anthropicNode", "position": {"x": 600, "y": 250}, "data": {"model": "claude-3-5-sonnet-20241022", "prompt": "{{initial_input.prompt}}", "max_tokens": 500}},
                {"id": "gemini-1", "type": "geminiNode", "position": {"x": 600, "y": 400}, "data": {"model": "gemini-2.0-flash", "prompt": "{{initial_input.prompt}}", "max_tokens": 500}},
                {"id": "openai-compare", "type": "openaiNode", "position": {"x": 900, "y": 250}, "data": {"model": "gpt-4o", "prompt": "Compare these AI model responses:\\n\\nGPT: {{openai-1.content}}\\n\\nClaude: {{anthropic-1.content}}\\n\\nGemini: {{gemini-1.content}}", "max_tokens": 1000}}
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "parallel-1"},
                {"id": "e2", "source": "parallel-1", "target": "openai-1"},
                {"id": "e3", "source": "parallel-1", "target": "anthropic-1"},
                {"id": "e4", "source": "parallel-1", "target": "gemini-1"},
                {"id": "e5", "source": "openai-1", "target": "openai-compare"},
                {"id": "e6", "source": "anthropic-1", "target": "openai-compare"},
                {"id": "e7", "source": "gemini-1", "target": "openai-compare"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },
    {
        "id": "00000000-0000-0000-0000-000000000010",
        "name": "Scheduled Analytics Report",
        "short_description": "Generate and send automated reports on a schedule",
        "description": "Automatically generate and distribute analytics reports. Runs on a weekly schedule, queries your data from Supabase, generates insights with AI, and sends formatted report to Slack.",
        "category": "Analytics",
        "tags": ["analytics", "reporting", "scheduled", "automation", "supabase"],
        "icon": "BarChart",
        "difficulty": "intermediate",
        "estimated_setup_minutes": 15,
        "is_featured": False,
        "required_connections": ["SUPABASE", "OPENAI", "SLACK"],
        "graph_definition": {
            "nodes": [
                {"id": "trigger-1", "type": "scheduleTriggerNode", "position": {"x": 100, "y": 200}, "data": {"schedule_type": "cron", "cron_preset": "weekly_monday_9am", "timezone": "UTC", "enabled": True}},
                {"id": "supabase-1", "type": "supabaseNode", "position": {"x": 350, "y": 200}, "data": {"action": "query", "table": "analytics", "query": "select * from analytics where created_at > now() - interval '7 days'"}},
                {"id": "openai-1", "type": "openaiNode", "position": {"x": 600, "y": 200}, "data": {"model": "gpt-4o", "prompt": "Analyze this week's data and create an executive report:\\n\\n{{supabase-1.data}}", "max_tokens": 1500}},
                {"id": "slack-1", "type": "slackNode", "position": {"x": 850, "y": 200}, "data": {"action": "send_message", "channel": "#team-updates", "message": "Weekly Analytics Report\\n\\n{{openai-1.content}}"}}
            ],
            "edges": [
                {"id": "e1", "source": "trigger-1", "target": "supabase-1"},
                {"id": "e2", "source": "supabase-1", "target": "openai-1"},
                {"id": "e3", "source": "openai-1", "target": "slack-1"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    }
]


def upgrade() -> None:
    """Seed builtin templates."""
    import json

    # Get connection
    connection = op.get_bind()

    now = datetime.now(timezone.utc)

    for template in BUILTIN_TEMPLATES:
        connection.execute(
            sa.text("""
                INSERT INTO workflow_template (
                    id, user_id, name, description, short_description,
                    category, tags, graph_definition, required_connections,
                    icon, difficulty, estimated_setup_minutes,
                    is_featured, is_public, clone_count, created_at, updated_at
                ) VALUES (
                    :id, NULL, :name, :description, :short_description,
                    :category, :tags, :graph_definition, :required_connections,
                    :icon, :difficulty, :estimated_setup_minutes,
                    :is_featured, TRUE, 0, :created_at, :updated_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    short_description = EXCLUDED.short_description,
                    category = EXCLUDED.category,
                    tags = EXCLUDED.tags,
                    graph_definition = EXCLUDED.graph_definition,
                    required_connections = EXCLUDED.required_connections,
                    icon = EXCLUDED.icon,
                    difficulty = EXCLUDED.difficulty,
                    estimated_setup_minutes = EXCLUDED.estimated_setup_minutes,
                    is_featured = EXCLUDED.is_featured,
                    updated_at = EXCLUDED.updated_at
            """),
            {
                "id": template["id"],
                "name": template["name"],
                "description": template["description"],
                "short_description": template["short_description"],
                "category": template["category"],
                "tags": json.dumps(template["tags"]),
                "graph_definition": json.dumps(template["graph_definition"]),
                "required_connections": json.dumps(template["required_connections"]),
                "icon": template["icon"],
                "difficulty": template["difficulty"],
                "estimated_setup_minutes": template["estimated_setup_minutes"],
                "is_featured": template["is_featured"],
                "created_at": now,
                "updated_at": now
            }
        )


def downgrade() -> None:
    """Remove seeded templates."""
    connection = op.get_bind()

    # Delete only system templates (user_id is NULL)
    template_ids = [t["id"] for t in BUILTIN_TEMPLATES]

    connection.execute(
        sa.text("""
            DELETE FROM workflow_template
            WHERE id = ANY(:ids) AND user_id IS NULL
        """),
        {"ids": template_ids}
    )
