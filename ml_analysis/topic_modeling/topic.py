import os
import sys
import pandas as pd
import logging
from bertopic import BERTopic
from sklearn.feature_extraction.text import CountVectorizer
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOPIC_MODEL_DIR = os.path.join(BASE_DIR, "..", "models", "topics_exp")
RESULTS_DIR = os.path.join(BASE_DIR, "..", "results")

def prepare_texts_for_topic_modeling(df, text_column="text_cleaned", min_length=3):
    texts = df[text_column].fillna("").astype(str).tolist()
    texts = [t for t in texts if len(t.split()) >= min_length]
    return texts

def train_topic_model(texts, min_topic_size=5):
    vectorizer = CountVectorizer(
        min_df=2,
        max_df=0.95,
        ngram_range=(1, 2)
    )

    topic_model = BERTopic(
        language="russian",
        vectorizer_model=vectorizer,
        min_topic_size=min_topic_size,
        n_gram_range=(1, 2),
        calculate_probabilities=True,
        verbose=True
    )

    topics, probabilities = topic_model.fit_transform(texts)

    topic_info = topic_model.get_topic_info()
    logger.info(f"\nНайдено топиков: {len(topic_info[topic_info['Topic'] != -1])}")
    return topic_model, topics, probabilities

def print_topics_summary(topic_model, num_topics=15):
    topic_info = topic_model.get_topic_info()
    topic_info = topic_info[topic_info['Topic'] != -1].head(num_topics)

    for _, row in topic_info.iterrows():
        topic_id = row['Topic']
        count = row['Count']
        name = row['Name']
        topic_words = topic_model.get_topic(topic_id)
        if topic_words:
            top_words = ", ".join([word for word, _ in topic_words[:8]])
        else:
            top_words = "не определено"
        print(f"\nТопик {topic_id} (кол-во: {count})")
        print(f"Название: {name}")
        print(f"Ключевые слова: {top_words}")

def analyze_topics_with_sentiment(topic_model, topics, df, text_column="text_cleaned", original_text_column="text"):
    valid_indices = [i for i, t in enumerate(topics) if t != -1]
    valid_topics = [topics[i] for i in valid_indices]

    original_texts = []
    for idx in valid_indices:
        text = df.iloc[idx][original_text_column]
        if pd.isna(text):
            text = ""
        else:
            text = str(text)
        original_texts.append(text)

    topic_df = pd.DataFrame({
        "text": original_texts,
        "topic": valid_topics
    })

    if "sentiment" in df.columns:
        topic_df["sentiment"] = df.iloc[valid_indices]["sentiment"].values

    topic_sentiment = {}
    for topic_id in sorted(set(valid_topics)):
        topic_data = topic_df[topic_df["topic"] == topic_id]

        if "sentiment" in topic_df.columns:
            sentiment_dist = topic_data["sentiment"].value_counts(normalize=True)
            topic_sentiment[topic_id] = sentiment_dist.to_dict()

            print(f"\nТопик {topic_id} (всего: {len(topic_data)} комментариев):")
            for sent, perc in sentiment_dist.items():
                print(f"{sent}: {perc:.1%}")

            print(f"\nПримеры:")
            shown = 0
            for text in topic_data["text"]:
                if shown >= 3:
                    break
                if text and len(text.strip()) > 0:
                    preview = text[:150] + "..." if len(text) > 150 else text
                    print(f"      - {preview}")
                    shown += 1
            if shown == 0:
                print("      (нет примеров с текстом)")
    return topic_df, topic_sentiment

def save_topic_model(topic_model, texts, topics, probabilities):
    os.makedirs(TOPIC_MODEL_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    topic_model.save(TOPIC_MODEL_DIR, serialization="safetensors")
    results_df = pd.DataFrame({
        "text": texts,
        "topic": topics,
        "topic_probability": probabilities.max(axis=1) if probabilities is not None else np.zeros(len(texts))
    })
    results_df.to_csv(os.path.join(RESULTS_DIR, "comments_with_topics.csv"), index=False)
    topic_info = topic_model.get_topic_info()
    topic_info.to_csv(os.path.join(RESULTS_DIR, "topics_info.csv"), index=False)

def main():
    csv_path = os.path.join(RESULTS_DIR, "comments_with_sentiment.csv")
    df = pd.read_csv(csv_path)

    if "sentiment" in df.columns:
        logger.info(f"\nРаспределение тональности:")
        for sent, count in df["sentiment"].value_counts().items():
            logger.info(f"   {sent}: {count} ({count / len(df) * 100:.1f}%)")

    texts = prepare_texts_for_topic_modeling(df, min_length=3)
    topic_model, topics, probabilities = train_topic_model(texts, min_topic_size=50)
    print_topics_summary(topic_model)
    analyze_topics_with_sentiment(topic_model, topics, df, original_text_column="text")
    # save_topic_model(topic_model, texts, topics, probabilities)
    return topic_model, topics, probabilities

if __name__ == "__main__":
    main()