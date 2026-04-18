import re
import pandas as pd
from datetime import datetime, timedelta


# даты
def parse_relative_date(date_str, parsed_at):
    if not isinstance(date_str, str):
        return None
    date_str_lower = date_str.lower().strip()
    if isinstance(parsed_at, str):
        parsed_at = datetime.fromisoformat(parsed_at.replace('Z', '+00:00'))
    if date_str_lower == 'сегодня':
        return parsed_at.date()
    if date_str_lower == 'вчера':
        return (parsed_at - timedelta(days=1)).date()

    hour_pattern = r'(\d+)?\s*(час|часа|часов)\s+назад'
    match = re.search(hour_pattern, date_str_lower)

    if match:
        if match.group(1):
            hours = int(match.group(1))
        else:
            hours = 1
        result_date = parsed_at - timedelta(hours=hours)
        return result_date.date()

    day_pattern = r'(\d+)\s+(день|дня|дней)\s+назад'
    match = re.search(day_pattern, date_str_lower)

    if match:
        days = int(match.group(1))
        result_date = parsed_at - timedelta(days=days)
        return result_date.date()

    return None


def parse_absolute_date(date_str):
    if not isinstance(date_str, str):
        return None

    months = {
        'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
        'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
        'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
    }

    pattern_with_year = r'(\d+)\s+([а-я]+)\s+(\d{4})'
    match = re.search(pattern_with_year, date_str.lower())

    if match:
        day = int(match.group(1))
        month_name = match.group(2)
        year = int(match.group(3))

        if month_name in months:
            month = months[month_name]
            try:
                return datetime(year, month, day).date()
            except ValueError:
                return None

    pattern_without_year = r'(\d+)\s+([а-я]+)'
    match = re.search(pattern_without_year, date_str.lower())

    if match:
        day = int(match.group(1))
        month_name = match.group(2)

        if month_name in months:
            month = months[month_name]
            current_year = datetime.now().year
            try:
                return datetime(current_year, month, day).date()
            except ValueError:
                return None

    for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y']:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue

    return None


def normalize_dates(comments_df, events_df):
    event_parsed_at = {}
    for _, row in events_df.iterrows():
        parsed_at_str = row['parsed_at']
        if isinstance(parsed_at_str, str):
            event_parsed_at[row['id']] = datetime.fromisoformat(parsed_at_str)

    normalized_dates = []
    failed_count = 0

    for idx, row in comments_df.iterrows():
        original_date = row['date']
        event_id = row['event_id']

        if pd.isna(original_date) or original_date == '':
            normalized_dates.append(None)
            continue

        date_str = str(original_date).strip()

        if event_id in event_parsed_at:
            rel_date = parse_relative_date(date_str, event_parsed_at[event_id])
            if rel_date:
                normalized_dates.append(rel_date)
                continue

        abs_date = parse_absolute_date(date_str)
        if abs_date:
            normalized_dates.append(abs_date)
        else:
            print(f"Не удалось распарсить дату: '{date_str}' (комментарий id={row['id']})")
            normalized_dates.append(None)
            failed_count += 1

    if failed_count > 0:
        print(f"\nВсего не удалось распарсить {failed_count} дат")

    comments_df['normalized_date'] = normalized_dates
    return comments_df


# текст
def clean_text(text):
    if not isinstance(text, str):
        return ""
    text = text.lower()
    emoji_pattern = re.compile("["
                               u"\U0001F600-\U0001F64F"
                               u"\U0001F300-\U0001F5FF"
                               u"\U0001F680-\U0001F6FF"
                               u"\U0001F700-\U0001F77F"
                               u"\U0001F780-\U0001F7FF"
                               u"\U0001F800-\U0001F8FF"
                               u"\U0001F900-\U0001F9FF"
                               u"\U0001FA00-\U0001FA6F"
                               u"\U0001FA70-\U0001FAFF"
                               u"\U00002702-\U000027B0"
                               u"\U000024C2-\U0001F251"
                               "]+", flags=re.UNICODE)
    text = emoji_pattern.sub(r'', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\d+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def remove_stopwords(text, custom_stopwords=None):
    russian_stopwords = {
        'и', 'в', 'во', 'по', 'что', 'на', 'я', 'с', 'со', 'как', 'а', 'но',
        'он', 'она', 'оно', 'они', 'его', 'её', 'их', 'ты', 'вы', 'вас', 'нам',
        'нас', 'вам', 'ваш', 'твой', 'мой', 'себя', 'этот', 'эта', 'это', 'эти',
        'тот', 'та', 'те', 'который', 'которая', 'которые', 'так', 'вот', 'было',
        'была', 'были', 'будет', 'будем', 'будете', 'будут', 'есть', 'быть',
        'только', 'ещё', 'уже', 'даже', 'ведь', 'вдруг', 'ли', 'раз', 'уж',
        'ну', 'же', 'либо', 'кое', 'то', 'где', 'тут', 'там', 'здесь', 'куда',
        'откуда', 'зачем', 'почему', 'потому', 'поэтому', 'тогда', 'тоже',
        'также', 'чтобы', 'будто', 'словно', 'как-то', 'всё', 'все', 'всю',
        'всей', 'всем', 'всех', 'вся', 'всего', 'всегда', 'никогда', 'иногда',
        'некоторый', 'некоторое', 'некоторые', 'несколько', 'много', 'мало',
        'очень', 'слишком', 'совсем', 'почти', 'около', 'возле', 'около',
        'хотя', 'этого', 'причем', 'есть'
    }

    if custom_stopwords:
        russian_stopwords.update(custom_stopwords)
    words = text.split()
    filtered_words = [word for word in words if word not in russian_stopwords]
    return ' '.join(filtered_words)


def basic_preprocessing(text, remove_stops=True, custom_stopwords=None):
    text = clean_text(text)
    if remove_stops:
        text = remove_stopwords(text, custom_stopwords)
    return text


def remove_duplicate_comments(df,
                              text_column='text',
                              group_columns=['event_id', 'text', 'author', 'rating']):
    df = df.copy()
    original_len = len(df)
    df = df[df[text_column].notna()]
    df = df[df[text_column].astype(str).str.strip() != '']
    after_empty = len(df)
    df = df.drop_duplicates(subset=group_columns, keep='first')
    after_dedup = len(df)
    print(f"Удалено дубликатов (одинаковые: событие+текст+автор+рейтинг): {after_empty - after_dedup}")
    return df


def remove_duplicate_events(events_df, comments_df=None, group_columns=None):
    events_df = events_df.copy()
    original_len = len(events_df)

    if group_columns is None:
        base_columns = ['title', 'text', 'url']
        group_columns = base_columns
    print(f"Поиск дубликатов по колонкам: {group_columns}")

    if len(group_columns) == 0:
        return events_df, comments_df

    events_df['is_duplicate'] = events_df.duplicated(subset=group_columns, keep='first')
    original_events = events_df[~events_df['is_duplicate']].copy()

    if comments_df is not None and len(original_events) < len(events_df):
        duplicate_events = events_df[events_df['is_duplicate']].copy()
        print(f"Найдено дубликатов событий: {len(duplicate_events)}")
        mapping = {}
        for _, dup in duplicate_events.iterrows():
            condition = True
            for col in group_columns:
                condition = condition & (original_events[col] == dup[col])

            matching_originals = original_events[condition]
            if len(matching_originals) > 0:
                original_id = matching_originals.iloc[0]['id']
                mapping[dup['id']] = original_id
            else:
                mapping[dup['id']] = dup['id']
        comments_df = comments_df.copy()
        comments_df['event_id'] = comments_df['event_id'].replace(mapping)
    events_df = original_events.drop(columns=['is_duplicate'])
    dup_count = original_len - len(events_df)
    if dup_count > 0:
        print(f"Удалено дубликатов событий: {dup_count}")
    else:
        print("Дубликатов событий не найдено")
    print(f"Осталось событий: {len(events_df)}")
    return events_df, comments_df


def process_comments(df, text_column='text', remove_stops=True, custom_stopwords=None):
    df = df.copy()
    df['text_cleaned'] = df[text_column].apply(
        lambda x: basic_preprocessing(x, remove_stops, custom_stopwords)
    )
    df = df[df['text_cleaned'].str.len() > 0].copy()
    df['text_length'] = df['text_cleaned'].apply(lambda x: len(x.split()))
    print(f"Осталось комментариев после очистки: {len(df)}")
    return df


def run_preprocessing(comments_df, events_df):
    print("\n1. Удаление дубликатов событий")
    events_df, comments_df = remove_duplicate_events(events_df, comments_df)
    print("\n2. Нормализация дат")
    comments_df = normalize_dates(comments_df, events_df)
    print("\n3. Удаление комментариев без рейтинга")
    before = len(comments_df)
    comments_df = comments_df[comments_df['rating'].notna()]
    print(f"   Удалено без рейтинга: {before - len(comments_df)}")
    print("\n4. Удаление дубликатов комментариев")
    comments_df = remove_duplicate_comments(comments_df)
    print("\n5. Обработка текста комментариев")
    comments_df = process_comments(comments_df, text_column='text', remove_stops=True)
    print(f"{len(events_df)} событий, {len(comments_df)} комментариев")
    return comments_df, events_df


if __name__ == "__main__":
    import sqlite3
    import os
    os.makedirs('./result', exist_ok=True)
    conn = sqlite3.connect('../data_collection/database.db')
    events_df = pd.read_sql_query("SELECT id, title, text, url, parsed_at FROM events", conn)
    comments_df = pd.read_sql_query("SELECT id, event_id, text, author, date, rating FROM comments", conn)
    conn.close()
    print(f"Загружено событий: {len(events_df)}")
    print(f"Загружено комментариев: {len(comments_df)}")
    comments_processed, events_processed = run_preprocessing(comments_df, events_df)
    comments_processed.to_csv('./result/comments_processed.csv', index=False)
    events_processed.to_csv('./result/events_processed.csv', index=False)
    print("\nПредобработка завершена")