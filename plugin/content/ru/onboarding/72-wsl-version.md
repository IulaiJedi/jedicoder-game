---
node: wsl-version
title: Первая версия WSL вместо второй
order: 72
section: trouble
probe: wsl --list --verbose
options: [check-version, no-luck]
option_titles: ["Проверить версию снова", "Не помогло"]
---
Ещё одна частая причина — старая версия самой WSL. Признак у неё
однозначный: «cannot execute binary file: Exec format error».

Посмотри в PowerShell:

```
wsl --list --verbose
```

В колонке VERSION должна стоять двойка. Стоит единица — переключи, подставив
своё имя дистрибутива из той же таблицы:

```
wsl --set-version Ubuntu 2
```

И отдельно, раз ты здесь: если браузер из WSL не открывается сам, а вместо
перехода печатается код — это не поломка. Скопируй код из браузера на Windows
и вставь обратно в окно WSL.
