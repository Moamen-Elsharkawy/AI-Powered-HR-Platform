"""
HR CV RAG System — A simple FastAPI app to ingest CVs, extract info with LLMs, and enable search/Q&A.
===================================
Run:  pip install -r requirements.txt
      uvicorn main:app --reload
Docs: http://localhost:8000/docs
"""

import os, uuid, json, re, tempfile
from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import faiss
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
from pypdf import PdfReader
import uvicorn

# ─── Config ───────────────────────────────────────────────────────────────────

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
EMBED_MODEL        = "text-embedding-3-small"
CHAT_MODEL         = "gpt-4o-mini"
DIM                = 1536
CHUNK_SIZE         = 800

if not OPENROUTER_API_KEY:
    raise RuntimeError(
        "\n\n❌  OPENROUTER_API_KEY is not set!\n"
        "    Open the .env file and paste your key:\n"
        "    OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxx\n"
        "    Get a free key at: https://openrouter.ai\n"
    )

client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

# ─── In-Memory Storage ────────────────────────────────────────────────────────

candidates_db: dict = {}
chunks_db: list     = []
index               = faiss.IndexFlatIP(DIM)
chunk_id_map: list  = []

# ─── Helpers ──────────────────────────────────────────────────────────────────

def normalize(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + 1e-12)

def embed(text: str) -> np.ndarray:
    resp = client.embeddings.create(model=EMBED_MODEL, input=[text[:6000]])
    return normalize(np.array(resp.data[0].embedding, dtype=np.float32))

def chunk_text(text: str) -> List[str]:
    return [text[i:i+CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE) if text[i:i+CHUNK_SIZE].strip()]

def extract_text(file_path: str, ext: str) -> str:
    if ext == "pdf":
        reader = PdfReader(file_path)
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    return open(file_path, encoding="utf-8", errors="replace").read()

def parse_cv_with_llm(text: str) -> dict:
    prompt = f"""Extract candidate info from this CV. Return ONLY valid JSON with these exact keys:
{{"name":null,"email":null,"phone":null,"location":null,"years_experience":null,"seniority":null,"role":null,"skills":[]}}
CV text:
{text[:4000]}"""
    try:
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        data.setdefault("skills", [])
        return data
    except Exception:
        email = re.search(r"[\w._%+-]+@[\w.-]+\.[a-zA-Z]{2,}", text)
        years = re.search(r"(\d+)\s+years?", text, re.I)
        return {
            "name": None, "email": email.group() if email else None,
            "phone": None, "location": None,
            "years_experience": int(years.group(1)) if years else None,
            "seniority": None, "role": None, "skills": [],
        }

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="HR CV RAG System", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "HR CV RAG API — visit /docs"}

# ─── Ingest ───────────────────────────────────────────────────────────────────

async def _process_one(file: UploadFile) -> dict:
    """Process a single CV file and return result dict."""
    ext = (file.filename or "file.txt").rsplit(".", 1)[-1].lower()
    if ext not in ("pdf", "txt"):
        return {"filename": file.filename, "error": "Only PDF or TXT files supported"}

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        return {"filename": file.filename, "error": "File too large (max 10MB)"}

    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        raw_text = extract_text(tmp_path, ext)
    except Exception as e:
        return {"filename": file.filename, "error": f"Text extraction failed: {e}"}
    finally:
        os.remove(tmp_path)

    if len(raw_text.strip()) < 50:
        return {"filename": file.filename, "error": "Could not extract enough text"}

    metadata     = parse_cv_with_llm(raw_text)
    candidate_id = str(uuid.uuid4())
    candidates_db[candidate_id] = {
        "id": candidate_id,
        "created_at": datetime.utcnow().isoformat(),
        **metadata,
    }

    global index, chunk_id_map
    chunks = chunk_text(raw_text)
    for chunk in chunks:
        chunk_id = str(uuid.uuid4())
        vec = embed(chunk).reshape(1, -1)
        faiss.normalize_L2(vec)
        index.add(vec)
        chunk_id_map.append(chunk_id)
        chunks_db.append({"id": chunk_id, "candidate_id": candidate_id, "text": chunk})

    return {
        "filename": file.filename,
        "candidate_id": candidate_id,
        "chunks": len(chunks),
        "metadata": candidates_db[candidate_id],
    }


@app.post("/ingest", tags=["Ingestion"])
async def ingest(files: List[UploadFile] = File(...)):
    if len(files) > 20:
        raise HTTPException(400, "Max 20 files at once")

    results, errors = [], []
    for file in files:
        result = await _process_one(file)
        if "error" in result:
            errors.append(result)
        else:
            results.append(result)

    return {
        "message": f"{len(results)} CV(s) ingested successfully" + (f", {len(errors)} failed" if errors else ""),
        "succeeded": results,
        "failed": errors,
        "total": len(files),
    }

# ─── Search ───────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    seniority: Optional[str] = None
    location: Optional[str] = None
    role: Optional[str] = None

@app.post("/search", tags=["Search"])
def search(req: SearchRequest):
    if index.ntotal == 0:
        return {"results": [], "total": 0, "query": req.query}

    q_vec = embed(req.query).reshape(1, -1)
    faiss.normalize_L2(q_vec)
    scores, indices = index.search(q_vec, min(100, index.ntotal))

    best, matched = {}, {}
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(chunk_id_map): continue
        chunk = next((c for c in chunks_db if c["id"] == chunk_id_map[idx]), None)
        if not chunk: continue
        cid = chunk["candidate_id"]
        if cid not in best or score > best[cid]:
            best[cid]    = float(score)
            matched[cid] = chunk["text"][:200]

    results = []
    for cid, score in sorted(best.items(), key=lambda x: -x[1]):
        c = candidates_db.get(cid, {})
        if req.seniority and (c.get("seniority") or "").lower() != req.seniority.lower(): continue
        if req.location  and req.location.lower()  not in (c.get("location") or "").lower(): continue
        if req.role      and req.role.lower()       not in (c.get("role") or "").lower(): continue
        results.append({"candidate": c, "score": round(score, 4), "matched_text": matched.get(cid, "")})
        if len(results) >= req.top_k: break

    return {"results": results, "total": len(results), "query": req.query}

# ─── Q&A ──────────────────────────────────────────────────────────────────────

class QARequest(BaseModel):
    question: str
    top_k: int = 5

@app.post("/qa", tags=["Q&A"])
def qa(req: QARequest):
    if index.ntotal == 0:
        return {"answer": "No CVs have been uploaded yet.", "citations": []}

    q_vec = embed(req.question).reshape(1, -1)
    faiss.normalize_L2(q_vec)
    scores, indices = index.search(q_vec, min(req.top_k * 3, index.ntotal))

    top_chunks = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(chunk_id_map): continue
        chunk = next((c for c in chunks_db if c["id"] == chunk_id_map[idx]), None)
        if chunk:
            candidate = candidates_db.get(chunk["candidate_id"], {})
            top_chunks.append({
                "text": chunk["text"],
                "candidate_name": candidate.get("name", "Unknown"),
                "candidate_id": chunk["candidate_id"],
            })

    if not top_chunks:
        return {"answer": "No relevant information found.", "citations": []}

    context = "\n\n".join(f"[{c['candidate_name']}]: {c['text']}" for c in top_chunks[:req.top_k])
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": "Answer ONLY based on the provided CV data. If info is not found, say so."},
            {"role": "user",   "content": f"Data:\n{context}\n\nQuestion: {req.question[:500]}"},
        ],
        temperature=0,
    )
    answer    = resp.choices[0].message.content or "No answer generated."
    citations = [{"candidate_name": c["candidate_name"], "candidate_id": c["candidate_id"],
                  "excerpt": c["text"][:200]} for c in top_chunks[:req.top_k]]
    return {"answer": answer, "citations": citations, "question": req.question}

# ─── Candidates ───────────────────────────────────────────────────────────────

@app.get("/candidates", tags=["Candidates"])
def list_candidates():
    return {"candidates": list(candidates_db.values()), "total": len(candidates_db)}

@app.get("/candidates/{candidate_id}", tags=["Candidates"])
def get_candidate(candidate_id: str):
    c = candidates_db.get(candidate_id)
    if not c: raise HTTPException(404, "Candidate not found")
    return c

@app.delete("/candidates/{candidate_id}", tags=["Candidates"])
def delete_candidate(candidate_id: str):
    if candidate_id not in candidates_db: raise HTTPException(404, "Candidate not found")
    del candidates_db[candidate_id]
    global chunks_db
    chunks_db = [c for c in chunks_db if c["candidate_id"] != candidate_id]
    return {"message": "Candidate deleted"}

@app.get("/health", tags=["System"])
def health():
    return {"status": "healthy", "candidates": len(candidates_db),
            "vectors": index.ntotal, "version": "1.0.0"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)