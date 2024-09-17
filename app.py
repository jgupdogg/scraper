# app.py

from fastapi import FastAPI, HTTPException, Security, Depends, Request
from fastapi.security.api_key import APIKeyHeader, APIKey
from starlette.status import HTTP_403_FORBIDDEN
from pydantic import BaseModel, HttpUrl
from typing import Optional
from ud_scraper import UDScraper
import os
import logging


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Retrieve API key from environment variable
API_KEY = os.environ.get("API_KEY")
if not API_KEY or API_KEY == "default-api-key":
    logger.error("API_KEY environment variable not set or default value used")
    raise RuntimeError("API_KEY environment variable not set or default value used")

API_KEY_NAME = "Access-Token"  # Ensure this matches the client
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Define request and response models
class ScrapeRequest(BaseModel):
    url: HttpUrl
    use_proxy: Optional[bool] = True

class ScrapeResponse(BaseModel):
    data: str

# API key dependency
async def get_api_key(api_key_header: str = Security(api_key_header)):
    logger.info(f"Expected API_KEY: {API_KEY}")
    logger.info(f"Received access_token: {api_key_header}")
    if api_key_header == API_KEY:
        return api_key_header
    else:
        logger.warning("Invalid API key received")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Could not validate credentials"
        )

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/scrape", response_model=ScrapeResponse)
async def scrape(
    scrape_request: ScrapeRequest,
    api_key: str = Security(get_api_key)
):
    logger.info(f"Received scrape request for URL: {scrape_request.url} with use_proxy={scrape_request.use_proxy}")
    try:
        # Initialize the scraper
        scraper = UDScraper(use_proxy=scrape_request.use_proxy)

        # Make the request to the URL
        soup = scraper.make_request(scrape_request.url)
        if soup is None:
            logger.error("Failed to scrape the URL")
            raise HTTPException(status_code=500, detail="Failed to scrape the URL")

        # Convert the soup to a string
        html_content = str(soup)

        logger.info("Scraping successful")

        # Close the scraper driver
        scraper.close_driver()

        # Return the scraped HTML content
        return ScrapeResponse(data=html_content)
    except Exception as e:
        logger.exception("An error occurred during scraping")
        raise HTTPException(status_code=500, detail=str(e))