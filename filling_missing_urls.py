import pandas as pd
import json
import random
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth

# Map platforms to their respective URL column names in your CSV
PLATFORM_URL_COLS = {
    "amazon": "Amazon_Link",
    "flipkart": "Flipkart_Link",
    "croma": "Croma_Link",
    "reliance": "Reliance_Link"
}

SOURCE_NAMES = {
    "amazon": "Amazon",
    "flipkart": "Flipkart",
    "reliance": "Reliance Digital",
    "croma": "Croma",
}


def create_search_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)

    stealth(
        driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )

    driver.get("https://www.google.com")
    return driver


def human_type(element, text):
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.05, 0.18))


def wait_out_captcha(driver):
    page_source = driver.page_source.lower()
    if "recaptcha" in page_source or "/sorry/" in driver.current_url:
        print("\n⚠️ Google is showing a CAPTCHA. Please solve it manually in the browser window...")
        input("Press Enter here once you've solved it and the results page loaded... ")


def is_product_url(url):
    url_lower = url.lower()
    if "amazon." in url_lower:
        return "/dp/" in url_lower or "/gp/product/" in url_lower
    if "flipkart.com" in url_lower:
        return "/p/itm" in url_lower
    if "reliancedigital.in" in url_lower:
        return "/product/" in url_lower
    if "croma.com" in url_lower:
        return "/p/" in url_lower
    return True


def get_site_key(url):
    url_lower = url.lower()
    if "amazon." in url_lower:
        return "amazon"
    if "flipkart.com" in url_lower:
        return "flipkart"
    if "reliancedigital.in" in url_lower:
        return "reliance"
    if "croma.com" in url_lower:
        return "croma"
    return None


def google_search_products(driver, query):
    wait = WebDriverWait(driver, 15)
    try:
        driver.get("https://www.google.com")
        search = wait.until(EC.presence_of_element_located((By.NAME, "q")))
        search.click()
        human_type(search, query)
        time.sleep(random.uniform(0.4, 1.0))
        search.send_keys(Keys.RETURN)

        try:
            wait.until(EC.presence_of_element_located((By.ID, "search")))
        except Exception:
            wait_out_captcha(driver)
            wait.until(EC.presence_of_element_located((By.ID, "search")))

        allowed_domains = ["amazon.in", "amazon.com", "flipkart.com", "croma.com", "reliancedigital.in"]
        invalid_keywords = ["google.com", "accounts.google", "policies.google", "/aclk", "#"]

        links = set()
        for a in driver.find_elements(By.TAG_NAME, "a"):
            try:
                href = a.get_attribute("href")
                if not href:
                    continue
                href = href.strip()
                if any(x in href for x in invalid_keywords) or href.endswith("#"):
                    continue
                href = href.split("#")[0].replace("http://", "https://")

                if any(domain in href.lower() for domain in allowed_domains):
                    links.add(href)
            except Exception:
                pass

        return links
    except Exception as e:
        print(f"Error during search: {e}")
        return set()


def process_csv(input_csv, output_csv):
    df = pd.read_csv(input_csv)
    driver = create_search_driver()

    try:
        for idx, row in df.iterrows():
            brand = str(row.get("Brand", "")).strip() if pd.notna(row.get("Brand")) else ""
            model = str(row.get("Model", "")).strip() if pd.notna(row.get("Model")) else ""
            
            product_name = f"{brand} {model}".strip()
            if not product_name:
                continue

            # Identify which platforms are missing URLs for this row
            missing_platforms = []
            for platform, col in PLATFORM_URL_COLS.items():
                val = row.get(col)
                if pd.isna(val) or str(val).strip() == "" or not str(val).strip().startswith("http"):
                    missing_platforms.append(platform)

            # If all URLs are already filled, skip searching
            if not missing_platforms:
                continue

            # Construct query targeting only the platforms with missing links
            platform_keywords = " ".join([SOURCE_NAMES[p] for p in missing_platforms])
            query = f"{product_name} price in {platform_keywords}"

            print("\n" + "=" * 80)
            print(f"Row {idx + 1}: Searching missing URLs for '{product_name}'")
            print(f"Target Platforms: {missing_platforms}")
            print(f"Query: {query}")
            print("=" * 80)

            found_urls = google_search_products(driver, query)

            # Update missing fields in DataFrame if a matching product URL is found
            for url in found_urls:
                site_key = get_site_key(url)
                if site_key in missing_platforms and is_product_url(url):
                    url_col = PLATFORM_URL_COLS[site_key]
                    
                    # Update column only if it's currently empty
                    if pd.isna(df.at[idx, url_col]) or str(df.at[idx, url_col]).strip() == "":
                        df.at[idx, url_col] = url
                        print(f"  [+] Updated {SOURCE_NAMES[site_key]} URL: {url}")

            # Save progress incrementally after each search
            df.to_csv(output_csv, index=False)

            # Human delay between Google searches
            delay = random.uniform(15, 30)
            print(f"Waiting {delay:.0f}s before next row search...")
            time.sleep(delay)

    finally:
        driver.quit()

    print(f"\nProcessing complete! Updated CSV saved to: {output_csv}")


if __name__ == "__main__":
    INPUT_CSV = "data/mobile_products_final.csv"
    OUTPUT_CSV = "data/mobile_products_final_urls.csv"
    
    process_csv(INPUT_CSV, OUTPUT_CSV)