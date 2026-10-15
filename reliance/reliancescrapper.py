import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


class RelianceDigitalScraper:
    def __init__(self, url, headless=True):
        self.url = url
        self.headless = headless
        self.product_info = {
            'price': None,
            'status': 'unknown'  # ok, out_of_stock, price_unavailable, not_found, fetch_error
        }

        html = self.fetch_html()
        if not html:
            self.product_info['status'] = 'fetch_error'
            return

        self.soup = BeautifulSoup(html, 'html.parser')
        self.product_info = self.get_product_info()

    def fetch_html(self):
        """Use a real Chromium browser via Playwright to bypass bot detection."""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-infobars",
                        "--window-size=1280,800",
                    ],
                )
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800},
                    locale="en-IN",
                    timezone_id="Asia/Kolkata",
                    extra_http_headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        "Accept-Language": "en-IN,en;q=0.9",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "none",
                        "Sec-Fetch-User": "?1",
                        "Upgrade-Insecure-Requests": "1",
                    },
                )
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-IN', 'en']});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    window.chrome = { runtime: {} };
                """)

                page = context.new_page()
                response = page.goto(self.url, timeout=30000, wait_until="domcontentloaded")

                if response is None:
                    print("Error: No response received from page.")
                    browser.close()
                    return None

                if response.status == 403:
                    print(f"Error: Blocked by site (status code: {response.status}).")
                    browser.close()
                    return None

                if response.status not in (200, 404):
                    print(f"Error: Unable to fetch HTML content. Status code: {response.status}")
                    browser.close()
                    return None

                # Dismiss a location/pincode popup if one appears (Reliance Digital
                # sometimes shows a "Select delivery location" style modal, similar
                # to Croma). Try filling a pincode, else fall back to closing it.
                try:
                    pincode_input = page.locator(
                        "input[placeholder*='pincode' i], input[placeholder*='pin code' i]"
                    ).first
                    if pincode_input.is_visible(timeout=4000):
                        pincode_input.fill("400049")
                        confirm_button = page.get_by_text(
                            re.compile("apply|continue|submit", re.I)
                        ).first
                        if confirm_button.is_visible():
                            confirm_button.click()
                        page.wait_for_timeout(1500)
                except Exception:
                    try:
                        close_icon = page.locator(
                            "[class*='close' i], button[aria-label*='close' i]"
                        ).first
                        if close_icon.is_visible(timeout=2000):
                            close_icon.click()
                            page.wait_for_timeout(1000)
                    except Exception:
                        pass  # No popup — safe to continue

                # Wait for price content to render
                try:
                    page.wait_for_selector("text=/\\u20b9/", timeout=8000)
                except Exception:
                    pass

                html = page.content()
                browser.close()
                return html

        except Exception as e:
            print(f"Request failed: {e}")
            return None

    def get_product_info(self):
        if not self.soup:
            return {'price': None, 'status': 'fetch_error'}

        page_text = self.soup.get_text(" ", strip=True).lower()

        # --- Detect invalid / removed product pages ---
        not_found_signals = [
            "page not found",
            "we can't find the page you're looking for",
            "404",
        ]
        if any(sig in page_text for sig in not_found_signals):
            return {'price': None, 'status': 'not_found'}

        # --- Out of stock / discontinued detection ---
        out_of_stock_signals = [
            "out of stock",
            "currently unavailable",
            "sold out",
            "this product has been discontinued",
            "notify me",  # Reliance Digital shows "Notify Me" instead of price/buy button when OOS
        ]
        is_out_of_stock = any(sig in page_text for sig in out_of_stock_signals)

        # --- Price extraction ---
        price = None

        # Try common Reliance Digital price class patterns first
        price_element = (
            self.soup.find('span', {'class': re.compile(r'price', re.I)}) or
            self.soup.find('div', {'class': re.compile(r'price', re.I)}) or
            self.soup.find('h2', {'class': re.compile(r'price', re.I)})
        )
        if price_element:
            text = price_element.get_text().strip()
            match = re.search(r'\u20b9[\d,]+(\.\d+)?', text)
            if match:
                price = match.group(0)

        # Fallback: generic pattern scan for a rupee-formatted number,
        # skipping struck-through (MRP/original price) elements
        if not price:
            price_pattern = re.compile(r'^\u20b9[\d,]+(\.\d+)?$')
            for tag in self.soup.find_all(['span', 'div', 'h2']):
                text = tag.get_text().strip()
                if price_pattern.match(text):
                    classes = ' '.join(tag.get('class') or [])
                    style = tag.get('style') or ''
                    if ('strike' in classes.lower() or 'line-through' in style.lower()
                            or 'mrp' in classes.lower() or 'old-price' in classes.lower()):
                        continue  # skip original/MRP price
                    price = text
                    break

        # --- Determine overall status ---
        if is_out_of_stock:
            status = 'out_of_stock'
            price = None  # don't report a stale price for unavailable items
        elif not price:
            status = 'price_unavailable'
        else:
            status = 'ok'

        return {
            'price': price,
            'status': status,
        }

    def get_price(self):
        return self.product_info.get('price') or 'Price not found'

    def get_status(self):
        return self.product_info.get('status')


# Execution
if __name__ == "__main__":
    urls = [
       "https://www.reliancedigital.in/product/apple-iphone-17e-256-gb-black-mmbrg8-9968387",
"https://www.reliancedigital.in/product/apple-ipad-air-m4-3278-cm-13-inch-wi-fi-tablet-128-gb-starlight-2026-mh5q4hna-mmaivc-9967346",
"https://www.reliancedigital.in/product/apple-ipad-air-m4-2759-cm-11-inch-wi-fi-tablet-128-gb-space-grey-2026-mh304hna-mmai6w-9967316",
"https://www.reliancedigital.in/product/apple-ipad-pro-m5-3302-cm-13-inch-wifi-tablet-with-standard-glass-1-tb-space-black-2025-mgt8c0-9550061",
"https://www.reliancedigital.in/product/apple-ipad-pro-m5-2794-cm-11-inch-wifi-tablet-with-standard-glass-1-tb-space-black-2025-mgt9lt-9550131",
"https://www.reliancedigital.in/product/apple-iphone-17-pro-max-512-gb-silver-mff2k1-9387383",
"https://www.reliancedigital.in/product/apple-iphone-17-pro-256-gb-silver-mff5yc-9388031",
"https://www.reliancedigital.in/product/apple-iphone-air-1-tb-sky-blue-mff4c6-9387516",
    ]

    for url in urls:
        print("=" * 80)
        print(url)
        r = RelianceDigitalScraper(url, headless=True)
        status = r.get_status()
        if status == 'fetch_error':
            print("Could not fetch the page. Check URL, network, or the site may still be blocking automated browsers.")
        elif status == 'not_found':
            print("Product page not found / invalid link.")
        elif status == 'out_of_stock':
            print("Product is out of stock / unavailable.")
        elif status == 'price_unavailable':
            print("Price not available on this page.")
        else:
            print("Price:", r.get_price())

