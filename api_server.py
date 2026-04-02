"""
補助用 HTTP サーバ（FastAPI）。
本番のメインUIは Streamlit（app.py）を推奨。本サーバはヘルスチェック・運用確認用。

起動例:
  uvicorn api_server:app --host 0.0.0.0 --port 8080

Docker / Render / Railway では streamlit 用 Dockerfile か、本 API のみを別プロセスで動かすことも可能。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="GENTA Scope", version="1.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "data_pipeline": "Stooq-first for Tokyo (.T), then yfinance; see market_fetch.py",
    }


@app.get("/")
def root():
    return {
        "message": "源太AI ハゲタカSCOPE",
        "ui": "streamlit run app.py",
        "docs": "/docs",
    }
