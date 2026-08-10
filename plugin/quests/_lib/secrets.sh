# shellcheck shell=bash
# Паттерны строк, похожих на секреты. Общие для актов: Акт 2 ловит утечку
# до пуша (05-env-guard), Акт 4 — перед выходом на GitHub (03m-secrets).
#
# Граница слова у sk- набрана (^|[^A-Za-z0-9]), а не \b: \b — GNU-
# расширение, BSD grep из macOS его не обещает. Голого sk- без границы и
# длины быть не должно: он матчит «risk-assessment» — ложный провал на
# невинном тексте.
#
# Формы: sk-… (устаревший OpenAI-стиль), sk-ant-… (Anthropic), sk-proj-…
# (новый OpenAI), ghp_… (классические токены GitHub), github_pat_…
# (fine-grained), NNNNNNNN:AA… (боты Telegram).
JC_SECRET_RE='((^|[^A-Za-z0-9])sk-[A-Za-z0-9]{16,}|(^|[^A-Za-z0-9])sk-(ant|proj)-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{22,}|[0-9]{8,10}:AA[A-Za-z0-9_-]{30,})'
