# ud_scraper.py

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup
import time
from datetime import timedelta, datetime
import random
import os
import tempfile
from proxy_pool import get_best_proxies 
import logging


# Scraper object with proxy pool and anti-bot detection
class UDScraper:
    proxy_pool_cache = []  # Class-level cache for proxies
    last_scraped_time = None  # Timestamp of the last proxy fetch
    PROXY_REFRESH_INTERVAL = timedelta(minutes=20)  # Time interval to refresh proxies

    def __init__(self, use_proxy=True):
        self.driver = None
        self.use_proxy = use_proxy
        current_time = datetime.now()

        # Check if proxies need to be refreshed (older than 20 minutes)
        if use_proxy and (not UDScraper.last_scraped_time or (current_time - UDScraper.last_scraped_time) > UDScraper.PROXY_REFRESH_INTERVAL):
            logging.info("Proxies are stale or not present. Fetching new proxies...")
            UDScraper.proxy_pool_cache = self.get_proxy_pool()
            UDScraper.last_scraped_time = current_time
            logging.info(f"Fetched and cached {len(UDScraper.proxy_pool_cache)} proxies.")
        else:
            logging.info(f"Using cached proxies. {len(UDScraper.proxy_pool_cache)} proxies available.")


    def get_proxy_pool(self):
        # Fetches fresh proxies from the proxy pool provider
        proxies = get_best_proxies()
        logging.info(f"Fetched {len(proxies)} fresh proxies from the provider.")
        return proxies

    def get_random_proxy(self):
        # Check if cached proxies are available
        if not UDScraper.proxy_pool_cache:
            logging.warning("Proxy pool cache is empty. Fetching new proxies.")
            UDScraper.proxy_pool_cache = self.get_proxy_pool()
            UDScraper.last_scraped_time = datetime.now()
        
        if UDScraper.proxy_pool_cache:
            proxy = random.choice(UDScraper.proxy_pool_cache)
            logging.info(f"Using proxy: {proxy['ip']}:{proxy['port']}")
            return proxy
        else:
            logging.error("No proxies available after fetch.")
            return None

    def setup_proxy_extension(self, proxy):
        # Use a temporary directory
        PROXY_FOLDER = os.path.join(tempfile.gettempdir(), 'ud_scraper_proxy_folder')
        os.makedirs(PROXY_FOLDER, exist_ok=True)

        manifest_json = """
        {
            "version": "1.0.0",
            "manifest_version": 3,
            "name": "Chrome Proxy",
            "permissions": [
                "proxy",
                "tabs",
                "storage",
                "webRequest",
                "webRequestAuthProvider"
            ],
            "host_permissions": [
                "<all_urls>"
            ],
            "background": {
                "service_worker": "background.js"
            },
            "minimum_chrome_version": "22.0.0"
        }
        """

        background_js = f"""
        var config = {{
            mode: "fixed_servers",
            rules: {{
                singleProxy: {{
                    scheme: "http",
                    host: "{proxy['ip']}",
                    port: parseInt({proxy['port']})
                }},
                bypassList: ["localhost"]
            }}
        }};

        chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});
        """

        with open(os.path.join(PROXY_FOLDER, "manifest.json"), "w") as f:
            f.write(manifest_json)
        with open(os.path.join(PROXY_FOLDER, "background.js"), "w") as f:
            f.write(background_js)

        return PROXY_FOLDER

    def setup_driver(self, proxy=None):
        print("Setting up driver...")
        logging.info("Setting up driver...")
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920x1080")
        options.add_argument("--disable-extensions")
        options.headless = True  # Run in headless mode

        if proxy:
            print(f"Using proxy: {proxy['ip']}:{proxy['port']}")
            proxy_folder = self.setup_proxy_extension(proxy)
            options.add_argument(f"--load-extension={proxy_folder}")
        else:
            print("Not using a proxy")

        # Specify the path to the Chrome binary
        chrome_binary_path = "/usr/bin/google-chrome"

        # Ensure chrome_binary_path is a string
        if not isinstance(chrome_binary_path, str):
            raise TypeError("Chrome binary path must be a string")

        # Set binary_location directly in options
        options.binary_location = chrome_binary_path

        try:
            driver = uc.Chrome(options=options)
        except Exception as e:
            print(f"Failed to initialize Chrome driver: {e}")
            raise

        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })
        print("Driver setup complete")
        return driver

    def make_request(self, url, max_retries=3):
        logging.info(f"Making request to {url} with max retries = {max_retries}")
        for attempt in range(max_retries):
            logging.info(f"Attempt {attempt + 1} of {max_retries}")
            proxy = self.get_random_proxy() if self.use_proxy else None
            self.driver = self.setup_driver(proxy)
            try:
                logging.info(f"Navigating to {url}")
                self.driver.get(url)
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                logging.info("Page loaded successfully.")
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                self.close_driver()
                return soup
            except (TimeoutException, WebDriverException) as e:
                logging.error(f"Attempt {attempt + 1} failed: {str(e)}")
                logging.info(f"Retrying{' with a new proxy' if self.use_proxy else ''}...")
                self.close_driver()
                time.sleep(2 ** attempt)  # Exponential backoff
        logging.error(f"Failed to fetch {url} after {max_retries} attempts.")
        return None

    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                logging.warning("Error during driver closure.")
            self.driver = None
