---
term: remote
title: Remote
aliases: [ремоут, git remote]
act: 4
rank: sentinel
category: git
xp: 5
related: [repository, push-pull]
---

**Remote** — адрес удалённого репозитория, куда git умеет отправлять и
откуда умеет забирать коммиты. Первый и обычно единственный remote по
традиции зовут **origin**.

**Зачем нужно:** без remote git — записная книжка на одном диске. С ним —
бэкап, совместная работа и деплой: сервер тоже забирает код из remote.

**Проверь, что понял:** что покажет `git remote -v` в твоём проекте?
