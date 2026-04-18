from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import sys
import os
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import create_tables, add_event, add_comment, add_source, get_events, get_comments

MAX_COMMENTS = 70
MIN_COMMENTS = 40
MAX_PAGES = 3

create_tables()

SOURCE_NAME = "Tripster"
BASE_URL = "https://experience.tripster.ru/experience/Saint_Petersburg/"

def get_existing_source_id():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM sources WHERE name = ?", (SOURCE_NAME,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


existing_source_id = get_existing_source_id()
if existing_source_id:
    source_id = existing_source_id
    print(f"Источник '{SOURCE_NAME}' уже существует (ID: {source_id})")
else:
    source_id = add_source(SOURCE_NAME, BASE_URL)
    print(f"Источник '{SOURCE_NAME}' создан (ID: {source_id})")

options = Options()
options.add_argument("--start-maximized")
options.add_argument("--headless")
options.add_argument("--disable-blink-features=AutomationControlled")
driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 30)

all_event_data = []

for page_num in range(1, MAX_PAGES + 1):
    page_url = f"{BASE_URL}?page={page_num}"
    print(f"\nСтраница {page_num}: {page_url}")
    driver.get(page_url)
    time.sleep(5)

    try:
        shadow_host = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "experience-mf-listing")))
        shadow_root = driver.execute_script("return arguments[0].shadowRoot", shadow_host)
    except:
        print("Shadow root на странице не найден")
        continue

    cards = shadow_root.find_elements(By.CSS_SELECTOR, "div.card-list > div > div")
    for card in cards:
        try:
            link_elem = card.find_element(By.CSS_SELECTOR, "div:nth-child(3) > a")
            event_url = link_elem.get_attribute("href")

            reviews_elem = card.find_element(By.CSS_SELECTOR, "div.general > div > a.reviews")
            total_comments = int(reviews_elem.text.strip().split()[0])

            if total_comments < MIN_COMMENTS:
                continue

            all_event_data.append((event_url, total_comments))
        except:
            continue

print(f"Карточек для парсинга после всех страниц: {len(all_event_data)}")

for i, (event_url, total_comments) in enumerate(all_event_data, start=1):
    print(f"\nПарсим карточку {i}/{len(all_event_data)}: {event_url}")
    existing_events = get_events()
    event_exists = False
    for event in existing_events:
        if event['url'] == event_url:
            event_exists = True
            break

    if event_exists:
        print("   Событие уже есть в БД, пропускаем")
        continue
    driver.get(event_url)
    time.sleep(5)

    try:
        inner_shadow_host = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "travelers-experience-mfe")))
        inner_shadow = driver.execute_script("return arguments[0].shadowRoot", inner_shadow_host)
    except:
        print("Shadow root на странице карточки не найден")
        continue

    try:
        title_elem = inner_shadow.find_element(
            By.CSS_SELECTOR,
            "div.wrap > div > div.main-content > header > div.experience-header__content > div.experience-header__title-wrapper > h1"
        )
        title = title_elem.text.strip()
    except:
        title = "No title"

    try:
        text_elem = inner_shadow.find_element(
            By.CSS_SELECTOR,
            "div.wrap > div > div.main-content > header > div.experience-header__content > div.experience-header__guide-section > div.experience-header__quote-wrapper > div > div > p"
        )
        text = text_elem.text.strip()
    except:
        text = None

    category = "Экскурсия"

    event_id = add_event(title, text=text, source_id=source_id, category=category, url=event_url)
    print(f"   Событие добавлено: {title[:50]}...")

    try:
        reviews_link = inner_shadow.find_element(
            By.CSS_SELECTOR,
            "div.ration-section-v2 > div.rating-info > div > span.info-text__count.clickable"
        )
        driver.execute_script("arguments[0].click();", reviews_link)
        time.sleep(3)

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.ui-modal-body")))
    except:
        print("   Не удалось открыть отзывы")
        continue

    saved_count = 0
    previous_height = 0
    scroll_attempts = 0
    ratings_count = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    existing_comments = get_comments(event_id)
    existing_texts = {c['text'] for c in existing_comments} if existing_comments else set()

    while scroll_attempts < 50:
        review_cards = inner_shadow.find_elements(By.CSS_SELECTOR, "div.modal-reviews-list > div")

        for review in review_cards:
            try:
                review_text = review.find_element(
                    By.CSS_SELECTOR, "div.review-card__content > div > div > div"
                ).text.strip()
            except:
                review_text = None

            if not review_text or review_text in existing_texts:
                continue

            try:
                author = review.find_element(
                    By.CSS_SELECTOR,
                    "div.review-card__header > div.review-card__user-info > div.review-card__user-name"
                ).text.strip()
            except:
                author = None

            try:
                review_date = review.find_element(
                    By.CSS_SELECTOR, "div.review-card__underheader > span"
                ).text.strip()
            except:
                review_date = None

            rating = None
            try:
                rating_div = review.find_element(By.CSS_SELECTOR, "div.review-card__underheader > div")
                filled_stars = rating_div.find_elements(By.CSS_SELECTOR, "svg.icon.filled")
                rating = len(filled_stars)
                if rating and rating in ratings_count:
                    ratings_count[rating] = ratings_count.get(rating, 0) + 1
            except:
                pass

            add_comment(event_id, text=review_text, author=author, date=review_date, rating=rating)
            saved_count += 1
            existing_texts.add(review_text)

        try:
            modal_scroll = driver.find_element(By.CSS_SELECTOR, "div.ui-modal__scroll-wrapper")
            current_height = driver.execute_script("return arguments[0].scrollHeight", modal_scroll)

            if current_height == previous_height:
                break

            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", modal_scroll)
            time.sleep(2)
            previous_height = current_height
            scroll_attempts += 1
        except:
            break

    print(f"   Сохранено комментариев: {saved_count}")

    try:
        close_btn = driver.find_element(By.CSS_SELECTOR, "button.ui-modal__close")
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass

driver.quit()