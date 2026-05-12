from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import Optional
import sqlite3
import secrets
import os

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Paul Café API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # в продакшене укажи домен сайта
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Basic Auth для admin ───────────────────────────────────────────────────────
security = HTTPBasic()
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "paul2025")   # поменяй в .env!

def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(credentials.username, ADMIN_USER)
    ok_pass = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# ── Database ──────────────────────────────────────────────────────────────────
DB = "paul_cafe.db"

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    conn = sqlite3.connect(DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS menu_items (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT    NOT NULL,
            name     TEXT    NOT NULL,
            desc     TEXT    DEFAULT '',
            price    INTEGER NOT NULL,
            active   INTEGER DEFAULT 1
        )
    """)
    count = conn.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
    if count == 0:
        items = [
            ("Ըմպելիքներ", "Էսպրեսո",           "Մաքուր, կենտրոնացված, արթնացնող",      700),
            ("Ըմպելիքներ", "Կապուչինո",           "Թանձր կաթ, փափուկ փրփուր",              900),
            ("Ըմպելիքներ", "Ֆլեթ Ուայթ",         "Կրկնակի շոտ, մետաքսյա կաթ",           1000),
            ("Ըմպելիքներ", "Մաչա Լաթե",           "Ճապոնական կանաչ թեյ, գոլ կաթ",        1200),
            ("Ըմպելիքներ", "Սպիտակ Հոտ Չոկոլադ", "Կաթ, բելգիական սպիտակ շոկոլադ",       1100),
            ("Թխվածք",     "Կռուասան",            "Թարմ թխված, կարագե, շերտ-շերտ",        800),
            ("Թխվածք",     "Բրունի",              "Մուգ շոկոլադ, ձեթածոր հյուսվածք",      700),
            ("Թխվածք",     "Ավոկադո Թոսթ",        "Թարմ հաց, ավոկադո, ռեհան, ձու",       1800),
            ("Թխվածք",     "Գրանոլա",             "Թարմ մրգեր, հունական մածուն, մեղր",    1500),
        ]
        conn.executemany(
            "INSERT INTO menu_items (category, name, desc, price) VALUES (?,?,?,?)",
            items
        )
    conn.commit()
    conn.close()

init_db()

# ── Schemas ───────────────────────────────────────────────────────────────────
class MenuItem(BaseModel):
    category: str
    name: str
    desc: Optional[str] = ""
    price: int
    active: Optional[bool] = True

class MenuItemUpdate(BaseModel):
    category: Optional[str] = None
    name: Optional[str] = None
    desc: Optional[str] = None
    price: Optional[int] = None
    active: Optional[bool] = None

# ── Public endpoints ──────────────────────────────────────────────────────────
@app.get("/menu", tags=["Public"])
def get_menu(db: sqlite3.Connection = Depends(get_db)):
    """Активное меню, сгруппированное по категориям."""
    rows = db.execute(
        "SELECT * FROM menu_items WHERE active=1 ORDER BY category, id"
    ).fetchall()
    grouped: dict = {}
    for row in rows:
        cat = row["category"]
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append({
            "id":    row["id"],
            "name":  row["name"],
            "desc":  row["desc"],
            "price": row["price"],
        })
    return grouped

# ── Admin endpoints ───────────────────────────────────────────────────────────
@app.get("/admin/menu", tags=["Admin"])
def admin_list(db: sqlite3.Connection = Depends(get_db), _=Depends(require_admin)):
    """Все позиции включая скрытые."""
    rows = db.execute("SELECT * FROM menu_items ORDER BY category, id").fetchall()
    return [dict(r) for r in rows]

@app.post("/admin/menu", status_code=201, tags=["Admin"])
def admin_create(item: MenuItem, db: sqlite3.Connection = Depends(get_db), _=Depends(require_admin)):
    """Добавить позицию."""
    cur = db.execute(
        "INSERT INTO menu_items (category, name, desc, price, active) VALUES (?,?,?,?,?)",
        (item.category, item.name, item.desc, item.price, int(item.active))
    )
    db.commit()
    return {"id": cur.lastrowid, **item.dict()}

@app.put("/admin/menu/{item_id}", tags=["Admin"])
def admin_update(item_id: int, item: MenuItemUpdate, db: sqlite3.Connection = Depends(get_db), _=Depends(require_admin)):
    """Обновить позицию частично."""
    existing = db.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "Позиция не найдена")
    updates = {k: v for k, v in item.dict().items() if v is not None}
    if not updates:
        return {"message": "Нечего обновлять"}
    fields = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [item_id]
    db.execute(f"UPDATE menu_items SET {fields} WHERE id=?", values)
    db.commit()
    return {"message": "Обновлено", "id": item_id}

@app.delete("/admin/menu/{item_id}", tags=["Admin"])
def admin_delete(item_id: int, db: sqlite3.Connection = Depends(get_db), _=Depends(require_admin)):
    """Удалить позицию."""
    existing = db.execute("SELECT id FROM menu_items WHERE id=?", (item_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "Позиция не найдена")
    db.execute("DELETE FROM menu_items WHERE id=?", (item_id,))
    db.commit()
    return {"message": "Удалено", "id": item_id}
