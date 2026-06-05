import asyncio
import json
from typing import List, Dict, AsyncGenerator
from loguru import logger
import httpx
from urllib.parse import urlparse, urlunparse

from src.schemas.llm import BaseLLMConfig
from src.services.llm import LLMService
from src.services.agents.llm_tasks import generate_general_chat_response
from src.services.search_providers.serper_provider import SerperProvider
from src.services.search_providers.serpapi_provider import SerpApiProvider
from src.services.crawl4ai_service import Crawl4AIService

class WebSearchUnavailableError(Exception):
    pass

def _normalize_domain(link: str) -> str:
    """Normalizes a URL to its base domain for deduplication."""
    try:
        parsed = urlparse(link)
        return parsed.netloc or ""
    except (ValueError, TypeError):
        return ""

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
    def __init__(self, query: str, async_client: httpx.AsyncClient, crawler_service: Crawl4AIService, selected_model: str):
        self.query = query
        self.selected_model = selected_model
        self.async_client = async_client
        self.crawler_service = crawler_service
        self.llm_service = LLMService(BaseLLMConfig(model="llama-3.3-70b-versatile", provider="groq"))
        self.search_providers = [
            SerperProvider(self.async_client),
            SerpApiProvider(self.async_client),
        ]

    async def _generate_search_queries(self) -> List[str]:
        prompt = f"""
        Based on the user's query: "{self.query}", generate three alternative, highly relevant, and specific search engine queries to gather comprehensive information.
        Return ONLY a valid JSON array of strings. Do NOT include explanations.
        Example: ["scientific evidence for keto diet", "long-term health effects of ketogenic diet", "keto diet for athletic performance"]
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
                logger.info(f"Generated alternate queries: {queries}")
                return [self.query] + queries[:3]
            return [self.query]
        except Exception as e:
            logger.warning(f"Failed to generate search queries, using original query. Error: {e}")
            return [self.query, f"{self.query} benefits", f"{self.query} risks"]

    async def _find_relevant_urls(self, query: str) -> List[Dict[str, str]]:
        for provider in self.search_providers:
            if provider.is_configured():
                try:
                    logger.info(f"Finding URLs for '{query}' using {provider.name}.")
                    results = await provider.search(query)
                    if results: return results
                except Exception as e:
                    provider._log_failure(query, e)
        return []

    async def search_and_respond(self) -> AsyncGenerator[Dict, None]:
        try:
            yield {"type": "status", "data": "Analyzing query and preparing search strategy..."}
            search_queries = await self._generate_search_queries()

            yield {"type": "status", "data": f"Searching the web with {len(search_queries)} queries..."}
            search_tasks = [self._find_relevant_urls(q) for q in search_queries]
            all_results = await asyncio.gather(*search_tasks)

            unique_urls = {}
            unique_domains = set()
            for result_list in all_results:
                for result in result_list:
                    link = result.get("link")
                    if not link:
                        continue

                    domain = _normalize_domain(link)
                    if link not in unique_urls and domain not in unique_domains:
                        unique_urls[link] = result
                        if domain:
                            unique_domains.add(domain)

            urls_found = list(unique_urls.values())
            if not urls_found:
                yield {"type": "final_response", "data": "I searched the web, but couldn't find any relevant pages."}
                return

            urls_to_crawl = [r.get("link") for r in urls_found][:5]
            yield {"type": "status", "data": f"Reading {len(urls_to_crawl)} pages with advanced crawling..."}

            scraped_contents = await self.crawler_service.crawl_many_and_extract_content(urls_to_crawl)
            combined_context = _join_with_cap(scraped_contents, cap=15000)

            if not combined_context.strip():
                yield {"type": "final_response", "data": "I found web pages but was unable to extract their content."}
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
            yield {"type": "final_response", "data": "An unexpected error occurred while processing your request."}

    async def _synthesize_response_stream(self, context: str, urls: list) -> AsyncGenerator[str, None]:
        system_prompt = f"""
        Based on the high-quality context extracted from web pages, provide a comprehensive, accurate, and confident answer to the user's query: "{self.query}".
        The answer should be well-structured and easy to understand. Cite the sources used by referencing their links from the list provided.

        Context:
        {context}

        Sources available for citation: {json.dumps(urls)}

        Answer:
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self.query},
        ]

        async for token in generate_general_chat_response(
            messages=messages, model_name=self.selected_model
        ):
            yield token