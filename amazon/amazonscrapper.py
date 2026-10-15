import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


class AmazonScraper:
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
                    locale="en-IN",
                )
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

                if response.status not in (200, 404):
                    # Amazon sometimes serves a 404 for a page that still renders a
                    # meaningful "unavailable" message, so we don't hard-fail on 404
                    print(f"Error: Unable to fetch HTML content. Status code: {response.status}")
                    browser.close()
                    return None

                # Wait for either the price block or the title block to render.
                # Amazon renames price classes too, but #corePrice_feature_div and
                # #productTitle have been stable identifiers for a long time.
                try:
                    page.wait_for_selector(
                        "#corePrice_feature_div, #productTitle, #title",
                        timeout=8000,
                    )
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
            return {'price': None, 'image_url': None, 'in_stock': False, 'status': 'fetch_error'}

        page_text = self.soup.get_text(" ", strip=True).lower()

        # --- Detect invalid / removed / dead product pages ---
        not_found_signals = [
            "sorry, we couldn't find that page",
            "page not found",
            "the web address you entered is not a functioning page",
            "looking for something?",
        ]
        # Amazon's 404 page usually has no #productTitle at all — use that as a
        # stronger signal than text matching alone
        has_title = self.soup.find(id='productTitle') is not None
        if any(sig in page_text for sig in not_found_signals) and not has_title:
            return {'price': None, 'image_url': None, 'in_stock': False, 'status': 'not_found'}

        # --- Out of stock / currently unavailable detection ---
        out_of_stock_signals = [
            "currently unavailable",
            "out of stock",
            "we don't know when or if this item will be back in stock",
        ]
        is_out_of_stock = any(sig in page_text for sig in out_of_stock_signals)

        # --- Price extraction ---
        price = None

        # Primary: the whole/current price, built from Amazon's split price spans.
        # Amazon renders price as: <span class="a-price-whole">39,599</span><span class="a-price-fraction">00</span>
        price_whole = self.soup.select_one('span.a-price:not(.a-text-price) span.a-price-whole')
        if price_whole:
            price = price_whole.get_text().strip().rstrip('.')
            price = f"\u20b9{price}"

        # Fallback 1: older/alternate price element ids
        if not price:
            price_element = (
                self.soup.find(id='priceblock_ourprice') or
                self.soup.find(id='priceblock_dealprice') or
                self.soup.find(id='priceblock_saleprice')
            )
            if price_element:
                price = price_element.get_text().strip()

        # Fallback 2: generic pattern scan for a rupee-formatted number,
        # skipping struck-through (MRP/list price) elements
        if not price:
            price_pattern = re.compile(r'^\u20b9[\d,]+(\.\d+)?$')
            for tag in self.soup.find_all(['span', 'div']):
                text = tag.get_text().strip()
                if price_pattern.match(text):
                    classes = ' '.join(tag.get('class') or [])
                    if 'a-text-price' in classes or 'text-decoration' in (tag.get('style') or ''):
                        continue  # skip original/MRP price
                    price = text
                    break

        # --- Image extraction ---
        image_url = None
        img_element = self.soup.find(id='landingImage') or self.soup.find(id='imgBlkFront')
        if img_element:
            image_url = img_element.get('src') or img_element.get('data-old-hires')

        # Fallback: og:image meta tag
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
        "https://www.amazon.in/Apple-iPhone-17e-256-GB/dp/B0GQVL6STN",
"https://www.amazon.in/Apple-iPad-Air-32-78-13%E2%80%B3/dp/B0GQVF818Z",
"https://www.amazon.in/Apple-iPad-Air-11%E2%80%B3-chip/dp/B0DZ78SLRY",
"https://www.amazon.in/Apple-iPad-Pro-13%E2%80%B3-M5/dp/B0FWD659TX",
"https://www.amazon.in/Apple-iPad-Pro-11%E2%80%B3-M5/dp/B0FWD7GNCD",
"https://www.amazon.in/iPhone-Pro-Max-256-Promotion/dp/B0FQFV2XKS",
"https://www.amazon.in/iPhone-Pro-256-Promotion-Breakthrough/dp/B0FQG1LPVF",
"https://www.amazon.in/iPhone-Air-256-GB-Promotion/dp/B0FQFTV1NP",
    ]

    for url in urls:
        print("=" * 80)
        print(url)
        a = AmazonScraper(url, headless=True)
        status = a.get_status()
        if status == 'fetch_error':
            print("Could not fetch the page. Check URL, network, or the site may still be blocking automated browsers.")
        elif status == 'not_found':
            print("Product page not found / invalid link.")
        elif status == 'out_of_stock':
            print("Product is currently unavailable / out of stock.")
            print("Image:", a.get_image_url())
        elif status == 'price_unavailable':
            print("Price not available on this page.")
            print("Image:", a.get_image_url())
        else:
            print("Price:", a.get_price())
            print("Image:", a.get_image_url())