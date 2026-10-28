"""Conversation-level Persian social-engineering risk models (CPU).

Model families (selected by template-grouped CV on the training split only):
  * tfidf : TF-IDF char 2-5 + word 1-2 grams -> Logistic Regression
  * emb   : multilingual sentence embedding (paraphrase-multilingual-MiniLM-L12-v2,
            supports Persian) of each turn + whole conversation -> Logistic Regression
  * combo : mean of tfidf and emb probabilities
"""
import os
import pickle

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, make_pipeline

from .text import normalize

EMB_MODEL = os.environ.get("TC_EMB_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
_ENC = None
_CACHE = {}


def conv_text(turns):
    return normalize(" || ".join(turns))


def encoder():
    global _ENC
    if _ENC is None:
        from sentence_transformers import SentenceTransformer
        _ENC = SentenceTransformer(EMB_MODEL, device="cpu")
    return _ENC


def embed(texts):
    todo = [t for t in dict.fromkeys(texts) if t not in _CACHE]
    if todo:
        vecs = encoder().encode(todo, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
        _CACHE.update(zip(todo, vecs))
    return np.stack([_CACHE[t] for t in texts])


def emb_features(turns):
    """[conversation embedding, max-pooled turn embeddings, last-turn embedding]."""
    t = [normalize(x) for x in turns]
    E = embed(t)
    return np.concatenate([embed([" || ".join(t)])[0], E.max(axis=0), E[-1]])


class TfidfModel:
    kind = "tfidf"

    def __init__(self, C=4.0, seed=0):
        self.pipe = make_pipeline(
            FeatureUnion([
                ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)),
                ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
            ]),
            LogisticRegression(C=C, class_weight="balanced", max_iter=3000, random_state=seed))

    def fit(self, ds):
        self.pipe.fit([conv_text(d["turns"]) for d in ds], [d["label"] for d in ds])
        return self

    def score(self, turns):
        return float(self.pipe.predict_proba([conv_text(turns)])[0, 1])

    def score_texts(self, texts):
        return self.pipe.predict_proba([normalize(t) for t in texts])[:, 1]


class EmbModel:
    kind = "emb"

    def __init__(self, C=1.0, seed=0):
        self.clf = LogisticRegression(C=C, class_weight="balanced", max_iter=3000, random_state=seed)

    def fit(self, ds):
        self.clf.fit(np.stack([emb_features(d["turns"]) for d in ds]), [d["label"] for d in ds])
        return self

    def score(self, turns):
        return float(self.clf.predict_proba(emb_features(turns)[None])[0, 1])

    def score_texts(self, texts):
        return np.array([self.score([t]) for t in texts])


class ComboModel:
    kind = "combo"

    def __init__(self, C_t=4.0, C_e=1.0, seed=0):
        self.t, self.e = TfidfModel(C_t, seed), EmbModel(C_e, seed)

    def fit(self, ds):
        self.t.fit(ds), self.e.fit(ds)
        return self

    def score(self, turns):
        return 0.5 * (self.t.score(turns) + self.e.score(turns))

    def score_texts(self, texts):
        return 0.5 * (self.t.score_texts(texts) + self.e.score_texts(texts))


CANDIDATES = {
    "tfidf_C1": lambda: TfidfModel(1.0), "tfidf_C4": lambda: TfidfModel(4.0),
    "emb_C0.3": lambda: EmbModel(0.3), "emb_C1": lambda: EmbModel(1.0), "emb_C4": lambda: EmbModel(4.0),
    "combo": lambda: ComboModel(4.0, 1.0),
}


def select_model(train, n_splits=5):
    """Template-grouped CV on training templates only. Returns best name and all scores."""
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold
    groups = [d["template_id"] for d in train]
    res = {}
    for name, mk in CANDIDATES.items():
        aucs = []
        for tr, va in GroupKFold(n_splits=n_splits).split(train, groups=groups):
            ys = [train[i]["label"] for i in va]
            if len(set(ys)) < 2:
                continue
            m = mk().fit([train[i] for i in tr])
            aucs.append(roc_auc_score(ys, [m.score(train[i]["turns"]) for i in va]))
        res[name] = {"cv_auc_mean": round(float(np.mean(aucs)), 4), "cv_auc_min": round(float(np.min(aucs)), 4), "folds": len(aucs)}
    best = max(res, key=lambda k: res[k]["cv_auc_mean"])
    return best, res


def save(model, path):
    with open(path, "wb") as f:
        pickle.dump(model, f)


def load(path):
    with open(path, "rb") as f:
        return pickle.load(f)


BLACKLIST = ["فوری", "اورژانس", "بدون کد", "کد نفرستید", "کد رو نفرستید", "پیامک نفرستید",
             "استثنا", "مدیریت", "واحد فنی", "همکار", "بیمارستان"]


def keyword_hit(turns):
    t = conv_text(turns)
    return any(normalize(k) in t for k in BLACKLIST)
