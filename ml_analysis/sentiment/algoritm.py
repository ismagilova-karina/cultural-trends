import os
import time
import torch
import torch.nn as nn
import numpy as np
import pandas as pd
import logging
import random
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW
from transformers import AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score
from sklearn.utils.class_weight import compute_class_weight
from tqdm import tqdm

CONFIG = {
    "epochs": 5,
    "batch_size": 8,
    "learning_rate": 3e-5,
    "max_length": 128,
    "warmup_steps": 500,
    "weight_decay": 0.01,
    "positive_samples": 2500,
    "neutral_target": 3000
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "..", "models", "sentiment_exp")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CommentDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_length):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        text = str(self.texts[idx])
        label = self.labels[idx]

        encoding = self.tokenizer(
            text,
            truncation=True,
            padding="max_length",
            max_length=self.max_length,
            return_tensors="pt"
        )

        return {
            "input_ids": encoding["input_ids"].squeeze(),
            "attention_mask": encoding["attention_mask"].squeeze(),
            "labels": torch.tensor(label, dtype=torch.long)
        }


def augment_text(text):
    if not isinstance(text, str) or len(text.split()) < 5:
        return text
    words = text.split()
    if len(words) > 2:
        idx1, idx2 = random.sample(range(len(words)), 2)
        words[idx1], words[idx2] = words[idx2], words[idx1]

    return ' '.join(words)


def balance_dataset(df, positive_samples=2500, neutral_target=3000):
    df_negative = df[df['sentiment'] == 'negative']
    df_neutral = df[df['sentiment'] == 'neutral']
    df_positive = df[df['sentiment'] == 'positive']
    print(f"  negative: {len(df_negative)}")
    print(f"  neutral: {len(df_neutral)}")
    print(f"  positive: {len(df_positive)}")
    df_balanced = df_negative.copy()
    neutral_count = len(df_neutral)
    if neutral_count < neutral_target:
        df_balanced = pd.concat([df_balanced, df_neutral])

        needed = neutral_target - neutral_count
        augmented = []
        while len(augmented) < needed:
            for _, row in df_neutral.iterrows():
                if len(augmented) >= needed:
                    break
                augmented_row = row.copy()
                augmented_row['text_cleaned'] = augment_text(row['text_cleaned'])
                augmented.append(augmented_row)

        df_augmented = pd.DataFrame(augmented)
        df_balanced = pd.concat([df_balanced, df_augmented])
        print(f"  нейтральные с аугментацией: {neutral_count} + {len(df_augmented)} = {neutral_target}")
    else:
        df_balanced = pd.concat([df_balanced, df_neutral.sample(n=neutral_target, random_state=42)])
        print(f"  нейтральные (взято): {neutral_target} (из {neutral_count})")

    if len(df_positive) > positive_samples:
        df_positive_sampled = df_positive.sample(n=positive_samples, random_state=42)
        print(f"  positive (взято): {positive_samples} (из {len(df_positive)})")
    else:
        df_positive_sampled = df_positive
        print(f"  positive (все): {len(df_positive)}")
    df_balanced = pd.concat([df_balanced, df_positive_sampled])
    df_balanced = df_balanced.sample(frac=1, random_state=42).reset_index(drop=True)

    print(df_balanced['sentiment'].value_counts())
    print(f"Всего: {len(df_balanced)}")
    return df_balanced


class TinySentimentTrainer:
    def __init__(self):
        self.label_map = {"negative": 0, "neutral": 1, "positive": 2}
        self.device = torch.device(
            "mps" if torch.backends.mps.is_available() else "cpu"
        )
    def train(self, texts, labels):
        model_name = "blanchefort/rubert-base-cased-sentiment-rurewiews"
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            num_labels=3,
            id2label={0: "negative", 1: "neutral", 2: "positive"},
            label2id={"negative": 0, "neutral": 1, "positive": 2}
        ).to(self.device)
        X_train, X_test, y_train, y_test = train_test_split(
            texts,
            labels,
            test_size=0.2,
            random_state=42,
            stratify=labels
        )

        logger.info(f"Train: {len(X_train)} | Test: {len(X_test)}")
        logger.info(f"Распределение в train: {np.bincount(y_train)}")
        logger.info(f"Распределение в test: {np.bincount(y_test)}")

        train_ds = CommentDataset(X_train, y_train, tokenizer, CONFIG["max_length"])
        test_ds = CommentDataset(X_test, y_test, tokenizer, CONFIG["max_length"])
        train_loader = DataLoader(train_ds, batch_size=CONFIG["batch_size"], shuffle=True)
        test_loader = DataLoader(test_ds, batch_size=CONFIG["batch_size"])

        optimizer = AdamW(
            model.parameters(),
            lr=CONFIG["learning_rate"],
            weight_decay=CONFIG["weight_decay"]
        )

        total_steps = len(train_loader) * CONFIG["epochs"]
        scheduler = get_linear_schedule_with_warmup(
            optimizer,
            num_warmup_steps=CONFIG["warmup_steps"],
            num_training_steps=total_steps
        )

        class_weights = compute_class_weight(
            class_weight="balanced",
            classes=np.array([0, 1, 2]),
            y=y_train
        )

        class_weights = torch.tensor(class_weights, dtype=torch.float).to(self.device)
        loss_fn = nn.CrossEntropyLoss(weight=class_weights)
        logger.info(f"Class weights: {class_weights}")

        best_accuracy = 0
        patience = 2
        patience_counter = 0

        for epoch in range(CONFIG["epochs"]):
            start = time.time()
            model.train()
            total_loss = 0

            logger.info(f"Epoch {epoch + 1}/{CONFIG['epochs']}")
            loop = tqdm(train_loader, desc=f"Epoch {epoch + 1}")

            for step, batch in enumerate(loop):
                optimizer.zero_grad()
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)
                labels_batch = batch["labels"].to(self.device)
                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask
                )
                logits = outputs.logits
                loss = loss_fn(logits, labels_batch)

                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()

                total_loss += loss.item()
                loop.set_postfix({
                    "loss": f"{loss.item():.4f}",
                    "avg": f"{total_loss / (step + 1):.4f}"
                })

            model.eval()
            val_preds, val_true = [], []
            with torch.no_grad():
                for batch in test_loader:
                    input_ids = batch["input_ids"].to(self.device)
                    attention_mask = batch["attention_mask"].to(self.device)
                    labels_batch = batch["labels"].to(self.device)
                    outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                    pred = torch.argmax(outputs.logits, dim=1)
                    val_preds.extend(pred.cpu().numpy())
                    val_true.extend(labels_batch.cpu().numpy())
            val_accuracy = accuracy_score(val_true, val_preds)

            logger.info(
                f"Epoch {epoch + 1}"
                f"loss={total_loss / len(train_loader):.4f} | "
                f"val_acc={val_accuracy:.4f} | "
                f"time={time.time() - start:.1f}s"
            )

            if val_accuracy > best_accuracy:
                best_accuracy = val_accuracy
                patience_counter = 0
                # model.save_pretrained(MODEL_DIR)
                # tokenizer.save_pretrained(MODEL_DIR)
                logger.info(f"Сохранена лучшая модель с accuracy={best_accuracy:.4f}")
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    logger.info(f"Остановка на эпохе {epoch + 1}")
                    break
        model.eval()
        preds, true = [], []

        with torch.no_grad():
            for batch in test_loader:
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)
                labels_batch = batch["labels"].to(self.device)

                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask
                )
                pred = torch.argmax(outputs.logits, dim=1)

                preds.extend(pred.cpu().numpy())
                true.extend(labels_batch.cpu().numpy())

        accuracy = accuracy_score(true, preds)
        macro_f1 = f1_score(true, preds, average="macro")
        f1_per_class = f1_score(true, preds, average=None)

        print(f"Accuracy:  {accuracy:.3f}")
        print(f"Macro F1:  {macro_f1:.3f}")
        print(f"Negative:  F1 = {f1_per_class[0]:.3f}")
        print(f"Neutral:   F1 = {f1_per_class[1]:.3f}")
        print(f"Positive:  F1 = {f1_per_class[2]:.3f}")

        metrics = {
            "accuracy": accuracy,
            "macro_f1": macro_f1,
            "f1_negative": f1_per_class[0],
            "f1_neutral": f1_per_class[1],
            "f1_positive": f1_per_class[2]
        }
        return model, tokenizer, metrics


def main():
    df = pd.read_csv("../results/comments_with_sentiment.csv")
    df = df[df["sentiment"].notna()]
    df_balanced = balance_dataset(
        df,
        positive_samples=CONFIG["positive_samples"],
        neutral_target=CONFIG["neutral_target"]
    )
    label_map = {"negative": 0, "neutral": 1, "positive": 2}
    texts = df_balanced["text_cleaned"].fillna("").astype(str).tolist()
    labels = [label_map[x] for x in df_balanced["sentiment"].tolist()]
    trainer = TinySentimentTrainer()
    trainer.train(texts, labels)


if __name__ == "__main__":
    main()