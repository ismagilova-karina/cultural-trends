import pandas as pd

def label_comments_by_rating(csv_path='../../../preprocessing/result/comments_processed.csv'):
    """
    1-2 звезды - negative
    3 звезды - neutral
    4-5 звезд - positive
    """
    df = pd.read_csv(csv_path)
    print(f"Загружено комментариев: {len(df)}")
    def get_sentiment(rating):
        if pd.isna(rating):
            return None
        elif rating in (1, 2):
            return 'negative'
        elif rating == 3:
            return 'neutral'
        elif rating in (4, 5):
            return 'positive'
        else:
            return None

    df['sentiment'] = df['rating'].apply(get_sentiment)

    total = len(df)
    positive = len(df[df['sentiment'] == 'positive'])
    neutral = len(df[df['sentiment'] == 'neutral'])
    negative = len(df[df['sentiment'] == 'negative'])
    unlabeled = len(df[df['sentiment'].isna()])

    print(f"Всего комментариев: {total}")
    print(f"  positive (4-5 звезд): {positive}")
    print(f"  neutral (3 звезды): {neutral}")
    print(f"  negative (1-2 звезды): {negative}")
    print(f"  не размечено (нет рейтинга): {unlabeled}")

    return df


def main():
    df_labeled = label_comments_by_rating()
    df_labeled.to_csv('../../results/comments_with_sentiment.csv', index=False, encoding='utf-8-sig')

if __name__ == "__main__":
    main()