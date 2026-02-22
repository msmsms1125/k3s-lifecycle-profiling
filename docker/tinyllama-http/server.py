from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import glob
import time

app = FastAPI()

LLM = None
MODEL_USED = None

class InferReq(BaseModel):
    prompt: str
    n_predict: int = 32
    temperature: float = 0.1

def pick_model_path() -> str:
    env = os.getenv("MODEL_PATH", "").strip()
    if env:
        return env
    cand = sorted(glob.glob("/models/*.gguf"))
    if not cand:
        return ""
    return cand[0]

def init_llm():
    global LLM, MODEL_USED
    if LLM is not None:
        return
    model_path = pick_model_path()
    MODEL_USED = model_path or "(none)"
    if not model_path or not os.path.isfile(model_path):
        return

    from llama_cpp import Llama

    n_ctx = int(os.getenv("N_CTX", "2048"))
    n_threads = int(os.getenv("N_THREADS", "4"))
    n_batch = int(os.getenv("N_BATCH", "128"))

    LLM = Llama(
        model_path=model_path,
        n_ctx=n_ctx,
        n_threads=n_threads,
        n_batch=n_batch,
        verbose=False,
    )

@app.get("/health")
def health():
    models_dir_ok = os.path.isdir("/models")
    preview = []
    if models_dir_ok:
        try:
            preview = sorted(os.listdir("/models"))[:20]
        except Exception:
            preview = ["(list failed)"]

    llm_ok = False
    err = None
    try:
        init_llm()
        llm_ok = (LLM is not None)
    except Exception as e:
        err = str(e)

    return {
        "ok": models_dir_ok and llm_ok,
        "models_dir": "/models",
        "files_preview": preview,
        "model_used": MODEL_USED,
        "llm_loaded": llm_ok,
        "error": err,
    }

@app.post("/infer")
def infer(req: InferReq):
    init_llm()
    if LLM is None:
        raise HTTPException(status_code=500, detail=f"model not loaded (model_used={MODEL_USED})")

    t0 = time.time()
    out = LLM(
        req.prompt,
        max_tokens=req.n_predict,
        temperature=req.temperature,
        stop=[],
    )
    t1 = time.time()

    text = out.get("choices", [{}])[0].get("text", "")
    return {
        "text": text,
        "latency_ms": int((t1 - t0) * 1000),
        "n_predict": req.n_predict,
        "temperature": req.temperature,
        "model_used": MODEL_USED,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
