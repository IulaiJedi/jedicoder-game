---
term: remote
title: Remote
aliases: [ремоут, git remote]
act: 4
rank: sentinel
category: git
xp: 5
related: [repository, push-pull]
example: `git remote -v` показывает адрес на GitHub, обычно под именем origin.
---
**Remote** — адрес репозитория в интернете, куда git отправляет и откуда
забирает коммиты.

**Зачем нужно:** без remote git — записная книжка на одном диске. С ним —
запасная копия, совместная работа и выкладка: сервер тоже забирает код
оттуда. Первый remote по традиции зовут origin.

**Проверь, что понял:** что покажет `git remote -v` в твоём проекте?
