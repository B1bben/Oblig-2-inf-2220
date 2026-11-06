from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer

ROOT=Path(__file__).parents[1]
KB=ROOT/"knowledge_base"
DB=ROOT/"data"/"chroma"

def main():
    model=SentenceTransformer("all-MiniLM-L6-v2")
    client=chromadb.PersistentClient(path=str(DB))
    try: client.delete_collection("nordictech_policies")
    except Exception: pass
    col=client.get_or_create_collection("nordictech_policies")
    docs=[]; ids=[]
    for p in sorted(KB.glob("*.txt")):
        text=p.read_text(encoding="utf-8")
        docs.append(text); ids.append(p.stem)
    emb=model.encode(docs, normalize_embeddings=True).tolist()
    col.add(ids=ids, documents=docs, embeddings=emb,
            metadatas=[{"source":i} for i in ids])
    print(f"Indexed {len(docs)} policy documents.")

if __name__=="__main__":
    main()
