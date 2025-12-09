# train_intent_classifier.py
# ============================================================
# Train Layer-1 intent classifier:
#   - Sentence embeddings (all-mpnet-base-v2)
#   - Logistic Regression (multi-class)
#   - 'unknown' labels merged into 'chitchat'
#
# Expects: intent_dataset.csv with columns:
#   - text
#   - primary_intent
# ============================================================

import os
import warnings

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import joblib

# -------------------------
# Config
# -------------------------

DATA_PATH = "test_files/intent_dataset.csv"          # your CSV
MODEL_BUNDLE_PATH = "intent_model.joblib"

# stronger than MiniLM, still fast
EMBED_MODEL_NAME = "all-mpnet-base-v2"

# if you want to see full warnings, remove this
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)


def main():
    # 1) Load data
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")

    df = pd.read_csv(DATA_PATH)

    # Basic validation
    required_cols = {"text", "primary_intent"}
    if not required_cols.issubset(df.columns):
        raise ValueError(f"CSV must contain columns: {required_cols}")

    # Clean text
    df["text"] = df["text"].astype(str).str.strip()
    df = df[df["text"] != ""].copy()

    # ---- MERGE 'unknown' → 'chitchat' ----
    df["primary_intent"] = df["primary_intent"].astype(str).str.strip().str.lower()
    df.loc[df["primary_intent"] == "unknown", "primary_intent"] = "chitchat"

    print("Label distribution after merging 'unknown' -> 'chitchat':")
    print(df["primary_intent"].value_counts(), "\n")

    X_text = df["text"].tolist()
    y_labels = df["primary_intent"].tolist()

    # 2) Encode labels
    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(y_labels)

    print("Label mapping (class_index -> intent_label):")
    for idx, label in enumerate(label_encoder.classes_):
        print(f"  {idx}: {label}")
    print()

    # 3) Train/test split
    X_train_text, X_test_text, y_train, y_test = train_test_split(
        X_text,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y
    )

    # 4) Load embedding model
    print(f"Loading embedding model: {EMBED_MODEL_NAME}")
    embedder = SentenceTransformer(EMBED_MODEL_NAME)

    print("Encoding training texts...")
    X_train_emb = embedder.encode(X_train_text, show_progress_bar=True)
    print("Encoding test texts...")
    X_test_emb = embedder.encode(X_test_text, show_progress_bar=True)

    X_train_emb = np.asarray(X_train_emb)
    X_test_emb = np.asarray(X_test_emb)

    # 5) Train classifier
    print("\nTraining LogisticRegression classifier...")
    clf = LogisticRegression(
        C = 2.0,
        max_iter = 3000,
        solver = 'lbfgs',

        
        n_jobs=-1,
        # multi_class left to default (multinomial in new sklearn)
    )
    clf.fit(X_train_emb, y_train)

    # 6) Evaluate
    y_pred = clf.predict(X_test_emb)

    print("\nClassification report (on hold-out test set):")
    print(
        classification_report(
            y_test,
            y_pred,
            target_names=label_encoder.classes_
        )
    )

    print("Confusion matrix:")
    print(confusion_matrix(y_test, y_pred))

    # 7) Save model bundle
    bundle = {
        "embed_model_name": EMBED_MODEL_NAME,
        "label_classes": label_encoder.classes_,
        "classifier": clf,
    }

    joblib.dump(bundle, MODEL_BUNDLE_PATH)
    print(f"\n✅ Saved model bundle to: {MODEL_BUNDLE_PATH}")


if __name__ == "__main__":
    main()
