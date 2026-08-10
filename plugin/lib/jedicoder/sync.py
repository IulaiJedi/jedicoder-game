"""Отправка накопленных событий боту потока.

Сеть не обязательна: любая её неудача — тихий отказ без потери очереди.
Повтор после обрыва безопасен: бот идемпотентен по client_id.
"""

import json
import os
import urllib.error
import urllib.request

from . import state as st

DEFAULT_ENDPOINT = "https://jedicoder.store/api/events"
CHUNK = 100
TIMEOUT = 5


def endpoint():
    return os.environ.get("JEDICODER_SYNC_URL") or DEFAULT_ENDPOINT


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _post(link_key, events, timeout=TIMEOUT):
    """Одна пачка. Возвращает (status, accepted, known).

    status: "ok" | "bad_batch" | "error" | "unknown_key".

    Тело ответа обязано разбираться: бот на неизвестный/сгоревший link_key
    тоже отвечает 200, но с accepted == known == 0 на непустую пачку — это
    единственная разница между честным приёмом и молчаливой потерей событий,
    и до этой правки плагин её не видел вовсе (игнорировал тело ответа).
    """
    try:
        body = json.dumps(
            {"link_key": link_key, "events": events}, ensure_ascii=False
        ).encode("utf-8")
        request = urllib.request.Request(
            endpoint(), data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        # 400 — пачка битая (баг плагина): выбрасываем, чтобы не отравить
        # очередь навсегда. Остальное — временная беда, попробуем позже.
        return ("bad_batch" if exc.code == 400 else "error"), 0, 0
    except Exception:
        return "error", 0, 0

    try:
        reply = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        reply = {}
    if not isinstance(reply, dict):
        reply = {}
    accepted = _int(reply.get("accepted"))
    known = _int(reply.get("known"))
    if events and accepted + known < len(events):
        # Непустая пачка, а бот не признал ни одного события ни принятым,
        # ни уже известным: ключ ему не знаком (чужой или умерший после
        # /newkey). Формально это тот же 200, но по смыслу — отказ.
        return "unknown_key", accepted, known
    return "ok", accepted, known


def flush(state_path):
    """Отправить очередь пачками. Возвращает (sent, dropped, remaining, status).

    status ∈ {"ok", "error", "unknown_key"}: "ok" — очередь дослана до конца
    (или изначально была пуста / без ключа), "error" — сетевая беда (повтор
    безопасен, ничего не потеряно), "unknown_key" — бот не узнал link_key:
    пачка НЕ вычёркивается, чтобы события не терялись навсегда молча.

    Снимок пачки читается без замка, сеть ходит без замка, и только
    вычёркивание отправленного — под замком: держать блокировку на время
    сетевого вызова значит остановить хуки падавана на секунды.
    """
    sent = dropped = 0
    while True:
        data = st.load(state_path)
        link_key = data.get("link_key")
        queue = list(data.get("pending_sync") or [])
        if not link_key or not queue:
            return sent, dropped, len(queue), "ok"
        chunk = queue[:CHUNK]
        status, _accepted, _known = _post(link_key, chunk)
        if status in ("error", "unknown_key"):
            return sent, dropped, len(queue), status
        chunk_ids = set(event.get("client_id") for event in chunk)
        with st.update_state(state_path) as fresh:
            fresh["pending_sync"] = [
                event for event in (fresh.get("pending_sync") or [])
                if event.get("client_id") not in chunk_ids
            ]
        if status == "ok":
            sent += len(chunk)
        else:
            dropped += len(chunk)


def maybe_flush(state_path):
    """Тихая попытка после команды CLI: не печатает и не бросает никогда.

    На "unknown_key" ведёт себя так же тихо, как на сетевой ошибке: просто
    не дренирует. Явный разговор с падаваном про ключ — дело `sync`/`link`,
    а не фоновой попытки после каждой команды.
    """
    try:
        data = st.load(state_path)
        if data.get("link_key") and data.get("pending_sync"):
            flush(state_path)
    except Exception:
        pass
