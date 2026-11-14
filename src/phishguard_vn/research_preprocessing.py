"""Research-only URL representations. Frozen E1/E2 extractors are never modified."""
from collections import Counter
import re
from urllib.parse import urlsplit, urlunsplit
import idna
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.feature_selection import SelectFromModel
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.preprocessing import StandardScaler
from phishguard_vn.brand_features import E2_FEATURES, BRAND_FEATURES
from phishguard_vn.features import CANDIDATE_FEATURES

def split_url(value):
    value = str(value)
    return urlsplit(value if "://" in value else "//" + value)

def normalize_url(value, mode="raw"):
    """Lossy research variants; raw input files and numeric features stay unchanged."""
    value = str(value)
    if mode == "raw":
        return value
    try:
        parts = split_url(value)
        host = parts.hostname or ""
        try:
            host = idna.encode(host, uts46=True).decode("ascii").lower()
        except idna.IDNAError:
            host = host.lower()
        if mode == "host_only":
            return host or value
        if not host:
            return value
        if ":" in host:  # IPv6 literal
            host = "[" + host + "]"
        port = parts.port  # invalid ports fall back to raw input, without dropping the row
        default = (parts.scheme.lower(), port) in {("http",80),("https",443)}
        netloc = host + (f":{port}" if port is not None and not default else "")
        # Remove scheme/userinfo/fragment; retain case and percent escapes of path/query.
        result = netloc + urlunsplit(("", "", parts.path, parts.query, ""))
        return result.lower() if mode == "canonical_lower" else result
    except ValueError:
        return value

class URLNormalizer(TransformerMixin, BaseEstimator):
    def __init__(self, mode="raw"):
        self.mode = mode
    def fit(self, X, y=None):
        return self
    def transform(self, X):
        return [normalize_url(x, self.mode) for x in X]

def regex_tokens(value):
    """Retain URL components and delimiter tokens instead of splitting only on whitespace."""
    value = str(value)
    pattern = r"[^\W_]+|[._~:/?#@!$&'()*+,;=%-]"
    try:
        parts = split_url(value)
        components = [("scheme",parts.scheme or "absent"),("host",parts.netloc),
                      ("path",parts.path),("query",parts.query),("fragment",parts.fragment)]
    except ValueError:
        components = [("invalid",value)]
    return [prefix + ":" + token for prefix,text in components
            for token in re.findall(pattern,text,flags=re.UNICODE)] or ["empty"]

def identity_tokens(tokens):
    return tokens

class LearnedSubwords(TransformerMixin, BaseEstimator):
    """Tokenizer vocabulary is fitted here; vectorizer vocabulary is fitted downstream."""
    def __init__(self, algorithm="bpe", vocab_size=2048):
        self.algorithm, self.vocab_size = algorithm, vocab_size
    def fit(self, X, y=None):
        from tokenizers import Tokenizer, models, trainers, pre_tokenizers, Regex
        alphabet = pre_tokenizers.ByteLevel.alphabet()
        common = dict(vocab_size=self.vocab_size, special_tokens=["[UNK]"],
                      initial_alphabet=alphabet, show_progress=False)
        if self.algorithm == "bpe":
            self.tokenizer_ = Tokenizer(models.BPE(unk_token="[UNK]"))
            trainer = trainers.BpeTrainer(**common)
        elif self.algorithm == "wordpiece":
            self.tokenizer_ = Tokenizer(models.WordPiece(unk_token="[UNK]", max_input_chars_per_word=4096))
            trainer = trainers.WordPieceTrainer(**common)
        elif self.algorithm == "unigram":
            self.tokenizer_ = Tokenizer(models.Unigram())
            trainer = trainers.UnigramTrainer(unk_token="[UNK]", **common)
        else:
            raise ValueError(self.algorithm)
        self.tokenizer_.pre_tokenizer = pre_tokenizers.Sequence([
            pre_tokenizers.Split(Regex(r"([./:?&=_-])"),behavior="isolated"),
            pre_tokenizers.ByteLevel(add_prefix_space=False,use_regex=False)])
        self.tokenizer_.train_from_iterator([str(x) for x in X], trainer=trainer)
        self.training_rows_ = len(X)
        return self
    def transform(self, X):
        return [e.tokens for e in self.tokenizer_.encode_batch([str(x) for x in X])]

def text_branch(spec, representation=None):
    representation = representation or spec["representation"]
    common = dict(min_df=2, max_features=50000, sublinear_tf=True, lowercase=False)
    if representation in {"bpe","wordpiece","unigram"}:
        return Pipeline([("subword",LearnedSubwords(representation)),
                         ("vectorizer",TfidfVectorizer(analyzer=identity_tokens, **common))])
    if representation == "regex":
        vectorizer = TfidfVectorizer(tokenizer=regex_tokens, token_pattern=None, **common)
    else:
        weighting = spec.get("weighting","tfidf")
        vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3,5), min_df=2,
            max_features=50000, lowercase=False, norm="l2", binary=weighting=="binary",
            use_idf=weighting=="tfidf", sublinear_tf=weighting in {"tfidf","log_tf"})
    return Pipeline([("normalize",URLNormalizer(spec.get("normalization","raw"))),
                     ("vectorizer",vectorizer)])

def make_linear(spec):
    representation = spec["representation"]
    char = text_branch(spec)
    if representation == "char_regex":
        features = ColumnTransformer([("char",text_branch(spec,"char"),"url"),
                                       ("regex",text_branch(spec,"regex"),"url")], sparse_threshold=1)
    elif representation in {"e1","brand","e2"}:
        columns = list(CANDIDATE_FEATURES) if representation=="e1" else (
                    list(BRAND_FEATURES) if representation=="brand" else list(E2_FEATURES))
        features = ColumnTransformer([("char",text_branch(spec,"char"),"url"),
                                      ("numeric",StandardScaler(),columns)],
                     transformer_weights={"char":1.0,"numeric":spec.get("numeric_weight",1.0)},
                     sparse_threshold=1)
    else:
        features = ColumnTransformer([("text",char,"url")], sparse_threshold=1)
    steps = [("features",features)]
    if representation == "l1":
        steps.append(("select",SelectFromModel(LogisticRegression(C=1.0, penalty="l1",
                         solver="liblinear", max_iter=2000, random_state=42), threshold=1e-5)))
    steps.append(("model",LogisticRegression(solver="liblinear", max_iter=2000, random_state=42)))
    return Pipeline(steps)

def feature_counts(model, X):
    if not isinstance(model, Pipeline):
        return {"features_before": getattr(model,"encoded_width_",20),
                "features_after": getattr(model,"encoded_width_",20)}
    transformed = model.named_steps["features"].transform(X.iloc[:2])
    before = transformed.shape[1]
    after = int(model.named_steps["select"].get_support().sum()) if "select" in model.named_steps else before
    return {"features_before":int(before),"features_after":int(after)}

def frame_from_urls(urls, spec):
    """Build only the inputs a research candidate needs; never open target websites."""
    import pandas as pd
    frame = pd.DataFrame({"url":list(urls)})
    representation = spec["representation"]
    if representation not in {"e1","brand","e2","ft_transformer"}:
        return frame
    from phishguard_vn.url_parser import parse_url
    from phishguard_vn.features import extract_features_from_parsed
    from phishguard_vn.brand_features import load_reference, extract_brand_features_from_parsed
    reference = load_reference()
    values = []
    for url in urls:
        parsed = parse_url(url)
        lexical = extract_features_from_parsed(parsed) if representation != "brand" else {}
        brand = extract_brand_features_from_parsed(parsed,reference) if representation != "e1" else {}
        values.append({**lexical,**brand})
    return pd.concat([frame,pd.DataFrame(values)],axis=1)
