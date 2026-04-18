import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_PATH = "../models/sentiment"

label_map = {
    0: "negative",
    1: "neutral",
    2: "positive"
}

device = torch.device(
    "mps" if torch.backends.mps.is_available() else "cpu"
)

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_PATH
).to(device)

model.eval()

def predict(text):
    encoding = tokenizer(
        text,
        truncation=True,
        padding=True,
        max_length=128,
        return_tensors="pt"
    )

    input_ids = encoding["input_ids"].to(device)
    attention_mask = encoding["attention_mask"].to(device)

    with torch.no_grad():
        outputs = model(
            input_ids=input_ids,
            attention_mask=attention_mask
        )

        logits = outputs.logits
        probs = torch.softmax(logits, dim=1)
        pred_class = torch.argmax(probs, dim=1).item()

    return {
        "text": text,
        "prediction": label_map[pred_class],
        "probabilities": {
            "negative": round(probs[0][0].item(), 3),
            "neutral": round(probs[0][1].item(), 3),
            "positive": round(probs[0][2].item(), 3),
        }
    }

if __name__ == "__main__":
    test_comments = [
        "Это было ужасно, зря потратил деньги, не впечатлило ничего в данной постановке, деньги на ветер",
        "Скучно и затянуто",
        "Ужасная игра актеров, полное разочарование, не советую никому",
        "Организация отвратительная, опоздали на час, гид ничего не знал",
        "Кошмар, а не экскурсия. Деньги на ветер, лучше бы дома остались",
        "Спектакль полный провал, скучно до зевоты, ушли в антракте",
        "Не понравилось категорически, голоса фальшивые, декорации убогие",

        "Нормально, ничего особенного не было, для разнообразия сойдет",
        "Средняя постановка, не впечатлила",
        "Обычная экскурсия, ничего выдающегося, но и плохого тоже",
        "Так себе, ожидал большего, но терпимо",
        "Неплохо, но могло быть и лучше. В целом удовлетворительно",
        "Обычный спектакль, без восторга, но время провели нормально",

        "Очень понравилось, супер концерт, актеры классные",
        "Отличная атмосфера, обязательно приду ещё",
        "Шикарная экскурсия, гид профессионал, узнал много нового",
        "Браво! Лучший спектакль в этом сезоне, актеры великолепны",
        "Восторг! Обязательно пойду еще раз и друзьям посоветую",
        "Потрясающая постановка, музыка завораживает, декорации шикарные",
        "Прекрасно провели время, спасибо организаторам, все на высшем уровне",
        "Замечательный гид, интереснейшая экскурсия, время пролетело незаметно",
        "Великолепно! Эмоции переполняют, огромное спасибо актерам",
        "Круто, огонь, просто бомба! Всем рекомендую",

        "В целом неплохо, но были минусы: долго ждали начала, гид немного торопился",
        "Местами интересно, но местами скучновато, на троечку",
        "Хорошо, но за такие деньги ожидал большего, в целом терпимо",
        "Игра актеров отличная, но сюжет слабоват, в целом неплохо"
    ]

    for comment in test_comments:
        result = predict(comment)
        print("\nTEXT:")
        print(result["text"])
        print("PREDICTION:")
        print(result["prediction"])
        print("PROBABILITIES:")
        print(result["probabilities"])