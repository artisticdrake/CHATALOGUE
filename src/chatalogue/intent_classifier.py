# intent_classifier.py
# ============================================================
# Runtime Layer-1 intent classifier
#  - Loads intent_model.joblib (trained with train_intent_classifier.py)
#  - Uses sentence-transformers to embed text
#  - Exposes: classify_intent(text) -> dict
# ============================================================

from typing import Dict, List, Any
import numpy as np
import joblib
from sentence_transformers import SentenceTransformer

MODEL_BUNDLE_PATH = "models/intent/intent_model.joblib"


class IntentClassifier:
    def __init__(self, model_path: str = MODEL_BUNDLE_PATH):
        bundle = joblib.load(model_path)
        self.embed_model_name: str = bundle["embed_model_name"]
        self.label_classes: List[str] = list(bundle["label_classes"])
        self.clf = bundle["classifier"]

        # load the same embedding model used during training
        self.embedder = SentenceTransformer(self.embed_model_name)

    def classify_intent(self, text: str, top_k: int = 3) -> Dict[str, Any]:
        """
        Classify a single user query into an intent.

        Returns:
            {
              "primary_intent": str,
              "confidence": float,
              "probs": {label: prob, ...},
              "top_k": [(label, prob), ...]
            }
        """
        text = (text or "").strip()
        if not text:
            return {
                "primary_intent": "chitchat",
                "confidence": 0.0,
                "probs": {lbl: 0.0 for lbl in self.label_classes},
                "top_k": [],
            }

        emb = self.embedder.encode([text])
        emb = np.asarray(emb)

        # LogisticRegression has predict_proba
        probs = self.clf.predict_proba(emb)[0]  # shape (num_classes,)
        best_idx = int(np.argmax(probs))
        best_label = self.label_classes[best_idx]
        best_conf = float(probs[best_idx])

        probs_dict = {
            label: float(p)
            for label, p in zip(self.label_classes, probs)
        }

        top_k = min(top_k, len(self.label_classes))
        sorted_indices = np.argsort(probs)[::-1][:top_k]
        top_k_list = [
            (self.label_classes[int(i)], float(probs[int(i)]))
            for i in sorted_indices
        ]

        return {
            "primary_intent": best_label,
            "confidence": best_conf,
            "probs": probs_dict,
            "top_k": top_k_list,
        }


# optional singleton for easy import
_classifier_singleton: IntentClassifier | None = None


def get_intent_classifier() -> IntentClassifier:
    global _classifier_singleton
    if _classifier_singleton is None:
        _classifier_singleton = IntentClassifier(MODEL_BUNDLE_PATH)
    return _classifier_singleton


# quick CLI test
if __name__ == "__main__":
    clf = get_intent_classifier()
    while True:
        msg = input("\nYou: ")
        if msg.lower().strip() in {"quit", "exit", "bye"}:
            break
        result = clf.classify_intent(msg)
        print("→ primary_intent:", result["primary_intent"])
        print("  confidence   :", f"{result['confidence']:.3f}")
        print("  top_k        :", result["top_k"])
