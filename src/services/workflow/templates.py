"""
Workflow Templates Service.

Provides built-in templates and template management functionality.
"""

from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from loguru import logger

from src.models.sql.workflow.template import WorkflowTemplate, TemplateCategory
from src.models.sql.workflow.workflow import Workflow, WorkflowStatus


# ============================================================
# BUILT-IN TEMPLATES
# ============================================================

BUILTIN_TEMPLATES: List[Dict[str, Any]] = [
    # 1. Email Summarizer with AI
    {
        "name": "Email Summarizer with AI",
        "short_description": "Summarize incoming emails and send digests to Slack",
        "description": """Automatically summarize your emails using AI and send a daily digest to Slack.

This workflow:
1. Triggers on a daily schedule (9 AM)
2. Fetches recent emails from Gmail
3. Uses OpenAI GPT to summarize key points
4. Sends a formatted summary to your Slack channel

Perfect for staying on top of email without constant inbox checking.""",
        "category": TemplateCategory.COMMUNICATION,
        "tags": ["email", "slack", "ai", "summarization", "productivity"],
        "icon": "Mail",
        "difficulty": "beginner",
        "estimated_setup_minutes": 10,
        "is_featured": True,
        "required_connections": ["OPENAI", "GMAIL_OAUTH", "SLACK"],
        "graph_definition": {
            "nodes": [
                {
                    "id": "trigger-1",
                    "type": "scheduleTriggerNode",
                    "position": {"x": 100, "y": 200},
                    "data": {
                        "schedule_type": "cron",
                        "cron_preset": "daily_9am",
                        "timezone": "UTC",
                        "enabled": True
                    }
                },
                {
                    "id": "gmail-1",
                    "type": "gmailNode",
                    "position": {"x": 350, "y": 200},
                    "data": {
                        "action": "list",
                        "query": "is:unread newer_than:1d",
                        "max_results": 20
                    }
                },
                {
                    "id": "openai-1",
                    "type": "openaiNode",
                    "position": {"x": 600, "y": 200},
                    "data": {
                        "model": "gpt-4o-mini",
                        "prompt": "Summarize these emails into a concise daily digest. Group by importance and include action items:\n\n{{gmail-1.emails}}",
                        "system_prompt": "You are an executive assistant creating email digests. Be concise but comprehensive. Highlight urgent items.",
                        "max_tokens": 1000
                    }
                },
                {
                    "id": "slack-1",
                    "type": "slackNode",
                    "position": {"x": 850, "y": 200},
                    "data": {
                        "action": "send_message",
                        "channel": "#daily-digest",
                        "message": "📧 *Daily Email Digest*\n\n{{openai-1.content}}"
                    }
                }
            ],
            "edges": [
                {"id": "e1", "source": "trigger-1", "target": "gmail-1"},
                {"id": "e2", "source": "gmail-1", "target": "openai-1"},
                {"id": "e3", "source": "openai-1", "target": "slack-1"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },

    # 2. Content Generator
    {
        "name": "AI Content Generator",
        "short_description": "Generate blog posts, social media content, or marketing copy",
        "description": """Generate high-quality content using AI with customizable prompts.

This workflow:
1. Takes a topic and content type as input
2. Uses Claude to research and outline
3. Uses GPT to write polished content
4. Outputs formatted content ready for publishing

Great for content marketing, blog posts, and social media.""",
        "category": TemplateCategory.MARKETING,
        "tags": ["content", "ai", "writing", "marketing", "blog"],
        "icon": "PenTool",
        "difficulty": "beginner",
        "estimated_setup_minutes": 5,
        "is_featured": True,
        "required_connections": ["OPENAI", "ANTHROPIC"],
        "graph_definition": {
            "nodes": [
                {
                    "id": "start-1",
                    "type": "startNode",
                    "position": {"x": 100, "y": 200},
                    "data": {}
                },
                {
                    "id": "anthropic-1",
                    "type": "anthropicNode",
                    "position": {"x": 350, "y": 200},
                    "data": {
                        "model": "claude-3-5-sonnet-20241022",
                        "prompt": "Create a detailed outline for a {{initial_input.content_type}} about: {{initial_input.topic}}\n\nInclude:\n- Key points to cover\n- Target audience considerations\n- Suggested structure\n- SEO keywords to include",
                        "system_prompt": "You are a content strategist. Create comprehensive outlines that lead to engaging, well-structured content.",
                        "max_tokens": 1000
                    }
                },
                {
                    "id": "openai-1",
                    "type": "openaiNode",
                    "position": {"x": 600, "y": 200},
                    "data": {
                        "model": "gpt-4o",
                        "prompt": "Write a complete {{initial_input.content_type}} based on this outline:\n\n{{anthropic-1.content}}\n\nTopic: {{initial_input.topic}}\nTone: {{initial_input.tone | default: 'professional'}}",
                        "system_prompt": "You are an expert content writer. Create engaging, well-researched content that matches the requested tone and format.",
                        "max_tokens": 2000
                    }
                }
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "anthropic-1"},
                {"id": "e2", "source": "anthropic-1", "target": "openai-1"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },

    # 3. Customer Support Bot
    {
        "name": "AI Customer Support Agent",
        "short_description": "Intelligent support agent with RAG and human escalation",
        "description": """Build an intelligent customer support agent powered by RAG.

This workflow:
1. Receives customer queries via webhook
2. Searches your knowledge base using RAG
3. Generates contextual responses with AI
4. Routes complex issues to human agents
5. Logs interactions for improvement

Features human-in-the-loop for complex cases.""",
        "category": TemplateCategory.CUSTOMER_SUPPORT,
        "tags": ["support", "rag", "ai", "chatbot", "customer-service"],
        "icon": "MessageCircle",
        "difficulty": "intermediate",
        "estimated_setup_minutes": 20,
        "is_featured": True,
        "required_connections": ["OPENAI"],
        "graph_definition": {
            "nodes": [
                {
                    "id": "start-1",
                    "type": "startNode",
                    "position": {"x": 100, "y": 200},
                    "data": {}
                },
                {
                    "id": "rag-1",
                    "type": "ragNode",
                    "position": {"x": 350, "y": 200},
                    "data": {
                        "action": "query",
                        "query": "{{initial_input.question}}",
                        "top_k": 5
                    }
                },
                {
                    "id": "router-1",
                    "type": "routerNode",
                    "position": {"x": 600, "y": 200},
                    "data": {
                        "routing_logic": "ai",
                        "routes": [
                            {"name": "auto_respond", "description": "Query can be answered from knowledge base"},
                            {"name": "escalate", "description": "Complex issue requiring human review"}
                        ]
                    }
                },
                {
                    "id": "openai-1",
                    "type": "openaiNode",
                    "position": {"x": 850, "y": 100},
                    "data": {
                        "model": "gpt-4o-mini",
                        "prompt": "Answer the customer's question using this context:\n\nQuestion: {{initial_input.question}}\n\nKnowledge Base Results:\n{{rag-1.results}}\n\nProvide a helpful, friendly response.",
                        "system_prompt": "You are a helpful customer support agent. Be concise and accurate. If you're unsure, acknowledge limitations.",
                        "max_tokens": 500
                    }
                },
                {
                    "id": "slack-1",
                    "type": "slackNode",
                    "position": {"x": 850, "y": 300},
                    "data": {
                        "action": "send_message",
                        "channel": "#support-escalations",
                        "message": "🚨 *Support Escalation*\n\nCustomer: {{initial_input.customer_id}}\nQuestion: {{initial_input.question}}\n\nContext found:\n{{rag-1.results}}"
                    }
                }
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "rag-1"},
                {"id": "e2", "source": "rag-1", "target": "router-1"},
                {"id": "e3", "source": "router-1", "target": "openai-1", "sourceHandle": "auto_respond"},
                {"id": "e4", "source": "router-1", "target": "slack-1", "sourceHandle": "escalate"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },

    # 4. Web Research Agent
    {
        "name": "Web Research Agent",
        "short_description": "Research any topic using AI and web search",
        "description": """Conduct comprehensive research on any topic.

This workflow:
1. Takes a research question as input
2. Uses Perplexity for real-time web search
3. Synthesizes findings with GPT
4. Outputs a structured research report

Perfect for competitive analysis, market research, and learning.""",
        "category": TemplateCategory.AI_AUTOMATION,
        "tags": ["research", "web-search", "ai", "perplexity", "analysis"],
        "icon": "Search",
        "difficulty": "beginner",
        "estimated_setup_minutes": 5,
        "is_featured": True,
        "required_connections": ["PERPLEXITY", "OPENAI"],
        "graph_definition": {
            "nodes": [
                {
                    "id": "start-1",
                    "type": "startNode",
                    "position": {"x": 100, "y": 200},
                    "data": {}
                },
                {
                    "id": "perplexity-1",
                    "type": "perplexityNode",
                    "position": {"x": 350, "y": 200},
                    "data": {
                        "model": "sonar-pro",
                        "prompt": "{{initial_input.question}}",
                        "search_recency": "week"
                    }
                },
                {
                    "id": "openai-1",
                    "type": "openaiNode",
                    "position": {"x": 600, "y": 200},
                    "data": {
                        "model": "gpt-4o",
                        "prompt": "Based on this research, create a comprehensive report:\n\nOriginal Question: {{initial_input.question}}\n\nResearch Findings:\n{{perplexity-1.content}}\n\nCitations:\n{{perplexity-1.citations}}\n\nCreate a well-structured report with:\n1. Executive Summary\n2. Key Findings\n3. Analysis\n4. Sources",
                        "system_prompt": "You are a research analyst. Create clear, well-organized reports with proper citations.",
                        "max_tokens": 2000
                    }
                }
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "perplexity-1"},
                {"id": "e2", "source": "perplexity-1", "target": "openai-1"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },

    # 5. Data Pipeline
    {
        "name": "Spreadsheet Data Processor",
        "short_description": "Process and transform spreadsheet data with AI",
        "description": """Automate spreadsheet data processing with AI assistance.

This workflow:
1. Reads data from Google Sheets
2. Processes/transforms data with code
3. Uses AI for data analysis or enrichment
4. Writes results back to a sheet

Great for data cleaning, enrichment, and automated reporting.""",
        "category": TemplateCategory.DATA_PROCESSING,
        "tags": ["data", "spreadsheet", "automation", "google-sheets"],
        "icon": "Table",
        "difficulty": "intermediate",
        "estimated_setup_minutes": 15,
        "is_featured": False,
        "required_connections": ["GOOGLE", "OPENAI"],
        "graph_definition": {
            "nodes": [
                {
                    "id": "start-1",
                    "type": "startNode",
                    "position": {"x": 100, "y": 200},
                    "data": {}
                },
                {
                    "id": "sheets-read",
                    "type": "googleSheetsNode",
                    "position": {"x": 350, "y": 200},
                    "data": {
                        "action": "read",
                        "spreadsheet_id": "{{initial_input.spreadsheet_id}}",
                        "range": "{{initial_input.range | default: 'Sheet1!A:Z'}}"
                    }
                },
                {
                    "id": "code-1",
                    "type": "codeExecutionNode",
                    "position": {"x": 600, "y": 200},
                    "data": {
                        "language": "python",
                        "code": "# Process the spreadsheet data\ndata = inputs.get('sheets-read', {}).get('data', [])\n\n# Example: filter and transform\nprocessed = []\nfor row in data[1:]:  # Skip header\n    if row:  # Skip empty rows\n        processed.append(row)\n\noutput = {'processed_rows': len(processed), 'data': processed}"
                    }
                },
                {
                    "id": "openai-1",
                    "type": "openaiNode",
                    "position": {"x": 850, "y": 200},
                    "data": {
                        "model": "gpt-4o-mini",
                        "prompt": "Analyze this data and provide insights:\n\n{{code-1.data}}\n\nProvide:\n1. Summary statistics\n2. Key patterns\n3. Recommendations",
                        "system_prompt": "You are a data analyst. Provide clear, actionable insights.",
                        "max_tokens": 1000
                    }
                }
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "sheets-read"},
                {"id": "e2", "source": "sheets-read", "target": "code-1"},
                {"id": "e3", "source": "code-1", "target": "openai-1"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },

    # 6. Simple Hello World
    {
        "name": "Hello World - Getting Started",
        "short_description": "A simple workflow to learn the basics",
        "description": """The simplest possible workflow to get started.

This workflow:
1. Starts with a trigger
2. Uses AI to generate a greeting
3. Outputs the result

Perfect for learning how workflows work.""",
        "category": TemplateCategory.STARTER,
        "tags": ["beginner", "tutorial", "hello-world"],
        "icon": "Zap",
        "difficulty": "beginner",
        "estimated_setup_minutes": 2,
        "is_featured": True,
        "required_connections": ["OPENAI"],
        "graph_definition": {
            "nodes": [
                {
                    "id": "start-1",
                    "type": "startNode",
                    "position": {"x": 100, "y": 200},
                    "data": {}
                },
                {
                    "id": "openai-1",
                    "type": "openaiNode",
                    "position": {"x": 350, "y": 200},
                    "data": {
                        "model": "gpt-4o-mini",
                        "prompt": "Say hello to {{initial_input.name | default: 'World'}} in a creative way!",
                        "system_prompt": "You are a friendly assistant. Be creative and fun!",
                        "max_tokens": 100
                    }
                }
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "openai-1"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },

    # 7. Document Analyzer with OCR
    {
        "name": "Document Analyzer",
        "short_description": "Extract and analyze text from documents and images",
        "description": """Process documents using OCR and AI analysis.

This workflow:
1. Accepts document URL or upload
2. Extracts text using Mistral's OCR
3. Analyzes content with AI
4. Outputs structured data

Perfect for invoice processing, document review, and data extraction.""",
        "category": TemplateCategory.DATA_PROCESSING,
        "tags": ["ocr", "document", "extraction", "mistral", "analysis"],
        "icon": "FileText",
        "difficulty": "intermediate",
        "estimated_setup_minutes": 10,
        "is_featured": False,
        "required_connections": ["MISTRAL", "OPENAI"],
        "graph_definition": {
            "nodes": [
                {
                    "id": "start-1",
                    "type": "startNode",
                    "position": {"x": 100, "y": 200},
                    "data": {}
                },
                {
                    "id": "mistral-1",
                    "type": "mistralParseNode",
                    "position": {"x": 350, "y": 200},
                    "data": {
                        "input_method": "url",
                        "document_url": "{{initial_input.document_url}}",
                        "output_format": "markdown"
                    }
                },
                {
                    "id": "openai-1",
                    "type": "openaiNode",
                    "position": {"x": 600, "y": 200},
                    "data": {
                        "model": "gpt-4o",
                        "prompt": "Analyze this document and extract key information:\n\n{{mistral-1.content}}\n\nExtract:\n- Document type\n- Key entities (names, dates, amounts)\n- Summary\n- Action items (if any)",
                        "system_prompt": "You are a document analyst. Extract structured information accurately.",
                        "max_tokens": 1500,
                        "json_mode": True
                    }
                }
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "mistral-1"},
                {"id": "e2", "source": "mistral-1", "target": "openai-1"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },

    # 8. YouTube Video Summarizer
    {
        "name": "YouTube Video Summarizer",
        "short_description": "Summarize any YouTube video with AI",
        "description": """Get AI summaries of YouTube videos.

This workflow:
1. Takes a YouTube URL as input
2. Extracts video transcript
3. Generates a comprehensive summary
4. Outputs key points and takeaways

Save time by getting the key information from long videos.""",
        "category": TemplateCategory.PRODUCTIVITY,
        "tags": ["youtube", "video", "summary", "ai", "content"],
        "icon": "Youtube",
        "difficulty": "beginner",
        "estimated_setup_minutes": 5,
        "is_featured": False,
        "required_connections": ["OPENAI"],
        "graph_definition": {
            "nodes": [
                {
                    "id": "start-1",
                    "type": "startNode",
                    "position": {"x": 100, "y": 200},
                    "data": {}
                },
                {
                    "id": "youtube-1",
                    "type": "youTubeNode",
                    "position": {"x": 350, "y": 200},
                    "data": {
                        "action": "get_transcript",
                        "video_url": "{{initial_input.video_url}}"
                    }
                },
                {
                    "id": "openai-1",
                    "type": "openaiNode",
                    "position": {"x": 600, "y": 200},
                    "data": {
                        "model": "gpt-4o-mini",
                        "prompt": "Summarize this video transcript:\n\n{{youtube-1.transcript}}\n\nProvide:\n1. Brief overview (2-3 sentences)\n2. Key points (bullet list)\n3. Main takeaways\n4. Who should watch this",
                        "system_prompt": "You are a content curator. Create clear, useful video summaries.",
                        "max_tokens": 1000
                    }
                }
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "youtube-1"},
                {"id": "e2", "source": "youtube-1", "target": "openai-1"}
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1}
        }
    },

    # 9. Parallel Processing Example
    {
        "name": "Multi-Model AI Comparison",
        "short_description": "Compare responses from multiple AI models in parallel",
        "description": """Run the same prompt through multiple AI models simultaneously.

This workflow:
1. Takes a prompt as input
2. Sends it to GPT, Claude, and Gemini in parallel
3. Collects all responses
4. Compares and summarizes the differences

Great for testing prompts and understanding model differences.""",
        "category": TemplateCategory.AI_AUTOMATION,
        "tags": ["ai", "comparison", "parallel", "testing", "models"],
        "icon": "GitBranch",
        "difficulty": "intermediate",
        "estimated_setup_minutes": 10,
        "is_featured": False,
        "required_connections": ["OPENAI", "ANTHROPIC", "GOOGLE"],
        "graph_definition": {
            "nodes": [
                {
                    "id": "start-1",
                    "type": "startNode",
                    "position": {"x": 100, "y": 250},
                    "data": {}
                },
                {
                    "id": "parallel-1",
                    "type": "parallelNode",
                    "position": {"x": 350, "y": 250},
                    "data": {
                        "wait_for_all": True
                    }
                },
                {
                    "id": "openai-1",
                    "type": "openaiNode",
                    "position": {"x": 600, "y": 100},
                    "data": {
                        "model": "gpt-4o-mini",
                        "prompt": "{{initial_input.prompt}}",
                        "max_tokens": 500
                    }
                },
                {
                    "id": "anthropic-1",
                    "type": "anthropicNode",
                    "position": {"x": 600, "y": 250},
                    "data": {
                        "model": "claude-3-5-sonnet-20241022",
                        "prompt": "{{initial_input.prompt}}",
                        "max_tokens": 500
                    }
                },
                {
                    "id": "gemini-1",
                    "type": "geminiNode",
                    "position": {"x": 600, "y": 400},
                    "data": {
                        "model": "gemini-2.0-flash",
                        "prompt": "{{initial_input.prompt}}",
                        "max_tokens": 500
                    }
                },
                {
                    "id": "openai-compare",
                    "type": "openaiNode",
                    "position": {"x": 900, "y": 250},
                    "data": {
                        "model": "gpt-4o",
                        "prompt": "Compare these AI model responses to the same prompt:\n\nPrompt: {{initial_input.prompt}}\n\n---\nGPT-4o-mini:\n{{openai-1.content}}\n\n---\nClaude 3.5 Sonnet:\n{{anthropic-1.content}}\n\n---\nGemini 2.0 Flash:\n{{gemini-1.content}}\n\n---\n\nProvide:\n1. Key similarities\n2. Notable differences\n3. Which response is best for what use case",
                        "system_prompt": "You are an AI analyst. Compare responses objectively and insightfully.",
                        "max_tokens": 1000
                    }
                }
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

    # 10. Scheduled Report Generator
    {
        "name": "Scheduled Analytics Report",
        "short_description": "Generate and send automated reports on a schedule",
        "description": """Automatically generate and distribute analytics reports.

This workflow:
1. Runs on a weekly schedule
2. Queries your data from Supabase
3. Generates insights with AI
4. Sends formatted report to Slack

Perfect for weekly summaries, KPI tracking, and team updates.""",
        "category": TemplateCategory.ANALYTICS,
        "tags": ["analytics", "reporting", "scheduled", "automation", "supabase"],
        "icon": "BarChart",
        "difficulty": "intermediate",
        "estimated_setup_minutes": 15,
        "is_featured": False,
        "required_connections": ["SUPABASE", "OPENAI", "SLACK"],
        "graph_definition": {
            "nodes": [
                {
                    "id": "trigger-1",
                    "type": "scheduleTriggerNode",
                    "position": {"x": 100, "y": 200},
                    "data": {
                        "schedule_type": "cron",
                        "cron_preset": "weekly_monday_9am",
                        "timezone": "UTC",
                        "enabled": True
                    }
                },
                {
                    "id": "supabase-1",
                    "type": "supabaseNode",
                    "position": {"x": 350, "y": 200},
                    "data": {
                        "action": "query",
                        "table": "analytics",
                        "query": "select * from analytics where created_at > now() - interval '7 days'"
                    }
                },
                {
                    "id": "openai-1",
                    "type": "openaiNode",
                    "position": {"x": 600, "y": 200},
                    "data": {
                        "model": "gpt-4o",
                        "prompt": "Analyze this week's data and create an executive report:\n\n{{supabase-1.data}}\n\nInclude:\n1. Executive Summary\n2. Key Metrics & Trends\n3. Highlights & Wins\n4. Areas for Improvement\n5. Recommendations",
                        "system_prompt": "You are a business analyst. Create clear, actionable reports with data-driven insights.",
                        "max_tokens": 1500
                    }
                },
                {
                    "id": "slack-1",
                    "type": "slackNode",
                    "position": {"x": 850, "y": 200},
                    "data": {
                        "action": "send_message",
                        "channel": "#team-updates",
                        "message": "📊 *Weekly Analytics Report*\n\n{{openai-1.content}}"
                    }
                }
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


# ============================================================
# TEMPLATE SERVICE
# ============================================================

class TemplateService:
    """Service for managing workflow templates."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_template(self, template_id: UUID) -> Optional[WorkflowTemplate]:
        """Gets a template by ID."""
        return await self.db.get(WorkflowTemplate, template_id)

    async def list_templates(
            self,
            category: Optional[TemplateCategory] = None,
            featured_only: bool = False,
            search: Optional[str] = None,
            limit: int = 50,
            offset: int = 0
    ) -> List[WorkflowTemplate]:
        """Lists templates with optional filtering."""
        query = select(WorkflowTemplate).where(
            WorkflowTemplate.is_public == True
        )

        if category:
            query = query.where(WorkflowTemplate.category == category)

        if featured_only:
            query = query.where(WorkflowTemplate.is_featured == True)

        if search:
            search_term = f"%{search.lower()}%"
            query = query.where(
                or_(
                    func.lower(WorkflowTemplate.name).like(search_term),
                    func.lower(WorkflowTemplate.description).like(search_term)
                )
            )

        query = query.order_by(
            WorkflowTemplate.is_featured.desc(),
            WorkflowTemplate.clone_count.desc()
        ).offset(offset).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def clone_template(
            self,
            template_id: UUID,
            user_id: UUID,
            workflow_name: Optional[str] = None
    ) -> Workflow:
        """
        Clones a template to create a new workflow for a user.

        Args:
            template_id: Template to clone
            user_id: User creating the workflow
            workflow_name: Optional custom name (defaults to template name)

        Returns:
            Created workflow
        """
        template = await self.get_template(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")

        # Create new workflow from template
        workflow = Workflow(
            user_id=user_id,
            name=workflow_name or f"{template.name} (Copy)",
            description=template.description,
            graph_definition=template.graph_definition.copy(),
            status=WorkflowStatus.DRAFT
        )

        self.db.add(workflow)

        # Increment clone count
        template.increment_clone_count()

        await self.db.commit()
        await self.db.refresh(workflow)

        logger.info(
            f"Cloned template to workflow",
            extra={
                "template_id": str(template_id),
                "workflow_id": str(workflow.id),
                "user_id": str(user_id)
            }
        )

        return workflow

    async def seed_builtin_templates(self) -> int:
        """
        Seeds the built-in templates into the database.

        Returns:
            Number of templates created/updated
        """
        count = 0

        for template_data in BUILTIN_TEMPLATES:
            # Check if template already exists by name
            result = await self.db.execute(
                select(WorkflowTemplate).where(
                    and_(
                        WorkflowTemplate.name == template_data["name"],
                        WorkflowTemplate.user_id.is_(None)  # System template
                    )
                )
            )
            existing = result.scalars().first()

            if existing:
                # Update existing template
                for key, value in template_data.items():
                    if key != "name":
                        setattr(existing, key, value)
                existing.updated_at = datetime.now(timezone.utc)
            else:
                # Create new template
                template = WorkflowTemplate(**template_data)
                self.db.add(template)
                count += 1

        await self.db.commit()

        logger.info(f"Seeded {count} new builtin templates")
        return count

    async def get_categories_with_counts(self) -> List[Dict[str, Any]]:
        """Gets all categories with template counts."""
        result = await self.db.execute(
            select(
                WorkflowTemplate.category,
                func.count(WorkflowTemplate.id).label("count")
            )
            .where(WorkflowTemplate.is_public == True)
            .group_by(WorkflowTemplate.category)
        )

        categories = []
        for row in result:
            categories.append({
                "category": row.category.value,
                "count": row.count
            })

        return sorted(categories, key=lambda x: x["count"], reverse=True)


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

async def seed_templates(db: AsyncSession) -> int:
    """Seeds built-in templates."""
    service = TemplateService(db)
    return await service.seed_builtin_templates()
