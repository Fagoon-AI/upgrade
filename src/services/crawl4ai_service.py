import asyncio
from typing import List, Optional
from loguru import logger
from crawl4ai import AsyncWebCrawler

class Crawl4AIService:
    _crawler_instance: Optional[AsyncWebCrawler] = None
    _lock = asyncio.Lock()  # Lock to prevent race conditions during initialization
    _semaphore = asyncio.Semaphore(4)  # Limit concurrent crawling operations to 4

    def __init__(self):
        """
        Initializes the service placeholder. The actual crawler is initialized lazily.
        """
        logger.info("Crawl4AIService placeholder initialized. Crawler will be created on first use.")

    async def _get_crawler(self) -> AsyncWebCrawler:
        """
        Lazily initializes and returns the singleton AsyncWebCrawler instance.
        This ensures that the slow startup of Playwright/browsers doesn't block
        the main application's launch.
        """
        if self._crawler_instance:
            return self._crawler_instance

        async with self._lock:
            # Double-check locking pattern
            if self._crawler_instance is None:
                logger.info("Initializing singleton Crawl4AI instance...")
                self._crawler_instance = AsyncWebCrawler()
                logger.success("Crawl4AI singleton instance created. Browser will launch on first use.")
        return self._crawler_instance

    async def crawl_many_and_extract_content(self, urls: List[str]) -> List[str]:
        """
        Crawls multiple URLs and extracts their content, with concurrency control.
        It ensures the crawler is initialized before proceeding.
        """
        if not urls:
            return []

        crawler = await self._get_crawler()

        async with self._semaphore:
            logger.info(f"Crawling {len(urls)} URLs with shared Crawl4AI instance: {urls}")
            try:
                # Use wait_for to add a timeout to the overall crawl operation
                results = await asyncio.wait_for(crawler.arun_many(urls), timeout=60.0)
                scraped_contents = []
                for result in results:
                    if result.success:
                        content = result.markdown or result.text or ""
                        scraped_contents.append(content)
                        logger.success(f"Successfully scraped content from {result.url}")
                    else:
                        scraped_contents.append("")
                        logger.warning(f"Failed to crawl {result.url} with error: {result.error_message}")
                return scraped_contents
            except asyncio.TimeoutError:
                logger.error(f"Crawling timed out for URLs: {urls}")
                return [""] * len(urls)
            except Exception as e:
                logger.error(f"Crawl4AI failed to process multiple URLs: {e}", exc_info=True)
                return [""] * len(urls)

    async def close(self):
        """
        Gracefully closes the underlying AsyncWebCrawler instance, releasing browser resources.
        This method is idempotent and thread-safe.
        """
        async with self._lock:
            if self._crawler_instance:
                logger.info("Closing singleton Crawl4AI instance...")
                await self._crawler_instance.close()
                self._crawler_instance = None
                logger.success("Crawl4AI instance closed successfully.")