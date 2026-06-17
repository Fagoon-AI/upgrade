import asyncio
import json
import datetime
from typing import List, Dict, AsyncGenerator
from urllib.parse import urlparse

import httpx
from loguru import logger
from ddgs import DDGS

from src.schemas.llm import BaseLLMConfig
from src.services.llm import LLMService
from src.services.agents.llm_tasks import generate_general_chat_response
from src.services.crawl4ai_service import Crawl4AIService

# --- AGGRESSIVE SPAM & BOT SHIELD ---
# Blocks social media login walls, SEO content farms, and strict anti-bot domains
FORBIDDEN_DOMAINS = [
    "facebook.com", "twitter.com", "instagram.com", "youtube.com", "tiktok.com", 
    "linkedin.com", "pinterest.com", "reddit.com", "trendsnewsline.com", 
    "newsline", "live-blogs", "liveblog", "clickbait", "blogspot.com",
    "govinfo.gov", "adst.org", "ndi.org", "quora.com"
]

def _normalize_domain(link: str) -> str:
    """Normalizes a URL to its base domain for deduplication."""
    try:
        parsed = urlparse(link)
        return parsed.netloc.lower() or ""
    except (ValueError, TypeError):
        return ""

def _is_valid_link(link: str) -> bool:
    """Checks if a URL is safe to crawl (not a PDF or known spam/bot-trap site)."""
    if not link:
        return False
        
    link_lower = link.lower()
    if link_lower.endswith(".pdf"):
        return False
        
    domain = _normalize_domain(link)
    if any(bad in domain or bad in link_lower for bad in FORBIDDEN_DOMAINS):
        return False
        
    return True

def _join_with_cap(chunks: List[str], cap: int = 15000) -> str:
    """Efficiently joins strings up to a specified character capacity."""
    output, total_len = [], 0
    for chunk in chunks:
        if not chunk:
            continue
        needed = cap - total_len
        if needed <= 0:
            break
        piece = chunk[:needed]
        output.append(piece)
        total_len += len(piece)
    return "\n\n".join(output)


class WebSearchService:
    def __init__(
        self, 
        query: str, 
        async_client: httpx.AsyncClient, 
        crawler_service: Crawl4AIService, 
        selected_model: str, 
        history: list = None,
        groq_api_key: str = None,
        user_id: str = None
    ):
        self.query = query
        self.selected_model = selected_model
        self.async_client = async_client
        self.crawler_service = crawler_service
        self.history = history or [] 
        self.user_id = user_id
        self.llm_service = LLMService(
            BaseLLMConfig(
                model="llama-3.3-70b-versatile", 
                provider="groq", 
                api_key=groq_api_key
            )
        )

    async def _generate_search_queries(self) -> List[str]:
        now = datetime.datetime.now()
        current_date = now.strftime("%B %d, %Y")
        current_month_year = now.strftime("%B %Y")
        
        prompt = f"""
        Today's exact date is {current_date}.
        Based on the user's query: "{self.query}", generate three alternative, highly relevant, and specific search engine queries.
        CRITICAL RULE: If the user is asking for "current", "latest", or "now" information, you MUST append "{current_month_year}" or "{now.year}" to the end of your search queries to bypass old SEO rankings and force fresh news.
        Example: ["current home minister of Nepal {current_month_year}", "Nepal cabinet updates {current_date}"]
        Return ONLY a valid JSON array of strings. Do NOT include explanations.
        """
        try:
            response = await asyncio.wait_for(
                self.llm_service.chat_completion(user_query=self.query, system_prompt=prompt),
                timeout=5.0
            )
            cleaned_response = response.strip().replace("`", "")
            if cleaned_response.startswith("json"):
                cleaned_response = cleaned_response[4:].strip()

            queries = json.loads(cleaned_response)
            if isinstance(queries, list) and len(queries) > 0:
                logger.info("Generated alternate queries: {}", queries)
                return [self.query] + queries[:3]
            return [self.query]
        except Exception as e:
            logger.warning(f"Failed to generate search queries, using original query. Error: {e}")
            return [self.query, f"{self.query} updates", f"{self.query} latest news"]

    async def _find_relevant_urls(self, query: str) -> List[Dict[str, str]]:
        try:
            logger.info(f"Finding URLs for '{query}' using zero-key DuckDuckGo Search.")

            # --- CRITICAL FIX: Restoring the Time Filter ---
            # Detect if the user wants recent news to trigger DuckDuckGo's time filter
            query_lower = self.query.lower()
            needs_fresh_news = any(word in query_lower for word in ["current", "latest", "now", "today", "recent", "news", "update", "updates"])
            
            def fetch_ddg_payload():
                with DDGS() as ddgs:
                    if needs_fresh_news:
                        # Use news search instead of text search for fresh news (timelimit="w" for past week to ensure enough results)
                        return list(ddgs.news(query, max_results=15, timelimit="w"))
                    else:
                        return list(ddgs.text(query, max_results=15))

            raw_results = await asyncio.to_thread(fetch_ddg_payload)

            formatted_results = []
            for item in raw_results:
                link = item.get("url") or item.get("href", "")
                # Only add the URL if it passes our strict spam/PDF shield
                if _is_valid_link(link):
                    formatted_results.append({
                        "title": item.get("title", "Untitled Source"),
                        "link": link,
                        "snippet": item.get("body", "")
                    })
                    
            return formatted_results

        except Exception as e:
            logger.error(f"DuckDuckGo metasearch failed for request string '{query}': {e}")
            return []

    async def search_and_respond(self) -> AsyncGenerator[Dict, None]:
        try:
            yield {"type": "status", "data": "Analyzing query and preparing search strategy..."}
            search_queries = await self._generate_search_queries()

            yield {"type": "status", "data": f"Searching the web via DuckDuckGo with {len(search_queries)} queries..."}
            search_tasks = [self._find_relevant_urls(q) for q in search_queries]
            all_results = await asyncio.gather(*search_tasks, return_exceptions=True)

            unique_urls = {}
            unique_domains = set()
            
            for result_list in all_results:
                if isinstance(result_list, Exception) or not result_list:
                    continue
                    
                for result in result_list:
                    link = result.get("link")
                    domain = _normalize_domain(link)
                    
                    if link not in unique_urls and domain not in unique_domains:
                        unique_urls[link] = result
                        if domain:
                            unique_domains.add(domain)

            urls_found = list(unique_urls.values())
            if not urls_found:
                yield {"type": "final_response", "data": "I searched the web, but couldn't find any reliable or accessible pages."}
                return

            # Grab the top 5 squeaky-clean URLs
            urls_to_crawl = [r.get("link") for r in urls_found][:5]

            yield {"type": "status", "data": f"Reading {len(urls_to_crawl)} verified pages with advanced crawling..."}

            # --- THREAD ISOLATION WORKAROUND FOR WINDOWS RE-LOADER ---
            def isolated_proactor_crawl_worker(urls: List[str]) -> List[str]:
                from src.services.crawl4ai_service import Crawl4AIService
                
                async def execute_local_crawl():
                    local_service = Crawl4AIService()
                    return await local_service.crawl_many_and_extract_content(urls)
                    
                return asyncio.run(execute_local_crawl())

            scraped_contents = await asyncio.to_thread(isolated_proactor_crawl_worker, urls_to_crawl)
            # --------------------------------------------------------

            combined_context = _join_with_cap(scraped_contents, cap=15000)

            if not combined_context.strip():
                yield {"type": "final_response", "data": "I found web pages but was unable to extract their text content (they may have strict bot protection)."}
                return

            crawled_source_metadata = [
                {
                    "title": r.get("title"),
                    "link": r.get("link"),
                    "domain": _normalize_domain(r.get("link"))
                }
                for r in urls_found
                if r.get("link") in urls_to_crawl
            ]

            yield {"type": "metadata", "data": {"source_urls": crawled_source_metadata}}

            yield {"type": "status", "data": "Generating your answer from the extracted information..."}
            async for token in self._synthesize_response_stream(combined_context, urls_to_crawl):
                yield {"type": "llm_token", "data": token}

        except Exception as e:
            logger.error(f"An unexpected error in search_and_respond: {e}", exc_info=True)
            yield {"type": "final_response", "data": "An unexpected error occurred while processing your web search request."}

    async def _synthesize_response_stream(self, context: str, urls: list) -> AsyncGenerator[str, None]:
        now = datetime.datetime.now()
        today_date = now.strftime("%B %d, %Y")
        
        system_prompt = f"""
        Today's exact date is {today_date}. 
        Provide a comprehensive, accurate, and confident answer to the user's query based ONLY on the provided context.

        CRITICAL TEMPORAL INSTRUCTION: You are reading live web data. Verify the YEAR. Base your final answer ONLY on the absolute latest chronological date mentioned.

        TONE & STYLE: Be conversational, helpful, and answer in complete sentences. Do NOT use annoying meta-phrases like "According to the context" or "The text mentions." Just state the facts smoothly and use markdown link citations. 
        IMPORTANT: If the user asks for multiple pieces of information (e.g., two different political positions) and your context only contains one, provide the one you have and politely state that the current search results did not contain the other. Do not hallucinate missing data.

        Context:
        {context}

        Sources available for citation: {json.dumps(urls)}
        """
        
        messages = [{"role": "system", "content": system_prompt}]
        
        for msg in self.history:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })

        async for token in generate_general_chat_response(
            messages=messages, 
            model_name=self.selected_model,
            user_id=self.user_id,
            feature="chat"
        ):
            yield token