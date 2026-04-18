import sqlite3
import pandas as pd
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from preprocessing.preprocessing import normalize_dates, process_comments

def save_topics_info(topic_model, db_path='test_database.db'):
    conn = sqlite3.connect(db_path)
    topic_info = topic_model.get_topic_info()

    if 'Representation' in topic_info.columns:
        topic_info['Representation'] = topic_info['Representation'].apply(
            lambda x: ', '.join(x) if isinstance(x, list) else str(x)
        )

    topic_info = topic_info.rename(columns={
        'Topic': 'topic_id',
        'Count': 'comment_count',
        'Name': 'topic_name',
        'Representation': 'keywords'
    })

    topic_info.to_sql('topics_info', conn, if_exists='replace', index=False)
    conn.close()
    print(f"Сохранено {len(topic_info)} описаний тем в таблицу topics_info")


def load_models():
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    from bertopic import BERTopic

    sentiment_path = "../ml_analysis/models/sentiment"
    topic_path = "../ml_analysis/models/topics"

    tokenizer = AutoTokenizer.from_pretrained(sentiment_path, local_files_only=True)
    sentiment_model = AutoModelForSequenceClassification.from_pretrained(sentiment_path, local_files_only=True)

    topic_model = BERTopic.load(topic_path)

    return tokenizer, sentiment_model, topic_model


def predict_sentiment(texts, tokenizer, model):
    import torch
    inputs = tokenizer(
        texts,
        truncation=True,
        padding=True,
        max_length=128,
        return_tensors="pt"
    )

    with torch.no_grad():
        outputs = model(**inputs)

    preds = torch.argmax(outputs.logits, dim=1)
    return [["negative", "neutral", "positive"][p] for p in preds]

def predict_topics(texts, topic_model):
    topics, _ = topic_model.transform(texts)
    return topics

def get_topic_description(topic_model, topic_id):
    if topic_id == -1:
        return "Не классифицировано"
    topic_info = topic_model.get_topic_info()
    topic_row = topic_info[topic_info['Topic'] == topic_id]
    if len(topic_row) > 0:
        return topic_row['Name'].values[0]
    return f"Тема {topic_id}"

def export_results(filtered_comments, filtered_events, topic_model):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("analysis_results", exist_ok=True)

    export_cols = ['id', 'text', 'sentiment', 'topic']
    available_cols = [col for col in export_cols if col in filtered_comments.columns]
    results_df = filtered_comments[available_cols].copy()
    results_df.to_csv(f"analysis_results/results_{timestamp}.csv", index=False, encoding='utf-8-sig')
    print(f"   Результаты сохранены в analysis_results/results_{timestamp}.csv")

    topic_summary = []
    for topic_id in filtered_comments['topic'].unique():
        if topic_id == -1:
            continue
        topic_data = filtered_comments[filtered_comments['topic'] == topic_id]
        sentiment_dist = topic_data['sentiment'].value_counts(normalize=True)
        topic_summary.append({
            'topic_id': topic_id,
            'topic_name': get_topic_description(topic_model, topic_id),
            'comment_count': len(topic_data),
            'positive_pct': sentiment_dist.get('positive', 0) * 100,
            'neutral_pct': sentiment_dist.get('neutral', 0) * 100,
            'negative_pct': sentiment_dist.get('negative', 0) * 100
        })

    topic_summary_df = pd.DataFrame(topic_summary)
    topic_summary_df.to_csv(f"analysis_results/topic_summary_{timestamp}.csv", index=False, encoding='utf-8-sig')
    print(f"   Сводка по темам сохранена в analysis_results/topic_summary_{timestamp}.csv")


def print_analysis_summary(filtered_comments, filtered_events, topic_model):
    total = len(filtered_comments)
    sentiment_counts = filtered_comments['sentiment'].value_counts()

    print("\n1. Распределение тональности")
    print(f"   Комментариев: {total}")
    print(
        f"   Положительные: {sentiment_counts.get('positive', 0)} ({sentiment_counts.get('positive', 0) / total * 100:.1f}%)")
    print(
        f"   Нейтральные:    {sentiment_counts.get('neutral', 0)} ({sentiment_counts.get('neutral', 0) / total * 100:.1f}%)")
    print(
        f"   Отрицательные:  {sentiment_counts.get('negative', 0)} ({sentiment_counts.get('negative', 0) / total * 100:.1f}%)")

    print("\n2. Топ 10 тем по количеству комментариев")
    topic_counts = filtered_comments['topic'].value_counts().head(10)
    for topic, count in topic_counts.items():
        if topic != -1:
            topic_name = get_topic_description(topic_model, topic)
            percent = count / total * 100
            topic_data = filtered_comments[filtered_comments['topic'] == topic]
            positive_pct = (topic_data['sentiment'] == 'positive').mean() * 100
            print(f"   Тема {topic}: {topic_name[:45]}")
            print(f"      Комментариев: {count} ({percent:.1f}%), Позитив: {positive_pct:.1f}%")

    print("\n3. Топ 5 популярных событий")
    event_comments = filtered_comments.groupby('event_id').size().sort_values(ascending=False)
    for event_id, count in event_comments.head(5).items():
        event_title = filtered_events[filtered_events['id'] == event_id]['title'].values[0]
        if len(event_title) > 60:
            event_title = event_title[:250] + "..."
        print(f"   {event_title}: {count} комментариев")

    topics_with_positive = []
    for topic in filtered_comments['topic'].unique():
        if topic != -1:
            topic_data = filtered_comments[filtered_comments['topic'] == topic]
            positive_pct = (topic_data['sentiment'] == 'positive').mean()
            if len(topic_data) > 20:
                topics_with_positive.append((topic, positive_pct, len(topic_data)))

    if topics_with_positive:
        best_topic = max(topics_with_positive, key=lambda x: x[1])
        topic_name = get_topic_description(topic_model, best_topic[0])
        print(f"   Самая позитивная тема: {topic_name[:250]}")
        print(f"      Позитив: {best_topic[1] * 100:.1f}% ({best_topic[2]} комментариев)")

    topics_with_negative = []
    for topic in filtered_comments['topic'].unique():
        if topic != -1:
            topic_data = filtered_comments[filtered_comments['topic'] == topic]
            negative_pct = (topic_data['sentiment'] == 'negative').mean()
            if len(topic_data) > 20:
                topics_with_negative.append((topic, negative_pct, len(topic_data)))

    if topics_with_negative:
        worst_topic = max(topics_with_negative, key=lambda x: x[1])
        topic_name = get_topic_description(topic_model, worst_topic[0])
        print(f"\n   Самая негативная тема: {topic_name[:250]}")
        print(f"      Негатив: {worst_topic[1] * 100:.1f}% ({worst_topic[2]} комментариев)")

    print("\n5. Примеры классификации")
    print("\n   Положительные комментарии:")
    positive_samples = filtered_comments[filtered_comments['sentiment'] == 'positive'].head(3)
    for _, row in positive_samples.iterrows():
        text_preview = row['text'][:250] + "..." if len(row['text']) > 250 else row['text']
        topic_name = get_topic_description(topic_model, row['topic'])
        print(f"\n      Текст: \"{text_preview}\"")
        print(f"      Тональность: {row['sentiment'].upper()}, Тема: {topic_name[:250]}")

    print("\n   Отрицательные комментарии:")
    negative_samples = filtered_comments[filtered_comments['sentiment'] == 'negative'].head(3)
    if len(negative_samples) > 0:
        for _, row in negative_samples.iterrows():
            text_preview = row['text'][:250] + "..." if len(row['text']) > 250 else row['text']
            topic_name = get_topic_description(topic_model, row['topic'])
            print(f"\n      Текст: \"{text_preview}\"")
            print(f"      Тональность: {row['sentiment'].upper()}, Тема: {topic_name[:250]}")
    else:
        print("      Отрицательные комментарии отсутствуют")

    print("\n   Нейтральные комментарии:")
    neutral_samples = filtered_comments[filtered_comments['sentiment'] == 'neutral'].head(3)
    if len(neutral_samples) > 0:
        for _, row in neutral_samples.iterrows():
            text_preview = row['text'][:250] + "..." if len(row['text']) > 120 else row['text']
            topic_name = get_topic_description(topic_model, row['topic'])
            print(f"\n      Текст: \"{text_preview}\"")
            print(f"      Тональность: {row['sentiment'].upper()}, Тема: {topic_name[:50]}")
    else:
        print("      Нейтральные комментарии отсутствуют")

def add_missing_columns(db_path='test_database.db'):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(comments)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'sentiment' not in columns:
        cursor.execute("ALTER TABLE comments ADD COLUMN sentiment TEXT")
    if 'topic' not in columns:
        cursor.execute("ALTER TABLE comments ADD COLUMN topic INTEGER")
    if 'confidence' not in columns:
        cursor.execute("ALTER TABLE comments ADD COLUMN confidence REAL")
    conn.commit()
    conn.close()


def main():
    db_path = 'test_database.db'
    print("\nПодготовка БД")
    add_missing_columns(db_path)

    print("\n1 Загрузка данных из БД")
    conn = sqlite3.connect(db_path)
    events_df = pd.read_sql_query("SELECT id, title, parsed_at FROM events", conn)
    comments_df = pd.read_sql_query("SELECT id, event_id, text, author, date, rating FROM comments", conn)
    conn.close()
    comments_df = normalize_dates(comments_df, events_df)
    filtered_events = events_df.copy()
    filtered_comments = comments_df.copy()
    print(f"{len(filtered_events)} событий, {len(filtered_comments)} комментариев")

    print("\n2 Предобработка текста")
    filtered_comments = process_comments(filtered_comments, text_column='text', remove_stops=True)

    print("\n3 Загрузка обученных моделей")
    tokenizer, sentiment_model, topic_model = load_models()
    print("       Модель sentiment загружена")
    print("       Модель topic modeling загружена")

    texts = filtered_comments['text'].fillna('').astype(str).tolist()
    sentiments = predict_sentiment(texts, tokenizer, sentiment_model)
    filtered_comments['sentiment'] = sentiments

    print("\n4 Тематическое моделирование")
    texts_cleaned = filtered_comments['text_cleaned'].fillna('').astype(str).tolist()
    topics = predict_topics(texts_cleaned, topic_model)
    filtered_comments['topic'] = topics
    unique_topics = len(set(topics)) - (1 if -1 in topics else 0)
    print(f"       Выделено {unique_topics} тема")

    print("\n5 Сохранение результатов")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for _, row in filtered_comments.iterrows():
        cursor.execute("""
            UPDATE comments 
            SET sentiment = ?, topic = ?
            WHERE id = ?
        """, (row['sentiment'], int(row['topic']), row['id']))

    conn.commit()
    conn.close()
    print(f"       Обновлено {len(filtered_comments)} комментариев")

    print("\n6 Сохранение информации о темах")
    save_topics_info(topic_model, db_path)

    export_results(filtered_comments, filtered_events, topic_model)
    print_analysis_summary(filtered_comments, filtered_events, topic_model)


if __name__ == "__main__":
    main()