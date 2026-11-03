from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer

ROOT=Path(__file__).parents[1]
DB=ROOT/"data"/"chroma"

_model=None
_col=None

def _load():
    global _model,_col
    if _model is None:
        _model=SentenceTransformer("all-MiniLM-L6-v2")
        client=chromadb.PersistentClient(path=str(DB))
        _col=client.get_or_create_collection("nordictech_policies")

def retrieve(query, k=2):
    _load()
    emb=_model.encode([query], normalize_embeddings=True).tolist()
    result=_col.query(query_embeddings=emb,n_results=k)
    out=[]
    for i,doc in enumerate(result["documents"][0]):
        out.append({"source":result["ids"][0][i],"text":doc})
    return out
