import pytest
import numpy as np
import intent_classifier as ic


# --------------------------------------------------------
# Fixtures: Fake model bundle + fake embedder + fake classifier
# --------------------------------------------------------

class FakeEmbedder:
    """Small dummy embedding model."""
    def encode(self, texts):
        # Always return deterministic vector
        return [[0.1, 0.2, 0.3]]


class FakeClassifier:
    """Fake sklearn classifier."""
    def __init__(self, probs):
        self._probs = np.asarray([probs])  # 2D for predict_proba

    def predict_proba(self, X):
        # Ignore X, always return stored probs
        return self._probs


@pytest.fixture
def fake_model_bundle():
    return {
        "embed_model_name": "fake-embed-model",
        "label_classes": ["course_info", "instructor_lookup", "chitchat"],
        "classifier": FakeClassifier([0.1, 0.7, 0.2]),
    }


# --------------------------------------------------------
# Test: __init__
# --------------------------------------------------------

def test_intent_classifier_init(monkeypatch, fake_model_bundle):
    """Ensure the model loads joblib + SentenceTransformer correctly."""

    # Fake joblib loader
    monkeypatch.setattr(ic.joblib, "load", lambda path: fake_model_bundle)

    # Fake SentenceTransformer
    monkeypatch.setattr(ic, "SentenceTransformer", lambda name: FakeEmbedder())

    clf = ic.IntentClassifier("fake.joblib")

    assert clf.label_classes == ["course_info", "instructor_lookup", "chitchat"]
    assert isinstance(clf.embedder, FakeEmbedder)
    assert isinstance(clf.clf, FakeClassifier)


# --------------------------------------------------------
# Test: classify_intent() – empty text
# --------------------------------------------------------

def test_classify_intent_empty(monkeypatch, fake_model_bundle):
    """Empty input should return chitchat with zero confidence."""

    monkeypatch.setattr(ic.joblib, "load", lambda path: fake_model_bundle)
    monkeypatch.setattr(ic, "SentenceTransformer", lambda name: FakeEmbedder())

    clf = ic.IntentClassifier("dummy")

    out = clf.classify_intent("")
    assert out["primary_intent"] == "chitchat"
    assert out["confidence"] == 0.0
    assert all(v == 0.0 for v in out["probs"].values())
    assert out["top_k"] == []


# --------------------------------------------------------
# Test: classify_intent() – normal classification
# --------------------------------------------------------

def test_classify_intent_normal(monkeypatch, fake_model_bundle):
    """Check main classification logic and top_k ordering."""

    monkeypatch.setattr(ic.joblib, "load", lambda path: fake_model_bundle)
    monkeypatch.setattr(ic, "SentenceTransformer", lambda name: FakeEmbedder())

    clf = ic.IntentClassifier("dummy")

    out = clf.classify_intent("When is CS101?")

    # classifier has probs [0.1, 0.7, 0.2]
    assert out["primary_intent"] == "instructor_lookup"
    assert pytest.approx(out["confidence"], rel=1e-6) == 0.7

    # probs dictionary matches fake classifier order
    assert out["probs"]["course_info"] == 0.1
    assert out["probs"]["instructor_lookup"] == 0.7
    assert out["probs"]["chitchat"] == 0.2

    # top_k should be sorted descending
    assert out["top_k"][0][0] == "instructor_lookup"
    assert out["top_k"][1][0] == "chitchat"
    assert out["top_k"][2][0] == "course_info"


# --------------------------------------------------------
# Test: classify_intent() – custom top_k
# --------------------------------------------------------

def test_classify_intent_top_k(monkeypatch, fake_model_bundle):
    """Ensure top_k parameter works as expected."""

    monkeypatch.setattr(ic.joblib, "load", lambda path: fake_model_bundle)
    monkeypatch.setattr(ic, "SentenceTransformer", lambda name: FakeEmbedder())

    clf = ic.IntentClassifier("dummy")

    out = clf.classify_intent("hello", top_k=2)

    assert len(out["top_k"]) == 2
    assert out["top_k"][0][0] == "instructor_lookup"


# --------------------------------------------------------
# Test: get_intent_classifier singleton
# --------------------------------------------------------

def test_get_intent_classifier_singleton(monkeypatch, fake_model_bundle):
    """Singleton should only create classifier once."""

    monkeypatch.setattr(ic.joblib, "load", lambda path: fake_model_bundle)
    monkeypatch.setattr(ic, "SentenceTransformer", lambda name: FakeEmbedder())

    # Reset module-level singleton
    ic._classifier_singleton = None

    clf1 = ic.get_intent_classifier()
    clf2 = ic.get_intent_classifier()

    assert clf1 is clf2      # same instance
    assert isinstance(clf1, ic.IntentClassifier)
