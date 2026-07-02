"""知识库管理接口。"""
from fastapi import APIRouter, UploadFile, HTTPException

from app.zhipu.kb import ensure_kb, list_docs, upload_doc, delete_doc

router = APIRouter(prefix="/api/kb")

@router.get("")
def kb_info():
    docs = list_docs()
    return {"kb_id": ensure_kb(),
            "docs": [{"id": d.get("id"), "name": d.get("name"),
                      "embedding_stat": d.get("embedding_stat"),
                      "fail": (d.get("failInfo") or {}).get("embedding_msg")} for d in docs]}

@router.post("/upload")
async def kb_upload(file: UploadFile):
    try:
        doc_id = upload_doc(file.filename, await file.read())
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"document_id": doc_id}

@router.delete("/docs/{doc_id}")
def kb_delete(doc_id: str):
    delete_doc(doc_id)
    return {"ok": True}
