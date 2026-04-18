import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import sys
import os
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class NeutralCommentsParser:
    def __init__(self, db_path='database.db', max_pages=30):
        self.db_path = db_path
        self.max_pages = max_pages
        self.driver = None
        self.wait = None
        self.source_id = None
        self.existing_event_urls = set()
        self.total_neutral = 0

    def setup_driver(self):
        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--headless")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 20)

    def load_existing_data(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM events WHERE source_id IN (SELECT id FROM sources WHERE name='Tripster')")
        events = cursor.fetchall()
        for event in events:
            if event[0]:
                self.existing_event_urls.add(event[0])
        conn.close()
        print(f"Загружено существующих событий Tripster: {len(self.existing_event_urls)}")

    def get_or_create_source(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM sources WHERE name='Tripster'")
        result = cursor.fetchone()
        if result:
            self.source_id = result[0]
        else:
            cursor.execute("INSERT INTO sources (name, url) VALUES (?, ?)",
                           ("Tripster", "https://experience.tripster.ru"))
            self.source_id = cursor.lastrowid
            conn.commit()
        conn.close()
        return self.source_id

    def add_event_to_db(self, title, category, text, source_id, url):
        from datetime import datetime
        parsed_at = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO events (title, category, text, source_id, url, parsed_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (title, category, text, source_id, url, parsed_at))
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return event_id

    def add_comment_to_db(self, event_id, text, author, date, rating):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO comments (event_id, text, author, date, rating)
            VALUES (?, ?, ?, ?, ?)
        """, (event_id, text, author, date, rating))
        comment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return comment_id

    def collect_event_urls_from_pages(self, base_url):
        event_urls = []
        for page_num in range(1, self.max_pages + 1):
            page_url = f"{base_url}?page={page_num}"
            print(f"\nСтраница {page_num}: {page_url}")
            self.driver.get(page_url)
            time.sleep(5)

            try:
                shadow_host = self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "experience-mf-listing")))
                shadow_root = self.driver.execute_script("return arguments[0].shadowRoot", shadow_host)
            except:
                print("   Shadow root не найден")
                continue

            cards = shadow_root.find_elements(By.CSS_SELECTOR, "div.card-list > div > div")
            print(f"   Найдено карточек на странице: {len(cards)}")

            for card in cards:
                try:
                    link_elem = card.find_element(By.CSS_SELECTOR, "div:nth-child(3) > a")
                    event_url = link_elem.get_attribute("href")
                    if event_url not in self.existing_event_urls:
                        event_urls.append(event_url)
                        print(f"   Новое событие: {event_url.split('/')[-2]}...")
                except:
                    continue
            time.sleep(random.uniform(2, 4))

        return event_urls

    def parse_event_neutral_comments(self, event_url):
        print(f"\nПарсинг события: {event_url}")

        if event_url in self.existing_event_urls:
            print("   Событие уже существует в БД")
            return 0

        try:
            self.driver.get(event_url)
            time.sleep(5)

            try:
                inner_shadow_host = self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "travelers-experience-mfe")))
                inner_shadow = self.driver.execute_script("return arguments[0].shadowRoot", inner_shadow_host)
            except:
                print("   Shadow root не найден")
                return 0

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

            try:
                reviews_link = inner_shadow.find_element(
                    By.CSS_SELECTOR,
                    "div.ration-section-v2 > div.rating-info > div > span.info-text__count.clickable"
                )
                self.driver.execute_script("arguments[0].click();", reviews_link)
                time.sleep(3)
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.ui-modal-body")))
            except:
                print("   Не удалось открыть отзывы")
                return 0

            neutral_comments = []
            previous_height = 0
            scroll_attempts = 0

            while scroll_attempts < 50:
                review_cards = inner_shadow.find_elements(By.CSS_SELECTOR, "div.modal-reviews-list > div")

                for review in review_cards:
                    try:
                        rating_element = review.find_element(By.CSS_SELECTOR, "div.review-card__underheader > div")
                        filled_stars = rating_element.find_elements(By.CSS_SELECTOR, "svg.icon.filled")
                        rating = len(filled_stars)

                        if rating == 3:
                            try:
                                review_text = review.find_element(
                                    By.CSS_SELECTOR, "div.review-card__content > div > div > div"
                                ).text.strip()
                            except:
                                review_text = None

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

                            if review_text:
                                neutral_comments.append({
                                    'text': review_text,
                                    'author': author,
                                    'date': review_date,
                                    'rating': rating
                                })
                    except:
                        continue

                try:
                    modal_scroll = self.driver.find_element(By.CSS_SELECTOR, "div.ui-modal__scroll-wrapper")
                    current_height = self.driver.execute_script("return arguments[0].scrollHeight", modal_scroll)

                    if current_height == previous_height:
                        break

                    self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", modal_scroll)
                    time.sleep(2)
                    previous_height = current_height
                    scroll_attempts += 1
                except:
                    break

            if len(neutral_comments) > 0:
                print(f"   Найдено нейтральных комментариев: {len(neutral_comments)}")

                source_id = self.get_or_create_source()
                event_id = self.add_event_to_db(title, "Экскурсия", text, source_id, event_url)
                print(f"   Событие добавлено: {title[:50]}...")

                for comment in neutral_comments:
                    self.add_comment_to_db(
                        event_id,
                        comment['text'],
                        comment['author'],
                        comment['date'],
                        comment['rating']
                    )
                result = len(neutral_comments)
            else:
                print(f"   Нейтральных комментариев  не найдено")
                result = 0

            try:
                close_btn = self.driver.find_element(By.CSS_SELECTOR, "button.ui-modal__close")
                self.driver.execute_script("arguments[0].click();", close_btn)
                time.sleep(1)
            except:
                pass

            return result

        except Exception as e:
            print(f"Ошибка: {e}")
            return 0

    def run(self):
        self.setup_driver()
        self.load_existing_data()
        self.get_or_create_source()
        base_url = "https://experience.tripster.ru/experience/Saint_Petersburg/"
        event_urls = self.collect_event_urls_from_pages(base_url)

        total_neutral = 0
        events_with_neutral = 0

        for i, event_url in enumerate(event_urls, 1):
            print(f"\n[{i}/{len(event_urls)}] Обработка события")
            neutral_count = self.parse_event_neutral_comments(event_url)
            if neutral_count > 0:
                total_neutral += neutral_count
                events_with_neutral += 1
            time.sleep(random.uniform(2, 3))

        self.driver.quit()

def main():
    parser = NeutralCommentsParser(db_path='database.db', max_pages=15)
    parser.run()


if __name__ == "__main__":
    main()