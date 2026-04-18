import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import create_tables, add_source, add_event, add_comment, get_events


class YandexAfishaParser:
    def __init__(self):
        self.source_id = None
        self.driver = None
        self.wait = None

        self.selection_urls = [
            # Театр
            # "https://afisha.yandex.ru/saint-petersburg/selections/theatre-opera-russia?source=rubric&city=saint-petersburg&tag=theatre",
            # "https://afisha.yandex.ru/saint-petersburg/selections/theatre-promenade-theatre?source=rubric&city=saint-petersburg&tag=theatre",
            # "https://afisha.yandex.ru/saint-petersburg/selections/theatre-ballet-russia?source=rubric&city=saint-petersburg&tag=theatre",
            "https://afisha.yandex.ru/saint-petersburg/selections/theatre-theatre-comedy-russia?source=rubric&city=saint-petersburg&tag=theatre",
            "https://afisha.yandex.ru/saint-petersburg/selections/drama?source=rubric&city=saint-petersburg&tag=theatre",
            "https://afisha.yandex.ru/saint-petersburg/selections/classical-play?source=rubric&city=saint-petersburg&tag=theatre",

            # Искусство
            # "https://afisha.yandex.ru/saint-petersburg/selections/modern-art?source=rubric&city=saint-petersburg&tag=art",
            # "https://afisha.yandex.ru/saint-petersburg/selections/art-history?source=rubric&city=saint-petersburg&tag=art",
            "https://afisha.yandex.ru/saint-petersburg/selections/photography-art?source=rubric&city=saint-petersburg&tag=art"
        ]

        create_tables()
        self.source_id = self.get_or_create_source()

    def get_or_create_source(self):
        import sqlite3
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM sources WHERE name = 'Yandex Afisha' LIMIT 1")
        result = cursor.fetchone()
        conn.close()

        if result:
            source_id = result[0]
            print(f"Источник 'Yandex Afisha' уже существует (ID: {source_id})")
            return source_id
        else:
            source_id = add_source("Yandex Afisha", "https://afisha.yandex.ru")
            print(f"Источник 'Yandex Afisha' создан (ID: {source_id})")
            return source_id

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

    def get_event_urls_from_selection(self, selection_url):
        print(f"Парсинг подборки: {selection_url}")
        self.driver.get(selection_url)
        time.sleep(5)

        load_more_count = 0
        while load_more_count < 5:
            try:
                load_more_button = self.driver.find_element(By.CSS_SELECTOR, 'button[data-test-id="eventsList.more"]')
                load_more_count += 1
                self.driver.execute_script("arguments[0].click();", load_more_button)
                time.sleep(random.uniform(2, 4))
            except:
                break

        links = self.driver.find_elements(By.CSS_SELECTOR, 'a[data-test-id="eventCard.link"]')
        print(f"Найдено ссылок: {len(links)}")

        event_urls = set()
        for link in links:
            href = link.get_attribute("href")
            if href:
                href = href.split("#")[0]
                event_urls.add(href)
        return event_urls

    def find_reviews_link(self):
        try:
            reviews_link = self.driver.find_element(By.CSS_SELECTOR, "a[data-test-id='titleWithMoreLink.link']")
            return reviews_link
        except:
            pass
        try:
            reviews_link = self.driver.find_element(By.XPATH, "//a[contains(@href, '/reviews')]")
            return reviews_link
        except:
            pass
        try:
            reviews_link = self.driver.find_element(By.XPATH, "//h2[contains(text(), 'Отзывы')]/parent::a")
            return reviews_link
        except:
            pass
        return None

    def click_show_more_button(self):
        button_selectors = [
            "button[data-test-id='eventReviewsPage.eventComments.showMoreButton']",
            "button[data-test-id='eventCommentsListMoreButton']",
        ]

        for selector in button_selectors:
            try:
                button = self.driver.find_element(By.CSS_SELECTOR, selector)
                if button and button.is_displayed() and button.is_enabled():
                    return button
            except:
                continue
        return None

    def event_exists_in_db(self, event_url):
        existing_events = get_events()
        for event in existing_events:
            if event['url'] == event_url:
                return True
        return False

    def parse_event(self, event_url):
        print(f"\nПарсинг события: {event_url}")

        if self.event_exists_in_db(event_url):
            print("Событие уже существует в БД, пропускаем")
            return None

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
                description = "Не найден"

            reviews_link = self.find_reviews_link()
            if not reviews_link:
                print("Ссылка на отзывы не найдена, событие пропускается")
                return None

            reviews_url = reviews_link.get_attribute("href")
            if not reviews_url.startswith('http'):
                reviews_url = "https://afisha.yandex.ru" + reviews_url

            self.driver.get(reviews_url)
            time.sleep(5)

            load_more_count = 0
            while load_more_count < 30:
                button = self.click_show_more_button()
                if button:
                    load_more_count += 1
                    print(f"'Показать ещё' #{load_more_count}")
                    self.driver.execute_script("arguments[0].click();", button)
                    time.sleep(2)
                else:
                    break

            time.sleep(3)

            expand_buttons = self.driver.find_elements(By.CSS_SELECTOR, "span[data-test-id='comment.showAllButton']")
            for btn in expand_buttons:
                if btn.is_displayed() and btn.is_enabled():
                    try:
                        self.driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.3)
                    except:
                        pass

            time.sleep(2)

            comment_spans = self.driver.find_elements(By.CSS_SELECTOR, "span[data-test-id='comment']")

            if len(comment_spans) == 0:
                print("Отзывы отсутствуют, событие не добавляется")
                return None

            event_id = add_event(
                title=title,
                category=category,
                text=description,
                source_id=self.source_id,
                url=event_url
            )
            print(f"Событие добавлено: {title[:50]}...")
            print(f"Найдено комментариев: {len(comment_spans)}")

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
                        add_comment(event_id=event_id, text=comment_text.strip(), author=author, date=comment_date,
                                    rating=rating)
                        count += 1

                except Exception:
                    continue
            return event_id

        except Exception as e:
            print(f"Ошибка при парсинге события: {e}")
            return None

    def run(self, max_events=250):

        self.setup_driver()
        all_event_urls = set()

        try:
            for selection_url in self.selection_urls:
                try:
                    event_urls = self.get_event_urls_from_selection(selection_url)
                    all_event_urls.update(event_urls)
                    print(f"Всего собрано уникальных событий: {len(all_event_urls)}")
                    time.sleep(random.uniform(3, 5))
                except Exception as e:
                    print(f"Ошибка при парсинге подборки {selection_url}: {e}")
                    continue

            events_to_parse = list(all_event_urls)
            if max_events:
                events_to_parse = events_to_parse[:max_events]
                print(f"\nОграничение парсинга: первые {max_events} событий")

            parsed_count = 0
            for i, event_url in enumerate(events_to_parse, 1):
                print(f"\n[{i}/{len(events_to_parse)}] Обработка события")
                event_id = self.parse_event(event_url)
                if event_id:
                    parsed_count += 1
                time.sleep(random.uniform(2, 4))

        finally:
            self.driver.quit()
        print(f"Обработано событий: {parsed_count}")


def main():
    parser = YandexAfishaParser()
    parser.run(max_events=250)


if __name__ == "__main__":
    main()