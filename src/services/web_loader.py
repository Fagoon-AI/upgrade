from typing import List
from loguru import logger


from src.loaders.web_page import WebPageLoader
from src.utils.common import async_time_execution


class WebPageLoaderService:
    """
    Service class to load content from multiple web pages using WebPageLoader.
    """

    def __init__(self, urls: List[str]) -> None:
        self.urls = urls
        self.loader = WebPageLoader()

    @async_time_execution
    async def get_content_from_url(self):
        """
        Fetches content from a list of URLs.

        Returns:
            List of web page content or None if an error occurs while fetching.
        """
        content = []

        for url in self.urls:
            try:
                page_content = self.loader.load_data(url)
                content.append(page_content)
            except Exception as e:
                logger.error(f"Error while fetching content from {url}: {e}")
                content.append(None)

        return content
