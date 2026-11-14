"""Small CPU research models, fixed training budgets; no holdout early stopping."""
from collections import Counter
import hashlib
from pathlib import Path
import numpy as np
import torch
from torch import nn
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.preprocessing import StandardScaler
from phishguard_vn.brand_features import E2_FEATURES
from phishguard_vn.research_preprocessing import regex_tokens

class CharCNN(nn.Module):
    def __init__(self, vocab):
        super().__init__()
        self.embedding = nn.Embedding(vocab,32,padding_idx=0)
        self.convs = nn.ModuleList([nn.Conv1d(32,32,k,padding=k//2) for k in (3,5,7)])
        self.head = nn.Linear(96,1)
    def forward(self, x):
        x = self.embedding(x).transpose(1,2)
        pooled = torch.cat([torch.relu(conv(x)).amax(2) for conv in self.convs],1)
        return self.head(pooled).squeeze(1)

class FastTextNet(nn.Module):
    def __init__(self, vocab):
        super().__init__()
        self.embedding = nn.EmbeddingBag(vocab,32,mode="mean",padding_idx=0)
        self.head = nn.Linear(32,1)
    def forward(self,x):
        return self.head(self.embedding(x)).squeeze(1)

class FTNet(nn.Module):
    """Feature-specific numerical tokens + CLS + one self-attention block."""
    def __init__(self, n_features):
        super().__init__()
        self.weight = nn.Parameter(torch.randn(n_features,32)*0.02)
        self.bias = nn.Parameter(torch.zeros(n_features,32))
        self.cls = nn.Parameter(torch.zeros(1,1,32))
        layer = nn.TransformerEncoderLayer(32,2,64,dropout=0.1,batch_first=True,
                                           activation="gelu",norm_first=True)
        self.encoder = nn.TransformerEncoder(layer,1,enable_nested_tensor=False)
        self.head = nn.Sequential(nn.LayerNorm(32),nn.Linear(32,1))
    def forward(self,x):
        tokens = x.unsqueeze(2)*self.weight + self.bias
        tokens = torch.cat([self.cls.expand(len(x),-1,-1),tokens],1)
        return self.head(self.encoder(tokens)[:,0]).squeeze(1)

class BertNet(nn.Module):
    def __init__(self, checkpoint):
        super().__init__()
        from transformers import BertModel
        self.encoder = BertModel.from_pretrained(checkpoint,local_files_only=True,
                                                  use_safetensors=True,add_pooling_layer=False)
        self.head = nn.Linear(self.encoder.config.hidden_size,1)
    def forward(self,x):
        hidden = self.encoder(input_ids=x[:,0],attention_mask=x[:,1]).last_hidden_state[:,0]
        return self.head(hidden).squeeze(1)

class NeuralURLClassifier(ClassifierMixin, BaseEstimator):
    def __init__(self, kind="char_cnn", epochs=2, learning_rate=0.001, checkpoint=""):
        self.kind, self.epochs, self.learning_rate, self.checkpoint = kind,epochs,learning_rate,checkpoint
    def _encode(self, X):
        if self.kind == "ft_transformer":
            return self.scaler_.transform(X[list(E2_FEATURES)]).astype("float32")
        urls = X["url"].astype(str).tolist()
        if self.kind == "char_cnn":
            values = np.zeros((len(urls),256),dtype="int64")
            for i,url in enumerate(urls):
                ids = [self.vocabulary_.get(c,1) for c in url[:256]]
                values[i,:len(ids)] = ids
            return values
        if self.kind == "fasttext_style":
            values = np.zeros((len(urls),512),dtype="int64")
            for i,url in enumerate(urls):
                terms = []
                for word in regex_tokens(url)[:64]:
                    terms.append(self.vocabulary_.get(word,1))
                    wrapped = "<"+word+">"
                    for n in (3,4,5):
                        for j in range(len(wrapped)-n+1):
                            h = int.from_bytes(hashlib.blake2b(wrapped[j:j+n].encode(),digest_size=4).digest(),"little")
                            terms.append(self.hash_offset_ + h%4096)
                terms = terms[:512] or [1]
                values[i,:len(terms)] = terms
            return values
        encoded = self.tokenizer_(urls,padding="max_length",truncation=True,max_length=64,
                                   return_tensors="np",return_token_type_ids=False)
        return np.stack([encoded["input_ids"],encoded["attention_mask"]],axis=1).astype("int64")
    def fit(self, X, y):
        torch.set_num_threads(2)
        torch.manual_seed(42)
        torch.use_deterministic_algorithms(True)
        y = np.asarray(y,dtype="float32")
        self.classes_ = np.array([0,1])
        self.training_rows_ = len(X)
        if self.kind == "ft_transformer":
            self.scaler_ = StandardScaler().fit(X[list(E2_FEATURES)])
            self.model_ = FTNet(len(E2_FEATURES))
            self.encoded_width_ = 20
        elif self.kind == "char_cnn":
            counts = Counter("".join(X["url"].astype(str)))
            chars = sorted(counts,key=lambda c:(-counts[c],c))[:254]
            self.vocabulary_ = {c:i+2 for i,c in enumerate(chars)}
            self.model_ = CharCNN(len(self.vocabulary_)+2)
            self.encoded_width_ = 256
        elif self.kind == "fasttext_style":
            counts = Counter(t for url in X["url"].astype(str) for t in regex_tokens(url))
            words = sorted(counts,key=lambda t:(-counts[t],t))[:4000]
            self.vocabulary_ = {t:i+2 for i,t in enumerate(words)}
            self.hash_offset_ = len(self.vocabulary_)+2
            self.model_ = FastTextNet(self.hash_offset_+4096)
            self.encoded_width_ = 512
        elif self.kind == "pretrained_url_transformer":
            from transformers import BertTokenizerFast
            self.tokenizer_ = BertTokenizerFast(vocab_file=str(Path(self.checkpoint)/"vocab.txt"),
                                                do_lower_case=True)
            self.model_ = BertNet(self.checkpoint)
            self.encoded_width_ = 64
        else:
            raise ValueError(self.kind)
        values = torch.from_numpy(self._encode(X))
        labels = torch.from_numpy(y)
        batch = 64 if self.kind=="pretrained_url_transformer" else 256
        optimizer = torch.optim.AdamW(self.model_.parameters(),lr=self.learning_rate,weight_decay=0.01)
        criterion = nn.BCEWithLogitsLoss()
        self.loss_history_ = []
        self.model_.train()
        generator = torch.Generator().manual_seed(42)
        for epoch in range(self.epochs):
            order = torch.randperm(len(values),generator=generator)
            total = 0.0
            for start in range(0,len(values),batch):
                ids = order[start:start+batch]
                optimizer.zero_grad()
                loss = criterion(self.model_(values[ids]),labels[ids])
                if not torch.isfinite(loss):
                    raise ValueError("Non-finite neural loss")
                loss.backward()
                optimizer.step()
                total += float(loss.detach())*len(ids)
            self.loss_history_.append(total/len(values))
        self.model_.eval()
        self.n_iter_ = self.epochs  # budget completed, NOT a convergence assertion
        return self
    def predict_proba(self, X):
        values = torch.from_numpy(self._encode(X))
        self.model_.eval()
        scores = []
        with torch.no_grad():
            for start in range(0,len(values),256 if self.kind!="pretrained_url_transformer" else 64):
                scores.extend(torch.sigmoid(self.model_(values[start:start+(256 if self.kind!="pretrained_url_transformer" else 64)])).numpy())
        scores = np.asarray(scores)
        return np.column_stack([1-scores,scores])
    def predict(self, X):
        return (self.predict_proba(X)[:,1]>=0.5).astype(int)
