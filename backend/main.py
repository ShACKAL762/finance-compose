import os
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import Transaction
from schemas import TransactionCreate, TransactionResponse


INDICES_SERVICE_URL = os.getenv(
    "INDICES_SERVICE_URL",
    "http://web-service:8001",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создаём таблицы при первом запуске приложения.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Personal Finance API",
    description="API для учёта личных доходов и расходов",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="База данных недоступна") from exc
    return {"status": "ok"}


@app.get(
    "/api/transactions",
    response_model=list[TransactionResponse],
)
def get_transactions(db: Session = Depends(get_db)):
    statement = select(Transaction).order_by(
        Transaction.date.desc(),
        Transaction.id.desc(),
    )
    return db.scalars(statement).all()


@app.post(
    "/api/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_transaction(
    transaction_data: TransactionCreate,
    db: Session = Depends(get_db),
):
    transaction = Transaction(
        date=transaction_data.date,
        type=transaction_data.type,
        category=transaction_data.category,
        description=transaction_data.description,
        amount=transaction_data.amount,
    )

    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    return transaction


@app.put("/api/transactions/{transaction_id}", response_model=TransactionResponse)
def update_transaction(transaction_id: int, data: TransactionCreate,
                       db: Session = Depends(get_db)):
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Операция не найдена")
    for key, value in data.model_dump().items():
        setattr(transaction, key, value)
    db.commit()
    db.refresh(transaction)
    return transaction


@app.delete(
    "/api/transactions/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
):
    transaction = db.get(Transaction, transaction_id)

    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Операция не найдена",
        )

    db.delete(transaction)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/indices")
async def get_indices():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{INDICES_SERVICE_URL.rstrip('/')}/indices"
            )
            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Сервис индексов вернул ошибку",
        ) from exc

    except (httpx.RequestError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось получить финансовые индексы",
        ) from exc