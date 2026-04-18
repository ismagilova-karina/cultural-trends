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


class TestDataCollector:
    def __init__(self, db_path='test_database.db'):
        self.db_path = db_path
        self.driver = None
        self.wait = None
        self.source_ids = {}

    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                url TEXT
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                category TEXT,
                text TEXT,
                source_id INTEGER,
                url TEXT,
                parsed_at TEXT,
                FOREIGN KEY (source_id) REFERENCES sources(id)
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER,
                text TEXT,
                author TEXT,
                date TEXT,
                rating INTEGER,
                FOREIGN KEY (event_id) REFERENCES events(id)
            )
            """)
            conn.commit()

    def get_or_create_source(self, name, url):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM sources WHERE name = ?", (name,))
            result = cursor.fetchone()
            if result:
                return result[0]
            else:
                cursor.execute("INSERT INTO sources (name, url) VALUES (?, ?)", (name, url))
                return cursor.lastrowid

    def add_event(self, title, category, text, source_id, url):
        from datetime import datetime
        parsed_at = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO events (title, category, text, source_id, url, parsed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (title, category, text, source_id, url, parsed_at))
            return cursor.lastrowid

    def add_comment(self, event_id, text, author=None, date=None, rating=None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO comments (event_id, text, author, date, rating)
                VALUES (?, ?, ?, ?, ?)
            """, (event_id, text, author, date, rating))
            return cursor.lastrowid

    def setup_driver(self):
        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--headless")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 20)

    def get_rating_from_icon(self, img_src):
        if 'd858a72' in img_src:
            return 5
        elif '3e8d761' in img_src:
            return 4
        elif '4705662' in img_src:
            return 3
        elif '608e251' in img_src:
            return 2
        elif '8a1e024' in img_src:
            return 1
        return None

    def parse_yandex_event(self, event_url):
        print(f"Яндекс.Афиша: {event_url[:80]}...")

        try:
            self.driver.get(event_url)
            time.sleep(random.uniform(3, 5))

            try:
                title = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1"))).text
            except:
                title = "Не найден"

            try:
                category = self.driver.find_element(By.CSS_SELECTOR, ".tags__item").text
            except:
                category = "Не найден"

            try:
                description = self.driver.find_element(By.CSS_SELECTOR, ".tlWAxz").text
            except:
                description = ""

            reviews_url = None
            try:
                reviews_link = self.driver.find_element(By.CSS_SELECTOR, "a[data-test-id='titleWithMoreLink.link']")
                reviews_url = reviews_link.get_attribute("href")
            except:
                try:
                    reviews_link = self.driver.find_element(By.XPATH, "//a[contains(@href, '/reviews')]")
                    reviews_url = reviews_link.get_attribute("href")
                except:
                    pass

            if not reviews_url:
                print("   Ссылка на отзывы не найдена, пропускаем")
                return None

            if not reviews_url.startswith('http'):
                reviews_url = "https://afisha.yandex.ru" + reviews_url

            self.driver.get(reviews_url)
            time.sleep(5)

            load_more_count = 0
            while load_more_count < 20:
                try:
                    button = self.driver.find_element(By.CSS_SELECTOR,
                                                      "button[data-test-id='eventReviewsPage.eventComments.showMoreButton']")
                    if button and button.is_displayed() and button.is_enabled():
                        load_more_count += 1
                        self.driver.execute_script("arguments[0].click();", button)
                        time.sleep(2)
                    else:
                        break
                except:
                    break

            time.sleep(2)

            expand_buttons = self.driver.find_elements(By.CSS_SELECTOR, "span[data-test-id='comment.showAllButton']")
            for btn in expand_buttons:
                try:
                    self.driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.3)
                except:
                    pass

            time.sleep(2)

            comment_spans = self.driver.find_elements(By.CSS_SELECTOR, "span[data-test-id='comment']")
            if len(comment_spans) == 0:
                print("   Отзывы отсутствуют")
                return None

            source_id = self.get_or_create_source("Yandex Afisha", "https://afisha.yandex.ru")
            event_id = self.add_event(title, category, description, source_id, event_url)
            print(f"   Событие добавлено: {title[:40]}...")
            print(f"   Найдено комментариев: {len(comment_spans)}")

            count = 0
            for span in comment_spans:
                try:
                    author = None
                    try:
                        author_elem = span.find_element(By.CSS_SELECTOR, "div[data-test-id='commentInfo.author']")
                        author = author_elem.text
                    except:
                        pass

                    comment_date = None
                    try:
                        date_elem = span.find_element(By.CSS_SELECTOR, "div[data-test-id='commentInfo.publishedDate']")
                        comment_date = date_elem.text
                    except:
                        pass

                    comment_text = None
                    try:
                        text_div = span.find_element(By.CSS_SELECTOR, "div.TextWrapper-adhih3-4")
                        comment_text = text_div.text
                    except:
                        pass

                    rating = None
                    try:
                        rating_img = span.find_element(By.CSS_SELECTOR, "div.RatingWrapper-sc-1rwc86d-3 img")
                        img_src = rating_img.get_attribute("src")
                        rating = self.get_rating_from_icon(img_src)
                    except:
                        pass

                    if comment_text and comment_text.strip():
                        self.add_comment(event_id, comment_text.strip(), author, comment_date, rating)
                        count += 1

                except Exception:
                    continue

            print(f"   Сохранено комментариев: {count}")
            return event_id

        except Exception as e:
            print(f"   Ошибка: {e}")
            return None

    def parse_tripster_event(self, event_url):
        print(f"Tripster: {event_url[:80]}...")

        try:
            self.driver.get(event_url)
            time.sleep(5)

            try:
                inner_shadow_host = self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "travelers-experience-mfe"))
                )
                inner_shadow = self.driver.execute_script("return arguments[0].shadowRoot", inner_shadow_host)
            except:
                print("   Shadow root не найден")
                return None

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

            source_id = self.get_or_create_source("Tripster", "https://experience.tripster.ru")
            event_id = self.add_event(title, "Экскурсия", text, source_id, event_url)
            print(f"   Событие добавлено: {title[:40]}...")

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
                return None

            saved_count = 0
            previous_height = 0
            scroll_attempts = 0

            while scroll_attempts < 50:
                review_cards = inner_shadow.find_elements(By.CSS_SELECTOR, "div.modal-reviews-list > div")

                for review in review_cards:
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

                    rating = None
                    try:
                        rating_div = review.find_element(By.CSS_SELECTOR, "div.review-card__underheader > div")
                        filled_stars = rating_div.find_elements(By.CSS_SELECTOR, "svg.icon.filled")
                        rating = len(filled_stars)
                    except:
                        pass

                    if review_text:
                        self.add_comment(event_id, review_text, author, review_date, rating)
                        saved_count += 1

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

            print(f"   Сохранено комментариев: {saved_count}")

            try:
                close_btn = self.driver.find_element(By.CSS_SELECTOR, "button.ui-modal__close")
                self.driver.execute_script("arguments[0].click();", close_btn)
                time.sleep(1)
            except:
                pass

            return event_id

        except Exception as e:
            print(f"   Ошибка: {e}")
            return None

    def run(self):
        self.init_database()
        self.setup_driver()

        yandex_urls = [
            "https://afisha.yandex.ru/saint-petersburg/musical-play/kvartirnik-korolevy",
            "https://afisha.yandex.ru/saint-petersburg/musical-play/antidepressant-muzykalnyi-spektakl",
            "https://afisha.yandex.ru/saint-petersburg/theatre_show/s-charlzom-bukovski-za-barnoi-stoikoi",
            "https://afisha.yandex.ru/saint-petersburg/theatre_show/platonov-masterskaia"
        ]

        tripster_urls = [
            "https://experience.tripster.ru/experience/43050/",
            "https://experience.tripster.ru/experience/30149/",
            "https://experience.tripster.ru/experience/88096/"
        ]

        print("\nПарсинг Яндекс.Афиши...")
        for url in yandex_urls:
            self.parse_yandex_event(url)
            time.sleep(random.uniform(2, 4))

        print("\nПарсинг Tripster...")
        for url in tripster_urls:
            self.parse_tripster_event(url)
            time.sleep(random.uniform(2, 4))

        self.driver.quit()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM events")
            events_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM comments")
            comments_count = cursor.fetchone()[0]

            cursor.execute("""
                SELECT s.name, COUNT(DISTINCT e.id), COUNT(c.id)
                FROM sources s
                LEFT JOIN events e ON e.source_id = s.id
                LEFT JOIN comments c ON c.event_id = e.id
                GROUP BY s.id
            """)

            print(f"Всего событий: {events_count}")
            print(f"Всего комментариев: {comments_count}")

def main():
    collector = TestDataCollector(db_path='test_database.db')
    collector.run()


if __name__ == "__main__":
    main()