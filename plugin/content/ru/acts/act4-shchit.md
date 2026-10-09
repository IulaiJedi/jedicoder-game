---
act: 4
slug: act4-shchit
title: Щит
rank: sentinel
rank_title: Страж
artifact: cso
# <!-- lint:novelty-skip --> значение оси ниже — идентификатор для движка и Голокрона, а не слово катсцены: падаван видит только тело файла, а слово deploy разбирается в Акте 5
axis: deploy
# <!-- lint:novelty-skip-end -->
muted: true
quests: [01-remote, 02-rotation, 03m-secrets, 04m-guard, 03v-user, 04v-firewall, 05v-hygiene]
quest_titles: ["Репозиторий на GitHub", "Ротация утёкшего токена", "Секреты вне репозитория", "2FA и права деплоя", "Уход с root", "Файрвол и fail2ban", "Гигиена сервера"]
quest_branches: [both, both, managed, managed, vps, vps, vps]
---
В этом акте ты кладёшь код на GitHub — сайт-хранилище кода — и защищаешь
ключи и сервер.

Ключ в открытом репозитории боты находят за минуты, а платят те, кто
тебе поверил.
