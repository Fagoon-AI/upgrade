import asyncio
import json
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from loguru import logger

from src.services.workflow_engine.nodes.base import BaseNode
from src.services.workflow_engine.context import ExecutionContext
from src.models.sql.workflow.connection import Connection
from src.core.encryption import crypto
from src.services.workflow.storage_service import StorageService


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class YouTubeConfig:
    """Configuration for YouTube operations."""
    max_results_per_page: int = 50
    max_total_results: int = 500
    storage_threshold_bytes: int = 10_000  # 10KB
    retry_delay: float = 1.0
    max_retries: int = 3


# Video ID pattern
VIDEO_ID_PATTERN = re.compile(
    r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})'
)


# ============================================================
# VIDEO ID EXTRACTOR
# ============================================================

class VideoIDExtractor:
    """Extracts video IDs from various YouTube URL formats."""

    @staticmethod
    def extract(input_str: str) -> Optional[str]:
        """Extracts video ID from URL or returns ID if already valid."""
        input_str = input_str.strip()

        # Check if it's already a valid video ID (11 characters)
        if re.match(r'^[a-zA-Z0-9_-]{11}$', input_str):
            return input_str

        # Try to extract from URL
        match = VIDEO_ID_PATTERN.search(input_str)
        if match:
            return match.group(1)

        return None


# ============================================================
# YOUTUBE CLIENT
# ============================================================

class YouTubeClient:
    """
    Robust YouTube Data API client.
    """

    def __init__(self, api_key: str, config: Optional[YouTubeConfig] = None):
        self.api_key = api_key
        self.config = config or YouTubeConfig()
        self._service = None

    async def _get_service(self):
        """Gets or creates YouTube service."""
        if self._service:
            return self._service

        try:
            from googleapiclient.discovery import build
            self._service = build(
                "youtube", "v3",
                developerKey=self.api_key,
                cache_discovery=False
            )
            return self._service
        except ImportError:
            raise RuntimeError("google-api-python-client is required")

    async def search_videos(
            self,
            query: str,
            max_results: int = 10,
            order: str = "relevance",
            published_after: Optional[str] = None,
            published_before: Optional[str] = None,
            video_duration: str = "any",
            safe_search: str = "moderate",
            region_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """Searches for videos."""
        service = await self._get_service()
        max_results = min(max_results, self.config.max_results_per_page)

        try:
            params = {
                "q": query,
                "part": "id,snippet",
                "maxResults": max_results,
                "type": "video",
                "order": order,
                "videoDuration": video_duration,
                "safeSearch": safe_search
            }

            if published_after:
                params["publishedAfter"] = published_after
            if published_before:
                params["publishedBefore"] = published_before
            if region_code:
                params["regionCode"] = region_code

            response = await asyncio.to_thread(
                service.search().list(**params).execute
            )

            videos = []
            for item in response.get("items", []):
                videos.append({
                    "video_id": item["id"]["videoId"],
                    "title": item["snippet"]["title"],
                    "description": item["snippet"]["description"],
                    "channel_id": item["snippet"]["channelId"],
                    "channel_title": item["snippet"]["channelTitle"],
                    "published_at": item["snippet"]["publishedAt"],
                    "thumbnail": item["snippet"]["thumbnails"].get("high", {}).get("url")
                })

            return {
                "success": True,
                "videos": videos,
                "count": len(videos),
                "total_results": response.get("pageInfo", {}).get("totalResults", 0),
                "next_page_token": response.get("nextPageToken")
            }

        except Exception as e:
            return self._handle_error(e)

    async def get_video_details(
            self,
            video_id: str
    ) -> Dict[str, Any]:
        """Gets detailed video information."""
        service = await self._get_service()

        # Extract video ID if URL provided
        extracted_id = VideoIDExtractor.extract(video_id)
        if not extracted_id:
            return {"success": False, "error": "Invalid video ID or URL"}

        try:
            response = await asyncio.to_thread(
                service.videos().list(
                    part="snippet,contentDetails,statistics,topicDetails",
                    id=extracted_id
                ).execute
            )

            if not response.get("items"):
                return {"success": False, "error": "Video not found"}

            item = response["items"][0]
            snippet = item["snippet"]
            stats = item.get("statistics", {})
            content = item.get("contentDetails", {})

            return {
                "success": True,
                "details": {
                    "video_id": extracted_id,
                    "title": snippet["title"],
                    "description": snippet["description"],
                    "channel_id": snippet["channelId"],
                    "channel_title": snippet["channelTitle"],
                    "published_at": snippet["publishedAt"],
                    "tags": snippet.get("tags", []),
                    "category_id": snippet.get("categoryId"),
                    "duration": content.get("duration"),
                    "definition": content.get("definition"),
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                    "thumbnail": snippet["thumbnails"].get("maxres", snippet["thumbnails"].get("high", {})).get("url")
                }
            }

        except Exception as e:
            return self._handle_error(e)

    async def get_video_comments(
            self,
            video_id: str,
            max_results: int = 100,
            order: str = "relevance"
    ) -> Dict[str, Any]:
        """Gets video comments."""
        service = await self._get_service()

        extracted_id = VideoIDExtractor.extract(video_id)
        if not extracted_id:
            return {"success": False, "error": "Invalid video ID or URL"}

        max_results = min(max_results, self.config.max_results_per_page)

        try:
            response = await asyncio.to_thread(
                service.commentThreads().list(
                    part="snippet",
                    videoId=extracted_id,
                    maxResults=max_results,
                    order=order,
                    textFormat="plainText"
                ).execute
            )

            comments = []
            for item in response.get("items", []):
                comment = item["snippet"]["topLevelComment"]["snippet"]
                comments.append({
                    "author": comment["authorDisplayName"],
                    "text": comment["textDisplay"],
                    "like_count": comment.get("likeCount", 0),
                    "published_at": comment["publishedAt"],
                    "reply_count": item["snippet"].get("totalReplyCount", 0)
                })

            return {
                "success": True,
                "comments": comments,
                "count": len(comments),
                "next_page_token": response.get("nextPageToken")
            }

        except Exception as e:
            return self._handle_error(e)

    async def get_channel_info(
            self,
            channel_id: str
    ) -> Dict[str, Any]:
        """Gets channel information."""
        service = await self._get_service()

        try:
            response = await asyncio.to_thread(
                service.channels().list(
                    part="snippet,statistics,contentDetails",
                    id=channel_id
                ).execute
            )

            if not response.get("items"):
                return {"success": False, "error": "Channel not found"}

            item = response["items"][0]
            snippet = item["snippet"]
            stats = item.get("statistics", {})

            return {
                "success": True,
                "channel": {
                    "channel_id": channel_id,
                    "title": snippet["title"],
                    "description": snippet["description"],
                    "custom_url": snippet.get("customUrl"),
                    "published_at": snippet["publishedAt"],
                    "thumbnail": snippet["thumbnails"].get("high", {}).get("url"),
                    "subscriber_count": int(stats.get("subscriberCount", 0)),
                    "video_count": int(stats.get("videoCount", 0)),
                    "view_count": int(stats.get("viewCount", 0))
                }
            }

        except Exception as e:
            return self._handle_error(e)

    async def get_transcript(
            self,
            video_id: str,
            languages: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Gets video transcript/captions."""
        extracted_id = VideoIDExtractor.extract(video_id)
        if not extracted_id:
            return {"success": False, "error": "Invalid video ID or URL"}

        try:
            from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

            # Try to get transcript
            if languages:
                transcript_list = await asyncio.to_thread(
                    YouTubeTranscriptApi.get_transcript,
                    extracted_id,
                    languages=languages
                )
            else:
                transcript_list = await asyncio.to_thread(
                    YouTubeTranscriptApi.get_transcript,
                    extracted_id
                )

            # Format transcript
            full_text = " ".join([entry["text"] for entry in transcript_list])

            return {
                "success": True,
                "transcript": full_text,
                "segments": transcript_list,
                "segment_count": len(transcript_list)
            }

        except ImportError:
            return {
                "success": False,
                "error": "youtube-transcript-api is not installed"
            }
        except Exception as e:
            error_str = str(e).lower()
            if "disabled" in error_str or "no transcript" in error_str:
                return {"success": False, "error": "Transcript not available for this video"}
            return {"success": False, "error": str(e)}

    def _handle_error(self, error: Exception) -> Dict[str, Any]:
        """Handles API errors."""
        error_str = str(error).lower()

        if "quota" in error_str:
            return {
                "success": False,
                "error": "YouTube API quota exceeded. Please try again later.",
                "error_code": "QUOTA_EXCEEDED"
            }

        if "forbidden" in error_str or "403" in error_str:
            return {
                "success": False,
                "error": "Access denied. Check API key permissions.",
                "error_code": "FORBIDDEN"
            }

        if "not found" in error_str or "404" in error_str:
            return {
                "success": False,
                "error": "Resource not found",
                "error_code": "NOT_FOUND"
            }

        logger.error(f"YouTube API error: {error}")
        return {"success": False, "error": str(error)}


# ============================================================
# YOUTUBE NODE
# ============================================================

class YouTubeNode(BaseNode):
    """
    YouTube Integration Node.

    Features:
    - Video search with filters
    - Video details and statistics
    - Comment extraction
    - Transcript/caption extraction
    - Channel information
    - Quota handling
    - Large content offloading

    Operations:
    - search_videos: Search YouTube
    - get_video_details: Get video info
    - get_video_comments: Get comments
    - get_transcript: Get video transcript
    - get_channel_info: Get channel info
    """

    node_type = "youtubeNode"

    @classmethod
    def get_manifest(cls) -> Dict[str, Any]:
        return {
            "type": cls.node_type,
            "display_name": "YouTube",
            "icon": "Youtube",
            "category": "Media & Content",
            "description": "YouTube video search, details, comments, and transcript extraction.",
            "fields": [
                {
                    "name": "connection_id",
                    "label": "Google API Connection",
                    "type": "connection_select",
                    "provider": "GOOGLE",
                    "helper": "Or provide API key directly"
                },
                {
                    "name": "api_key",
                    "label": "API Key",
                    "type": "password",
                    "helper": "YouTube Data API v3 key"
                },
                {
                    "name": "operation",
                    "label": "Operation",
                    "type": "select",
                    "options": ["search_videos", "get_video_details", "get_video_comments", "get_transcript", "get_channel_info"],
                    "default": "search_videos"
                },
                {
                    "name": "query",
                    "label": "Search Query",
                    "type": "text",
                    "conditional": {"operation": "search_videos"}
                },
                {
                    "name": "video_id",
                    "label": "Video ID or URL",
                    "type": "text",
                    "conditional": {"operation": ["get_video_details", "get_video_comments", "get_transcript"]},
                    "helper": "YouTube video ID or full URL"
                },
                {
                    "name": "channel_id",
                    "label": "Channel ID",
                    "type": "text",
                    "conditional": {"operation": "get_channel_info"}
                },
                {
                    "name": "max_results",
                    "label": "Max Results",
                    "type": "number",
                    "default": 10,
                    "conditional": {"operation": ["search_videos", "get_video_comments"]}
                },
                {
                    "name": "order",
                    "label": "Sort Order",
                    "type": "select",
                    "options": ["relevance", "date", "viewCount", "rating"],
                    "default": "relevance",
                    "conditional": {"operation": "search_videos"}
                },
                {
                    "name": "video_duration",
                    "label": "Duration Filter",
                    "type": "select",
                    "options": ["any", "short", "medium", "long"],
                    "default": "any",
                    "conditional": {"operation": "search_videos"}
                },
                {
                    "name": "transcript_language",
                    "label": "Transcript Language",
                    "type": "text",
                    "placeholder": "en",
                    "conditional": {"operation": "get_transcript"},
                    "helper": "Language code (e.g., en, es, fr)"
                },
                {
                    "name": "offload_large",
                    "label": "Offload Large Results",
                    "type": "boolean",
                    "default": True
                }
            ],
            "outputs": ["status", "videos", "details", "comments", "transcript", "channel", "count"]
        }

    def __init__(self):
        super().__init__()
        self.config = YouTubeConfig()
        self.storage = StorageService()

    async def execute(
            self,
            db: AsyncSession,
            context: ExecutionContext,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes YouTube operation."""
        # Get API key
        api_key = await self._get_api_key(db, input_data)

        if not api_key:
            return {"status": "error", "error": "API key is required"}

        operation = input_data.get("operation", "search_videos")

        # Create client
        client = YouTubeClient(api_key, self.config)

        # Execute operation
        if operation == "search_videos":
            result = await self._search_videos(client, input_data)
        elif operation == "get_video_details":
            result = await self._get_video_details(client, input_data)
        elif operation == "get_video_comments":
            result = await self._get_video_comments(client, input_data, context)
        elif operation == "get_transcript":
            result = await self._get_transcript(client, input_data, context)
        elif operation == "get_channel_info":
            result = await self._get_channel_info(client, input_data)
        else:
            return {"status": "error", "error": f"Unknown operation: {operation}"}

        return result

    async def _get_api_key(
            self,
            db: AsyncSession,
            input_data: Dict[str, Any]
    ) -> Optional[str]:
        """Gets API key from connection or direct input."""
        connection_id = input_data.get("connection_id")

        if connection_id:
            result = await db.execute(
                select(Connection).where(Connection.id == connection_id)
            )
            conn = result.scalars().first()

            if conn:
                try:
                    creds = json.loads(crypto.decrypt(conn.encrypted_credentials))
                    return creds.get("api_key") or creds.get("youtube_api_key")
                except Exception as e:
                    logger.error(f"Failed to decrypt connection: {e}")

        return input_data.get("api_key")

    async def _search_videos(
            self,
            client: YouTubeClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executes video search."""
        query = input_data.get("query", "").strip()
        if not query:
            return {"status": "error", "error": "Search query is required"}

        max_results = min(int(input_data.get("max_results", 10)), 50)
        order = input_data.get("order", "relevance")
        video_duration = input_data.get("video_duration", "any")

        result = await client.search_videos(
            query=query,
            max_results=max_results,
            order=order,
            video_duration=video_duration
        )

        if not result.get("success"):
            return {"status": "error", "error": result.get("error")}

        return {
            "status": "success",
            "videos": result.get("videos", []),
            "count": result.get("count", 0),
            "total_results": result.get("total_results", 0)
        }

    async def _get_video_details(
            self,
            client: YouTubeClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Gets video details."""
        video_id = input_data.get("video_id", "").strip()
        if not video_id:
            return {"status": "error", "error": "Video ID is required"}

        result = await client.get_video_details(video_id)

        if not result.get("success"):
            return {"status": "error", "error": result.get("error")}

        return {
            "status": "success",
            "details": result.get("details")
        }

    async def _get_video_comments(
            self,
            client: YouTubeClient,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """Gets video comments with optional offloading."""
        video_id = input_data.get("video_id", "").strip()
        if not video_id:
            return {"status": "error", "error": "Video ID is required"}

        max_results = min(int(input_data.get("max_results", 100)), 100)

        result = await client.get_video_comments(video_id, max_results)

        if not result.get("success"):
            return {"status": "error", "error": result.get("error")}

        comments = result.get("comments", [])

        # Check if offloading needed
        if input_data.get("offload_large", True):
            comments_text = json.dumps(comments, indent=2)
            if len(comments_text) > self.config.storage_threshold_bytes:
                try:
                    storage_uri = await self.storage.upload_artifact(
                        execution_id=context.execution_id,
                        node_id=self.node_type,
                        content=comments_text,
                        filename=f"comments_{VideoIDExtractor.extract(video_id)}.json"
                    )
                    if storage_uri:
                        return {
                            "status": "success",
                            "comments": storage_uri,
                            "count": len(comments),
                            "is_offloaded": True
                        }
                except Exception as e:
                    logger.warning(f"Failed to offload comments: {e}")

        return {
            "status": "success",
            "comments": comments,
            "count": len(comments),
            "is_offloaded": False
        }

    async def _get_transcript(
            self,
            client: YouTubeClient,
            input_data: Dict[str, Any],
            context: ExecutionContext
    ) -> Dict[str, Any]:
        """Gets video transcript with optional offloading."""
        video_id = input_data.get("video_id", "").strip()
        if not video_id:
            return {"status": "error", "error": "Video ID is required"}

        language = input_data.get("transcript_language")
        languages = [language] if language else None

        result = await client.get_transcript(video_id, languages)

        if not result.get("success"):
            return {"status": "error", "error": result.get("error")}

        transcript = result.get("transcript", "")

        # Check if offloading needed
        if input_data.get("offload_large", True) and len(transcript) > self.config.storage_threshold_bytes:
            try:
                storage_uri = await self.storage.upload_artifact(
                    execution_id=context.execution_id,
                    node_id=self.node_type,
                    content=transcript,
                    filename=f"transcript_{VideoIDExtractor.extract(video_id)}.txt"
                )
                if storage_uri:
                    return {
                        "status": "success",
                        "transcript": storage_uri,
                        "segment_count": result.get("segment_count", 0),
                        "is_offloaded": True
                    }
            except Exception as e:
                logger.warning(f"Failed to offload transcript: {e}")

        return {
            "status": "success",
            "transcript": transcript,
            "segments": result.get("segments", []),
            "segment_count": result.get("segment_count", 0),
            "is_offloaded": False
        }

    async def _get_channel_info(
            self,
            client: YouTubeClient,
            input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Gets channel information."""
        channel_id = input_data.get("channel_id", "").strip()
        if not channel_id:
            return {"status": "error", "error": "Channel ID is required"}

        result = await client.get_channel_info(channel_id)

        if not result.get("success"):
            return {"status": "error", "error": result.get("error")}

        return {
            "status": "success",
            "channel": result.get("channel")
        }