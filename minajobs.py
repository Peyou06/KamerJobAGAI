from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time


def start_driver():

    options = Options()
    options.add_argument("--headless")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    return driver


def scrape_minajobs():

    driver = start_driver()

    url = "https://minajobs.net"
    driver.get(url)

    time.sleep(5)

    soup = BeautifulSoup(driver.page_source, "html.parser")

    jobs = soup.find_all("h2", class_="entry-title")

    job_list = []

    for job in jobs:

        title = job.text.strip()

        job_list.append({
            "title": title
        })

    driver.quit()

    return job_list