import os
import re
import boto3
import requests
import asyncio
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# Load AWS credentials from .env file
load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET_NAME = "nvidia-data-bucket"

# NVIDIA Financial Reports URL
URL = "https://investor.nvidia.com/financial-info/financial-reports/default.aspx"

# Define years and quarters to scrape
YEARS_TO_SCRAPE = ["2022", "2023", "2024", "2025"]
QUARTERS = ["First Quarter", "Second Quarter", "Third Quarter", "Fourth Quarter"]

# Initialize Boto3 S3 Client
s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

async def get_pdf_links(page, year, quarter):
    """Scrapes 10-K and 10-Q PDFs for a given year and quarter."""
    print(f"🔍 Scraping {quarter} {year}...")

    # **Select the year in the dropdown**
    dropdown = page.locator("select")
    await dropdown.wait_for(state="visible", timeout=15000)
    await dropdown.select_option(year)
    await page.wait_for_load_state("networkidle")  # Ensure reload completes

    # **Expand the quarter section**
    quarter_section = page.locator(f"text={quarter}")
    plus_button = quarter_section.locator("xpath=..").locator("button")

    if await plus_button.is_visible():
        await plus_button.click()
        await page.wait_for_load_state("networkidle")

    # **Find `10-K` and `10-Q` Links**
    pdf_links = []
    for report_type in ["10-K", "10-Q"]:
        report_locator = page.locator(f"text={report_type}")

        if await report_locator.is_visible():
            print(f"📄 Clicking {report_type} for {quarter} {year}...")

            # **Use JavaScript to force-click**
            await page.evaluate('(element) => element.click()', await report_locator.element_handle())
            await page.wait_for_load_state("networkidle")

            # **Extract PDF URL**
            pdf_url = await page.evaluate('''() => {
                let link = document.querySelector("a[href$='.pdf']");
                return link ? link.href : null;
            }''')

            if pdf_url:
                pdf_links.append(pdf_url)
                print(f"✅ Found {report_type} PDF: {pdf_url}")

    return pdf_links

async def download_and_upload_pdfs(pdf_links, year, quarter):
    """Downloads PDFs and uploads them to AWS S3 under `financial-reports/{YEAR}/`."""
    for pdf_url in pdf_links:
        pdf_name = pdf_url.split("/")[-1]

        print(f"📥 Downloading {pdf_name} for {year} - {quarter}...")
        response = requests.get(pdf_url, stream=True)
        if response.status_code == 200:
            s3_key = f"financial-reports/{year}/{quarter.replace(' ', '_')}/{pdf_name}"
            s3_client.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_key,
                Body=response.content,
                ContentType="application/pdf"
            )
            print(f"✅ Uploaded {pdf_name} to S3 in {s3_key}")
        else:
            print(f"❌ Failed to download {pdf_url}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Debug mode to see interactions
        page = await browser.new_page()
        
        print("🚀 Opening webpage...")
        await page.goto(URL, timeout=90000)
        await page.wait_for_load_state("networkidle")

        for year in YEARS_TO_SCRAPE:
            for quarter in QUARTERS:
                pdf_links = await get_pdf_links(page, year, quarter)
                if pdf_links:
                    await download_and_upload_pdfs(pdf_links, year, quarter)
                else:
                    print(f"❌ No PDFs found for {quarter} {year}.")

        await browser.close()

# Run the scraper
asyncio.run(main())
