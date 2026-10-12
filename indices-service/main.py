from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException

app = FastAPI(title="Financial Indices Service", version="2.0.0")
logger = logging.getLogger(__name__)
INFLATION_URL = "https://www.cbr.ru/hd_base/infl/"
KEY_RATE_URL = "https://www.cbr.ru/hd_base/KeyRate/"
REQUEST_TIMEOUT = 10.0
MAX_PAGE_BYTES = 2_000_000


class TableParser(HTMLParser):
    """Читает строки таблиц, сохраняя заголовки для проверки формата."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def download(url):
    request = Request(url, headers={
        "User-Agent": "PersonalFinanceStudentProject/2.0",
        "Accept": "text/html",
    })
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        body = response.read(MAX_PAGE_BYTES + 1)
        if len(body) > MAX_PAGE_BYTES:
            raise ValueError("Страница источника слишком большая")
        charset = response.headers.get_content_charset() or "utf-8"
    return body.decode(charset)


def number(value):
    cleaned = value.replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        result = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("Источник вернул неверное число") from exc
    if not result.is_finite():
        raise ValueError("Источник вернул неконечное число")
    return result


def latest_row(html, date_format, pattern, required_headers, columns):
    parser = TableParser()
    parser.feed(html)
    for table in parser.tables:
        if not table:
            continue
        header = " ".join(table[0]).lower()
        if not all(text in header for text in required_headers):
            continue
        rows = []
        for row in table[1:]:
            if len(row) != columns or not re.fullmatch(pattern, row[0]):
                continue
            try:
                dt = datetime.strptime(row[0], date_format)
                # Значения проверяем до выбора строки: при изменении формата
                # лучше выдать ошибку, чем незаметно показать старые данные.
                values = [number(cell) for cell in row[1:]]
            except (ValueError, InvalidOperation) as exc:
                raise ValueError("Изменился формат таблицы Банка России") from exc
            rows.append((dt, row[0], values))
        if rows:
            return max(rows, key=lambda item: item[0])
    raise ValueError("Таблица показателей не найдена на сайте Банка России")


def build_result(inflation_html, key_rate_html):
    _, period, inflation_values = latest_row(
        inflation_html, "%m.%Y", r"\d{2}\.\d{4}",
        ("дата", "ключевая ставка", "инфляция", "цель"), 4,
    )
    _, rate_date, rate_values = latest_row(
        key_rate_html, "%d.%m.%Y", r"\d{2}\.\d{2}\.\d{4}",
        ("дата", "ставка"), 2,
    )
    inflation = inflation_values[1]
    key_rate = rate_values[0]
    # Годовая инфляция = годовой ИПЦ в процентах - 100.
    # Это индекс к тому же месяцу предыдущего года, не месячный ИПЦ.
    cpi = Decimal("100") + inflation
    return {
        "source": "Банк России; первичный источник инфляции — Росстат",
        "source_urls": [INFLATION_URL, KEY_RATE_URL],
        "is_demo": False,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "indices": [
            {
                "name": f"Годовая инфляция ({period})",
                "value": float(inflation), "unit": "%",
                "period": period, "source_url": INFLATION_URL,
            },
            {
                "name": f"Ключевая ставка ({rate_date})",
                "value": float(key_rate), "unit": "%",
                "date": rate_date, "source_url": KEY_RATE_URL,
            },
            {
                "name": f"ИПЦ год к году, расчётный ({period})",
                "value": float(cpi), "unit": "%",
                "period": period, "calculated": True,
                "formula": "100 + годовая инфляция, %",
                "source_url": INFLATION_URL,
            },
        ],
    }


@app.get("/indices")
def get_indices():
    try:
        # Каждый запрос /indices действительно обращается к интернету.
        with ThreadPoolExecutor(max_workers=2) as executor:
            inflation_future = executor.submit(download, INFLATION_URL)
            key_rate_future = executor.submit(download, KEY_RATE_URL)
            result = build_result(inflation_future.result(), key_rate_future.result())
        return result
    except (HTTPError, URLError, TimeoutError, OSError, ValueError,
            UnicodeError) as exc:
        logger.warning("Не удалось получить показатели Банка России: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Не удалось получить показатели с сайта Банка России. "
                   "Проверьте интернет и повторите запрос.",
        ) from exc


@app.get("/health")
def health():
    # Готовность процесса не зависит от доступности внешнего сайта.
    return {"status": "ok", "mode": "internet"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
