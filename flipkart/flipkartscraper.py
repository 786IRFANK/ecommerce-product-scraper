from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


class FlipkartScraper:
    def __init__(self, url, headless=True):
        self.url = url
        self.headless = headless
        self.product_info = {
            'price': None,
            'image_url': None,
            'in_stock': False,
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
                    ],
                )
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800},
                    locale="en-US",
                )
                # Hide the navigator.webdriver flag that sites use to detect automation
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

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

                if response.status != 200:
                    print(f"Error: Unable to fetch HTML content. Status code: {response.status}")
                    browser.close()
                    return None

                # Give the page a moment to render dynamic price/image content.
                # Flipkart changes its CSS class names often, so instead of waiting
                # on a specific class we just wait for any element containing a
                # rupee sign, which is far more stable.
                try:
                    page.wait_for_selector("text=/\\u20b9/", timeout=8000)
                except Exception:
                    # Not found in time — page may show out-of-stock or a
                    # different layout; continue anyway and let parsing handle it.
                    pass

                html = page.content()
                browser.close()
                return html

        except Exception as e:
            print(f"Request failed: {e}")
            return None

    def get_product_info(self):
        if not self.soup:
            return {'price': None, 'image_url': None, 'in_stock': False, 'status': 'fetch_error'}

        page_text = self.soup.get_text(" ", strip=True).lower()

        # --- Detect invalid / removed product pages ---
        not_found_signals = [
            "page not found",
            "sorry, this page isn't available",
            "product no longer available",
        ]
        if any(sig in page_text for sig in not_found_signals):
            return {'price': None, 'image_url': None, 'in_stock': False, 'status': 'not_found'}

        # --- Out of stock detection ---
        out_of_stock_signals = ["sold out", "out of stock", "currently unavailable"]
        is_out_of_stock = any(sig in page_text for sig in out_of_stock_signals)

        # --- Price extraction ---
        # Flipkart renames its price CSS classes frequently (Nx9bqj, _30jeq3,
        # _16Jk6d have all been used at different times), so class-based lookups
        # go stale fast. Instead, search all elements for a short piece of text
        # that looks like a rupee price (e.g. "₹39,599") and isn't a struck-through
        # original-price or a "X% off" line.
        import re
        price = None

        # Try known class names first (fast path, works if they haven't changed)
        price_element = (
            self.soup.find('div', {'class': 'Nx9bqj'}) or
            self.soup.find('div', {'class': '_30jeq3'}) or
            self.soup.find('div', {'class': '_16Jk6d'})
        )
        if price_element:
            price = price_element.get_text().strip()

        # Fallback: scan for a rupee-prefixed number in a short text node,
        # skipping ones that carry a "line-through" style (original/MRP price)
        if not price:
            price_pattern = re.compile(r'^\u20b9[\d,]+(\.\d+)?$')
            candidates = []
            for tag in self.soup.find_all(['div', 'span']):
                text = tag.get_text().strip()
                if price_pattern.match(text):
                    style = (tag.get('style') or '') + ' '.join(tag.get('class') or [])
                    is_struck_through = 'line-through' in style.lower()
                    if not is_struck_through:
                        candidates.append(text)
            if candidates:
                # The current/selling price is usually the first plain (non-struck)
                # rupee value that appears near the top of the product info section
                price = candidates[0]

        # --- Image extraction ---
        image_url = None
        img_element = (
            self.soup.find('img', {'class': 'DByuf4'}) or
            self.soup.find('img', {'class': '_396cs4'}) or
            self.soup.find('img', {'class': '_2r_T1I'})
        )
        if img_element:
            image_url = img_element.get('src') or img_element.get('data-src')

        # Fallback: og:image meta tag — usually stable regardless of class name changes
        if not image_url:
            og_image = self.soup.find('meta', {'property': 'og:image'})
            if og_image and og_image.get('content'):
                image_url = og_image['content']

        # --- Determine overall status ---
        if is_out_of_stock or not price:
            status = 'out_of_stock' if is_out_of_stock else 'price_unavailable'
            in_stock = False
        else:
            status = 'ok'
            in_stock = True

        return {
            'price': price,
            'image_url': image_url,
            'in_stock': in_stock,
            'status': status,
        }

    def get_price(self):
        return self.product_info.get('price') or 'Price not found'

    def get_image_url(self):
        return self.product_info.get('image_url') or 'Image not found'

    def get_status(self):
        return self.product_info.get('status')

    def is_in_stock(self):
        return self.product_info.get('in_stock')


# Execution
if __name__ == "__main__":
    urls = [
       "https://www.flipkart.com/apple-iphone-17e-black-256-gb/p/itm52965cb6acfcd",
"https://www.flipkart.com/apple-ipad-air-128-gb-rom-13-0-inch-wi-fi-only-m4-chip-space-grey/p/itma8c25951d9058?pid=TABHH62JTA3CKTVT&lid=LSTTABHH62JTA3CKTVTENXSAS&hl_lid=&marketplace=FLIPKART&fm=eyJ3dHAiOiJyZWNvIiwicHJwdCI6InBwIiwibWlkIjoicHJvZHVjdFJlY29tbWVuZGF0aW9uL2FzcGVjdFNpbWlsYXIifQ%3D%3D",
"https://www.flipkart.com/apple-ipad-air-256-gb-rom-11-0-inch-wi-fi-only-m4-chip-blue/p/itm76f019a29501b?pid=TABHH62JGF9AHDGC&lid=LSTTABHH62JGF9AHDGCYMMK2U&hl_lid=&marketplace=FLIPKART&fm=eyJ3dHAiOiJyZWNvIiwicHJwdCI6InBwIiwibWlkIjoicHJvZHVjdFJlY29tbWVuZGF0aW9uL3NpbWlsYXIifQ%3D%3D",
"https://www.flipkart.com/apple-2025-ipad-pro-m5-16-gb-ram-1-tb-rom-13-0-inch-wi-fi-5g-m5-chip-space-black/p/itm6ef4f0ecc9e5e?pid=TABHGWU3RREBUVG6",
"https://www.flipkart.com/apple-2025-ipad-pro-m5-12-gb-ram-256-rom-11-0-inch-wi-fi-only-space-black/p/itm6078d862a86a9",
"https://www.flipkart.com/apple-iphone-17-pro-max-cosmic-orange-256-gb/p/itmd38e30731883a",
"https://www.flipkart.com/apple-iphone-17-pro-silver-256-gb/p/itm106f475c264c7",
"https://www.flipkart.com/apple-iphone-air-space-black-256-gb/p/itm98092611013dd",

    ]

    for index, url in enumerate(urls, start=1):
        print(f"\n--- Processing Product {index}/{len(urls)} ---")
        f = FlipkartScraper(url, headless=True)

        status = f.get_status()
        if status == 'fetch_error':
            print("Could not fetch the page. Check URL, network, or anti-bot blocking.")
        elif status == 'not_found':
            print("Product page not found / removed.")
        elif status == 'out_of_stock':
            print("Product is out of stock.")
            print("Image:", f.get_image_url())
        elif status == 'price_unavailable':
            print("Price not available on this page.")
            print("Image:", f.get_image_url())
        else:
            print("Price:", f.get_price())
            print("Image:", f.get_image_url())
