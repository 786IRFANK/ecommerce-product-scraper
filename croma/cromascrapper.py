import re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


class CromaScraper:
    def __init__(self, url, pincode="400049", headless=True):
        self.url = url
        self.pincode = pincode
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
        """Use a real Chromium browser via Playwright to bypass bot detection
        and dismiss Croma's location/pincode popup before reading the page."""
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
                    print(f"Error: Unable to fetch HTML content. Status code: {response.status}")
                    browser.close()
                    return None

                # --- Handle the "SELECT YOUR LOCATION" pincode popup ---
                # As seen in the reference screenshot: an input field for pincode,
                # a "Continue" button, and a close ("X") icon. We try entering the
                # pincode and clicking Continue; if that fails for any reason we
                # fall back to just closing the popup so the page underneath is
                # still readable.
                try:
                    pincode_input = page.locator(
                        "input[placeholder*='pincode' i], input[type='text']"
                    ).first
                    pincode_input.wait_for(timeout=6000)
                    if pincode_input.is_visible():
                        pincode_input.fill(self.pincode)
                        continue_button = page.get_by_text("Continue", exact=False).first
                        if continue_button.is_visible():
                            continue_button.click()
                        page.wait_for_timeout(1500)
                except Exception:
                    # Popup didn't appear, or interacting with it failed.
                    # Try just closing it via the "X" icon as a fallback.
                    try:
                        close_icon = page.locator(
                            "[class*='close' i], button[aria-label*='close' i]"
                        ).first
                        if close_icon.is_visible(timeout=2000):
                            close_icon.click()
                            page.wait_for_timeout(1000)
                    except Exception:
                        pass  # No popup at all — safe to continue

                # Wait for price content to render after the popup is handled
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
        ]
        if any(sig in page_text for sig in not_found_signals):
            return {'price': None, 'status': 'not_found'}

        # --- Discontinued / out of stock detection ---
        # Croma shows an explicit "This item has been discontinued" message,
        # as well as "out of stock" / "currently unavailable" in other cases.
        out_of_stock_signals = [
            "this item has been discontinued",
            "out of stock",
            "currently unavailable",
            "sold out",
        ]
        is_out_of_stock = any(sig in page_text for sig in out_of_stock_signals)

        # --- Price extraction ---
        price = None

        # Try common Croma price class/id patterns first
        price_element = (
            self.soup.find('span', {'class': re.compile(r'amount', re.I)}) or
            self.soup.find('span', {'class': re.compile(r'price', re.I)}) or
            self.soup.find('div', {'class': re.compile(r'new-price', re.I)})
        )
        if price_element:
            text = price_element.get_text().strip()
            if re.match(r'^\u20b9[\d,]+(\.\d+)?$', text):
                price = text

        # Fallback: generic pattern scan for a rupee-formatted number,
        # skipping struck-through (MRP/original price) elements
        if not price:
            price_pattern = re.compile(r'^\u20b9[\d,]+(\.\d+)?$')
            for tag in self.soup.find_all(['span', 'div']):
                text = tag.get_text().strip()
                if price_pattern.match(text):
                    classes = ' '.join(tag.get('class') or [])
                    style = tag.get('style') or ''
                    if 'strike' in classes.lower() or 'line-through' in style.lower() or 'old-price' in classes.lower():
                        continue  # skip original/MRP price
                    price = text
                    break

        # --- Determine overall status ---
        if is_out_of_stock:
            status = 'out_of_stock'
            price = None  # discontinued items shouldn't report a stale price
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
        "https://www.croma.com/apple-iphone-17e-256gb-black-/p/317543?srsltid=AfmBOorn7O-KqJfsOhiOYurfdkqkhy-2uVkigGybnFuD1BQh3C3lSMdF",
"https://www.croma.com/apple-ipad-air-m4-wi-fi-13-inch-128gb-space-grey-2026-model-/p/320681?srsltid=AfmBOoodValocONOjFtKfZIPmUJ97l3FUgDYCFHLa6i0_4rc5M6aVs-n",
"https://www.croma.com/apple-ipad-air-m4-wi-fi-11-inch-128gb-space-grey-2026-model-/p/320688?srsltid=AfmBOoqgmmt4CuQ2KbeI0gVgUWF76PobjuYpz8tYw38XI-pp11zn9FMR",
"https://www.croma.com/apple-ipad-pro-m5-chip-wi-fi+5g-13-inch-2tb-silver-2025-model-/p/318875?srsltid=AfmBOop7IrsX51tnUyksocYKuGFiNdBxg-y3vgdCXVeiszYjizcieSag",
"https://www.croma.com/apple-ipad-pro-wi-fi-11-inch-256gb-space-black-2025-model-/p/318814?srsltid=AfmBOopu0zvUUdfVM9-MHiNaoHVb5733v8JISrYJhLbCyf-99AuxSjNe",
"https://www.croma.com/apple-iphone-17-pro-max-256gb-silver-/p/317432?srsltid=AfmBOoql0nrzFZIoU9K1oKt4Dh_HjyB3gra0N_kizCz4nFy9D8xq01QV",
"https://www.croma.com/apple-iphone-17-256gb-black-/p/317396?srsltid=AfmBOor-C70a68xNQ-m6kWC7hd3hB0QuGkQkZA-VP2_5brr50NUEthBX",
"https://www.croma.com/apple-iphone-air-256gb-sky-blue-/p/317458?srsltid=AfmBOorhJssMHOsLDkt3xkfVNB6XQU5B4LA6FVKrfIpKy2eSPegTCnz_",
"https://www.croma.com/apple-iphone-17-256gb-black-/p/317396?srsltid=AfmBOoqYCDbRMPs_anYWPkvRyCxni-pmmzY8swgSCPt0iN__VQ_eJayz",
"https://www.croma.com/apple-watch-ultra-3-gps+cellular-with-natural-titanium-milanese-loop-m-49mm-retina-ltpo3-oled-display-natural-titanium-case-/p/317416?srsltid=AfmBOor3KU24mUSlFaL5WCljIkJ_g5MXKJGTh7pkKNmFnxXInNTmC84D",
    ]

    for url in urls:
        print("=" * 80)
        print(url)
        c = CromaScraper(url, pincode="400049", headless=False)
        status = c.get_status()
        if status == 'fetch_error':
            print("Could not fetch the page. Check URL, network, or the site may still be blocking automated browsers.")
        elif status == 'not_found':
            print("Product page not found / invalid link.")
        elif status == 'out_of_stock':
            print("Product is discontinued / out of stock.")
        elif status == 'price_unavailable':
            print("Price not available on this page.")
        else:
            print("Price:", c.get_price())