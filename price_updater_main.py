import argparse
import random
import shutil
import time
from pathlib import Path

import pandas as pd


# ============================================================
# IMPORT YOUR EXISTING SCRAPER CLASSES
# ============================================================
# CHANGE THESE IMPORTS according to your project structure.

from amazon.amazonscrapper import AmazonScraper
from flipkart.flipkartscraper import FlipkartScraper
from croma.cromascrapper import CromaScraper
from reliance.reliancescrapper import RelianceDigitalScraper


# ============================================================
# CONFIGURATION & FILE PATH SETTINGS
# ============================================================

# 📌 Yaha apna CSV File Path / File Name add karein:
CSV_FILE_PATH = "products.csv"  # Ya path: "C:/path/to/your/file.csv"

# 📌 Row Range Set Karein (e.g., 200 se 500 tak):
# Note: 1-indexed (Jaise Excel me dikhta hai, Header line ke baad 1st data row = 1)
START_ROW = 200  
END_ROW = 500    

AMAZON_LINK_COL = "Amazon_Link"
AMAZON_PRICE_COL = "Amazon_Price_INR"
AMAZON_IMAGE_COL = "Amazon_Image_URL"

FLIPKART_LINK_COL = "Flipkart_Link"
FLIPKART_PRICE_COL = "Flipkart_Price_INR"

CROMA_LINK_COL = "Croma_Link"
CROMA_PRICE_COL = "Croma_Price_INR"

RELIANCE_LINK_COL = "Reliance_Link"
RELIANCE_PRICE_COL = "Reliance_Price_INR"

# Random delay between products
MIN_DELAY = 3
MAX_DELAY = 7

# Croma pincode
CROMA_PINCODE = "400049"


# ============================================================
# HELPERS
# ============================================================

def format_price(price):
    if price is None:
        return ""

    try:
        value = float(price)

        if value.is_integer():
            return str(int(value))

        return str(value)

    except Exception:
        return str(price)


def is_valid_url(value):
    """
    Check whether CSV value contains a usable URL.
    """
    if pd.isna(value):
        return False

    value = str(value).strip()

    if not value:
        return False

    if value.lower() in ["nan", "none", "null", "n/a", "na"]:
        return False

    if not value.startswith(("http://", "https://")):
        return False

    return True


def clean_price(price):
    """
    Convert scraper price into a clean numeric value.
    """

    if price is None:
        return None

    try:
        # Already numeric
        if isinstance(price, (int, float)):
            if pd.isna(price):
                return None

            if price <= 0:
                return None

            return round(float(price), 2)

        price = str(price).strip()

        if not price:
            return None

        # Remove common currency/text
        price = (
            price.replace("₹", "")
            .replace("Rs.", "")
            .replace("Rs", "")
            .replace("INR", "")
            .replace(",", "")
            .strip()
        )

        # Keep only digits and decimal point
        cleaned = ""

        decimal_found = False

        for char in price:
            if char.isdigit():
                cleaned += char

            elif char == "." and not decimal_found:
                cleaned += char
                decimal_found = True

        if not cleaned:
            return None

        value = float(cleaned)

        if value <= 0:
            return None

        return round(value, 2)

    except Exception:
        return None


def clean_image_url(image_url):
    """
    Clean Amazon image URL.
    """

    if image_url is None:
        return None

    if pd.isna(image_url):
        return None

    image_url = str(image_url).strip()

    if not image_url:
        return None

    if image_url.lower() in ["none", "null", "nan"]:
        return None

    return image_url


def scrape_amazon(url):
    """
    Scrape Amazon price + image.
    """

    print("\n" + "=" * 80)
    print("AMAZON")
    print(url)
    print("=" * 80)

    result = {
        "success": False,
        "price": None,
        "image": None,
        "status": None,
    }

    try:
        scraper = AmazonScraper(
            url,
            headless=True
        )

        status = scraper.get_status()

        result["status"] = status

        print("Status:", status)

        # Always try to get image
        try:
            image = scraper.get_image_url()
            result["image"] = clean_image_url(image)

            if result["image"]:
                print("Image:", result["image"])

        except Exception as e:
            print("Amazon image error:", e)

        if status == "fetch_error":
            print("Amazon fetch error.")

        elif status == "not_found":
            print("Amazon product not found.")

        elif status == "out_of_stock":
            print("Amazon product is out of stock.")

        elif status == "price_unavailable":
            print("Amazon price unavailable.")

        else:
            try:
                price = scraper.get_price()
                price = clean_price(price)

                if price:
                    result["price"] = price
                    result["success"] = True

                    print("Amazon Price:", price)
                else:
                    print("Amazon price returned empty.")

            except Exception as e:
                print("Amazon price error:", e)

    except Exception as e:
        print("Amazon scraper exception:", repr(e))

    return result


def scrape_flipkart(url):
    """
    Scrape Flipkart price.
    """

    print("\n" + "=" * 80)
    print("FLIPKART")
    print(url)
    print("=" * 80)

    result = {
        "success": False,
        "price": None,
        "status": None,
    }

    try:
        scraper = FlipkartScraper(
            url,
            headless=True
        )

        status = scraper.get_status()

        result["status"] = status

        print("Status:", status)

        if status == "fetch_error":
            print("Flipkart fetch error.")

        elif status == "not_found":
            print("Flipkart product not found.")

        elif status == "out_of_stock":
            print("Flipkart product is out of stock.")

            try:
                print("Image:", scraper.get_image_url())
            except Exception:
                pass

        elif status == "price_unavailable":
            print("Flipkart price unavailable.")

            try:
                print("Image:", scraper.get_image_url())
            except Exception:
                pass

        else:
            try:
                price = scraper.get_price()
                price = clean_price(price)

                if price:
                    result["price"] = price
                    result["success"] = True

                    print("Flipkart Price:", price)
                else:
                    print("Flipkart price returned empty.")

            except Exception as e:
                print("Flipkart price error:", e)

    except Exception as e:
        print("Flipkart scraper exception:", repr(e))

    return result


def scrape_croma(url):
    """
    Scrape Croma price.
    """

    print("\n" + "=" * 80)
    print("CROMA")
    print(url)
    print("=" * 80)

    result = {
        "success": False,
        "price": None,
        "status": None,
    }

    try:
        scraper = CromaScraper(
            url,
            pincode=CROMA_PINCODE,
            headless=False
        )

        status = scraper.get_status()

        result["status"] = status

        print("Status:", status)

        if status == "fetch_error":
            print("Croma fetch error.")

        elif status == "not_found":
            print("Croma product not found.")

        elif status == "out_of_stock":
            print("Croma product is out of stock.")

        elif status == "price_unavailable":
            print("Croma price unavailable.")

        else:
            try:
                price = scraper.get_price()
                price = clean_price(price)

                if price:
                    result["price"] = price
                    result["success"] = True

                    print("Croma Price:", price)
                else:
                    print("Croma price returned empty.")

            except Exception as e:
                print("Croma price error:", e)

    except Exception as e:
        print("Croma scraper exception:", repr(e))

    return result


def scrape_reliance(url):
    """
    Scrape Reliance Digital price.
    """

    print("\n" + "=" * 80)
    print("RELIANCE DIGITAL")
    print(url)
    print("=" * 80)

    result = {
        "success": False,
        "price": None,
        "status": None,
    }

    try:
        scraper = RelianceDigitalScraper(
            url,
            headless=True
        )

        status = scraper.get_status()

        result["status"] = status

        print("Status:", status)

        if status == "fetch_error":
            print("Reliance fetch error.")

        elif status == "not_found":
            print("Reliance product not found.")

        elif status == "out_of_stock":
            print("Reliance product is out of stock.")

        elif status == "price_unavailable":
            print("Reliance price unavailable.")

        else:
            try:
                price = scraper.get_price()
                price = clean_price(price)

                if price:
                    result["price"] = price
                    result["success"] = True

                    print("Reliance Price:", price)
                else:
                    print("Reliance price returned empty.")

            except Exception as e:
                print("Reliance price error:", e)

    except Exception as e:
        print("Reliance scraper exception:", repr(e))

    return result


# ============================================================
# PROCESS ONE ROW
# ============================================================

def process_row(df, index):

    print("\n")
    print("#" * 100)
    print(f"PROCESSING ROW {index + 1}")
    print("#" * 100)

    updated = False

    # --------------------------------------------------------
    # AMAZON
    # --------------------------------------------------------

    amazon_url = df.at[index, AMAZON_LINK_COL]

    if is_valid_url(amazon_url):

        result = scrape_amazon(str(amazon_url).strip())

        # Update price ONLY if valid
        if result["success"] and result["price"] is not None:
            df.at[index, AMAZON_PRICE_COL] = format_price(result["price"])
            updated = True

            print(
                f"Amazon price updated: "
                f"₹{result['price']}"
            )

        else:
            print(
                "Amazon price not updated "
                "(keeping existing value)."
            )

        # Update image if available
        if result["image"]:
            df.at[index, AMAZON_IMAGE_COL] = str(result["image"])
            updated = True
            print("Amazon image updated.")

    else:
        print("Amazon URL not available. Skipping.")

    # --------------------------------------------------------
    # FLIPKART
    # --------------------------------------------------------

    flipkart_url = df.at[index, FLIPKART_LINK_COL]

    if is_valid_url(flipkart_url):

        result = scrape_flipkart(
            str(flipkart_url).strip()
        )

        if result["success"] and result["price"] is not None:

            df.at[index, FLIPKART_PRICE_COL] = format_price(result["price"])

            updated = True

            print(
                f"Flipkart price updated: "
                f"₹{result['price']}"
            )

        else:

            print(
                "Flipkart price not updated "
                "(keeping existing value)."
            )

    else:
        print("Flipkart URL not available. Skipping.")

    # --------------------------------------------------------
    # CROMA
    # --------------------------------------------------------

    croma_url = df.at[index, CROMA_LINK_COL]

    if is_valid_url(croma_url):

        result = scrape_croma(
            str(croma_url).strip()
        )

        if result["success"] and result["price"] is not None:

            df.at[index, CROMA_PRICE_COL] = format_price(result["price"])

            updated = True

            print(
                f"Croma price updated: "
                f"₹{result['price']}"
            )

        else:

            print(
                "Croma price not updated "
                "(keeping existing value)."
            )

    else:
        print("Croma URL not available. Skipping.")

    # --------------------------------------------------------
    # RELIANCE
    # --------------------------------------------------------

    reliance_url = df.at[index, RELIANCE_LINK_COL]

    if is_valid_url(reliance_url):

        result = scrape_reliance(
            str(reliance_url).strip()
        )

        if result["success"] and result["price"] is not None:

            df.at[index, RELIANCE_PRICE_COL] = format_price(result["price"])

            updated = True

            print(
                f"Reliance price updated: "
                f"₹{result['price']}"
            )

        else:

            print(
                "Reliance price not updated "
                "(keeping existing value)."
            )

    else:
        print("Reliance URL not available. Skipping.")

    return updated


# ============================================================
# MAIN CSV PROCESSOR
# ============================================================

def process_csv(input_file, start_row=None, end_row=None):

    input_path = Path(input_file)

    if not input_path.exists():

        raise FileNotFoundError(
            f"CSV file not found: {input_path}"
        )

    print("\n")
    print("=" * 100)
    print("PRICE UPDATE SCRIPT")
    print("=" * 100)

    print("Input CSV:", input_path)

    # --------------------------------------------------------
    # BACKUP
    # --------------------------------------------------------

    backup_path = input_path.with_name(
        input_path.stem + "_backup" + input_path.suffix
    )

    if not backup_path.exists():

        shutil.copy2(
            input_path,
            backup_path
        )

        print(
            "Backup created:",
            backup_path
        )

    else:

        print(
            "Backup already exists:",
            backup_path
        )

    # --------------------------------------------------------
    # READ CSV
    # --------------------------------------------------------

    df = pd.read_csv(
        input_path,
        dtype=str,
        keep_default_na=False
    )

    total_rows = len(df)

    print(f"Total rows in CSV: {total_rows}")
    print("Columns:", list(df.columns))

    # Calculate 0-based indices for slicing
    start_idx = max(0, (start_row - 1)) if start_row is not None else 0
    end_idx = min(total_rows, end_row) if end_row is not None else total_rows

    if start_idx >= total_rows or start_idx >= end_idx:
        print(f"Invalid row range: {start_row} to {end_row}. Exiting.")
        return

    print(f"Processing row range: Row {start_idx + 1} to Row {end_idx} (Total {end_idx - start_idx} rows)")

    # --------------------------------------------------------
    # CHECK REQUIRED COLUMNS
    # --------------------------------------------------------

    required_columns = [

        AMAZON_LINK_COL,
        AMAZON_PRICE_COL,

        FLIPKART_LINK_COL,
        FLIPKART_PRICE_COL,

        CROMA_LINK_COL,
        CROMA_PRICE_COL,

        RELIANCE_LINK_COL,
        RELIANCE_PRICE_COL,
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:

        raise ValueError(
            "\nMissing required CSV columns:\n"
            + "\n".join(
                f"  - {column}"
                for column in missing_columns
            )
        )

    # --------------------------------------------------------
    # ADD AMAZON IMAGE COLUMN
    # --------------------------------------------------------

    if AMAZON_IMAGE_COL not in df.columns:

        df[AMAZON_IMAGE_COL] = ""

        print(
            f"Added column: {AMAZON_IMAGE_COL}"
        )

    # --------------------------------------------------------
    # PROCESS RANGE OF ROWS
    # --------------------------------------------------------

    for index in range(start_idx, end_idx):

        try:

            print("\n")
            print(
                f"Progress: Row {index + 1}/{total_rows} "
                f"({((index + 1 - start_idx) / (end_idx - start_idx)) * 100:.2f}% of selected batch)"
            )

            process_row(
                df,
                index
            )

            # ------------------------------------------------
            # SAVE AFTER EVERY ROW
            # ------------------------------------------------

            df.to_csv(
                input_path,
                index=False,
                encoding="utf-8-sig"
            )

            print(
                f"CSV saved successfully "
                f"after row {index + 1}."
            )

        except KeyboardInterrupt:

            print("\n")
            print(
                "Process interrupted by user."
            )

            # Save current state
            df.to_csv(
                input_path,
                index=False,
                encoding="utf-8-sig"
            )

            print(
                "Current progress saved."
            )

            break

        except Exception as e:

            print("\n")
            print(
                f"ERROR processing row "
                f"{index + 1}:"
            )

            print(
                repr(e)
            )

            # Save even if row fails
            try:

                df.to_csv(
                    input_path,
                    index=False,
                    encoding="utf-8-sig"
                )

                print(
                    "CSV saved after error."
                )

            except Exception as save_error:

                print(
                    "Could not save CSV:",
                    repr(save_error)
                )

        # ----------------------------------------------------
        # DELAY BETWEEN ROWS
        # ----------------------------------------------------

        if index < end_idx - 1:

            delay = random.randint(
                MIN_DELAY,
                MAX_DELAY
            )

            print("\n")
            print(
                f"Waiting {delay} seconds "
                f"before next row..."
            )

            try:

                time.sleep(delay)

            except KeyboardInterrupt:

                print(
                    "\nStopped during delay."
                )

                break

    # --------------------------------------------------------
    # FINAL SAVE
    # --------------------------------------------------------

    df.to_csv(
        input_path,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n")
    print("=" * 100)
    print("PROCESS COMPLETED")
    print("=" * 100)

    print(
        "Updated CSV:",
        input_path
    )

    print(
        "Backup CSV:",
        backup_path
    )

    print(
        f"Processed Rows: {start_idx + 1} to {end_idx}"
    )

    print("=" * 100)


# ============================================================
# COMMAND LINE / EXECUTION
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Update price details from CSV."
    )

    parser.add_argument(
        "--file", default=CSV_FILE_PATH, help="Path to input CSV file"
    )
    parser.add_argument(
        "--start", type=int, default=START_ROW, help="Start row (1-indexed)"
    )
    parser.add_argument(
        "--end", type=int, default=END_ROW, help="End row (inclusive)"
    )

    args = parser.parse_args()

    process_csv(
        input_file=args.file,
        start_row=args.start,
        end_row=args.end
    )


if __name__ == "__main__":
    main()


# python price_updater_main.py --file "data/mobile_products_final_urls.csv" --start 260 --end 1991