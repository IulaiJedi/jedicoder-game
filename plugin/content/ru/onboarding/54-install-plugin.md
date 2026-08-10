---
node: plugin-install
title: Поставь игру
order: 54
section: install
options: [link-key]
option_titles: ["Поставил — дальше"]
---
Теперь сама игра. Две строки — в том же терминале, не внутри Claude Code:

```
claude plugin marketplace add IulaiJedi/jedicoder-game
claude plugin install jedicoder@jedicoder
```

Первая говорит Claude Code, где игру брать. Вторая её ставит.

Теперь запусти Claude Code в папке проекта, над которым будешь работать, и
набери:

```
/jedicoder:start
```

Именно первой командой в свежей сессии — это важнее, чем кажется. Правила
игры подхватываются при старте сессии, и разговор, начатый раньше, пойдёт
мимо них: игра будет вести себя странно, а ты не поймёшь почему.
