#!/usr/bin/env python3
"""Единая точка входа для скиллов и команд плагина.

Скиллы — markdown, поэтому вся логика вызывается отсюда одной командой,
а скилл только пересказывает вывод падавану по правилам контракта.
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jedicoder import acts, content, contract, debrief, frontmatter, quests, ranks, scroll, sync  # noqa: E402
from jedicoder import state as st  # noqa: E402

SUBCOMMANDS = (
    "status", "contract", "enter", "check", "ack", "project", "track",
    "artifact", "debrief", "scroll", "link", "sync", "finale", "book", "root",
    "reset", "recipe",
)

# Адрес сайта: на нём живёт Книга — разворот главы в браузере. Переменная
# окружения — по образцу sync.endpoint(): нужна тестам и локальной проверке,
# падавану про неё знать незачем.
DEFAULT_SITE_URL = "https://jedicoder.store"

# Метка, которую ставит десктопный Голокрон, запуская Claude Code у себя в
# Верстаке (golokron/src/main/workbench/launch.ts, GOLOKRON_MARK). Внутри
# него Книга в браузере не нужна: разворот главы, доску квестов и счётчики
# показывает Сцена справа — то же самое, только рядом с терминалом. Вопрос
# «открывать ли Книгу» падавану внутри Голокрона звучит как «открыть
# Голокрон в браузере?» — живой прогон 2026-09-10 — и не задаётся.
GOLOKRON_MARK = "JEDICODER_GOLOKRON"


def _inside_golokron():
    return bool(os.environ.get(GOLOKRON_MARK))

# Маршрут страницы финала на сайте. Отдельной константой и ровно одной: тот
# же адрес печатает карточка ранга и уносит с собой Свиток, а адрес, набранный
# в двух местах, расходится молча — переехал маршрут, и половина падаванов
# уходит в 404 из файла, который лежит у них в проекте навсегда.
FINALE_PATH = "finale"

# content/ лежит внутри plugin/: при установке из маркетплейса Claude Code
# копирует в кэш только source-папку, и всё снаружи неё не приезжает
# (подтверждено вживую 2026-07-27).
DEFAULT_CONTENT_ROOT = Path(__file__).resolve().parents[2] / "content" / "ru"
DEFAULT_QUESTS_ROOT = Path(__file__).resolve().parents[2] / "quests"

USAGE = "Команды: " + ", ".join(SUBCOMMANDS)

# Одноразовые объяснения от миграций состояния. Это не сообщение об ошибке,
# а разговор с человеком, у которого игра только что забрала ранг: сначала
# что произошло, потом что сохранено, потом как вернуть.
NOTICES = {
    st.NOTICE_ACT1_REAL: (
        "Плагин обновился: Акт 1 стал настоящим. Раньше он закрывался одним\n"
        "словом, теперь — квестами ресерча, и старое подтверждение больше его\n"
        "не закрывает. Пройденное дальше не потеряно: закрытые квесты Акта 2\n"
        "на месте, все до одного. Ранг считается по актам, закрытым подряд с\n"
        "первого, — он вернётся сам, как только закроешь Акт 1."
    ),
}


def _project_path(data):
    """Путь проекта из сохранения — непустой строкой или None.

    Мусор читается как отсутствие, тем же правилом, что track_of и deploy_of
    в acts.py, и раздел проверяется раньше значения по той же причине, что
    и там: сохранение правят руками и откатывают на версию назад, а
    project мог перестать быть словарём целиком.

    Оба следствия видны падавану. Path() на списке роняет TypeError в самой
    частой команде игры, а напечатанный как есть список дал бы «Папка
    проекта: ['/tmp']» — питоновский литерал, поданный как исправный путь,
    то есть ложное успокоение ровно там, где тикет требует тревоги.
    """
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    path = project.get("path")
    if not isinstance(path, str) or not path:
        return None
    return path


def _project_lines(data, project_exists):
    """Строки первого экрана про папку проекта — куда игра вообще смотрит.

    Живой заход 2026-09-06: путь в сохранении указывал на песочницу прошлой
    сессии, которой давно нет. Карта показывала «0 из 6» на фактически
    сделанном акте, серия сохранений стояла на нуле, и причину пришлось
    искать по файловой системе — потому что первый экран называл ранг, XP,
    Тёмную сторону, серию и карту, и ни слова о папке.

    `project_exists` — факт с диска, и добывает его вызывающий
    (`_project_exists`): здесь чистая функция от сохранения, чтобы тесты
    первого экрана оставались словарными и не зависели от того, что лежит
    на машине.

    Тревога — ровно на `False`, то есть «смотрели и не нашли». Не смотрели
    вовсе (`None` при заданном пути) — путь называется как есть: пугать
    падавана незнанием хуже, чем промолчать.

    Слова здесь ранние. Первый экран печатается до любого акта, и «папка»,
    «проверка», «квест» падаван к этому моменту уже встретил, а
    «репозиторий» — нет; по той же причине ниже стоит «серия сохранений», а
    не «серия коммитов».
    """
    path = _project_path(data)
    if path is None:
        # Пути нет: check возьмёт «.», то есть каталог запуска Claude Code.
        # Это почти никогда не то, чего ждёт человек, и молчание тут читается
        # как «игра знает, где мой проект». Серия названа тем же следствием,
        # что и ниже: commit_pulse выходит и на пустом пути, поэтому нуль
        # строкой выше врёт здесь ровно так же, как на мёртвом пути.
        return [
            "Папка проекта не установлена.",
            "  Проверки квестов пойдут из текущей папки, серия сохранений "
            "не растёт.",
            "  Назови папку: project path <путь>",
        ]
    if project_exists is False:
        # Слова те же, что у _cmd_check («Не найдена папка проекта»), —
        # один случай не должен называться на двух экранах по-разному.
        # Порядок другой: все три случая блока открываются словами «Папка
        # проекта», и вместе они читаются как одна строка о разном.
        return [
            "Папка проекта не найдена: {}".format(path),
            "  Игра смотрит туда: квесты не проверяются, серия сохранений "
            "не растёт.",
            "  Назови папку заново: project path <путь>",
        ]
    return ["Папка проекта: {}".format(path)]


def render_status(data, project_exists):
    rank = data.get("rank", st.RANK_YOUNGLING)
    lines = [
        "Ранг: {} ({})".format(ranks.RANK_TITLES.get(rank, rank), rank),
    ]
    # Начисление за квесты уже живо (20 XP за первое закрытие check/ack).
    # Нулевой счётчик не печатается до первого начисления: вечное «XP: 0»
    # читается как сломанная механика, а появившееся число — как награда.
    # term.xp (лут словаря) приедет с хуком словаря-лута.
    if data.get("xp", 0):
        lines.append("XP: {}".format(data["xp"]))
    # Нулевой счётчик молчит — все три, а не только XP. Довод у них общий и
    # уже записан строкой выше: вечный ноль читается как сломанная механика, а
    # появившееся число — как награда. Живой заход 2026-09-10 показал вторую
    # половину той же цены: новичок, впервые открывший игру, получал список из
    # пяти незнакомых величин — «Тёмная сторона: 0», «Серия сохранений: 0
    # (лучшая 0)» — и читал первый экран как приборную панель чужого самолёта.
    # Тёмная сторона на нуле вдобавок называет наказание раньше, чем падаван
    # успел что-то сделать; она обязана появляться вместе с первым очком, и
    # тогда её видно.
    if data.get("dark_side", 0):
        lines.append("Тёмная сторона: {}".format(data["dark_side"]))
    streak = data.get("streak", {})
    if streak.get("current", 0) or streak.get("best", 0):
        # «Сохранений», а не «коммитов»: эта строка печатается на самом
        # первом экране, до любого акта, а слово «коммит» падаван получает
        # только в Акте 2. Игра сама называет коммит точкой сохранения —
        # значит на первом экране у счётчика есть честное имя, которое ничего
        # не должно объяснять заранее. Регрессия закрыта тестом первого
        # экрана в tests/test_cli.py: линтер контента сюда не дотягивается.
        lines.append(
            "Серия сохранений: {} (лучшая {})".format(
                streak.get("current", 0), streak.get("best", 0)
            )
        )
    lines.append("")
    lines += _project_lines(data, project_exists)
    lines.append("")
    lines.append("Карта:")
    for number in sorted(ranks.ACTS):
        entry = (data.get("acts") or {}).get(str(number)) or {}
        status = entry.get("status")
        if ranks.is_muted(number):
            # Выключенный акт с карты не убран намеренно: падаван должен
            # видеть, что дорога есть и она не кончилась насовсем.
            lines.append(
                "  [·] Акт {}. {} — готовится, в клубе".format(
                    number, ranks.ACTS[number]["title"]
                )
            )
            continue
        if status == ranks.STATUS_DONE:
            mark = "[x]"
        elif status == ranks.STATUS_IN_PROGRESS:
            mark = "[>]"
        else:
            mark = "[ ]"
        # Знаменатель берётся из реестра акта, а не из записанных квестов:
        # иначе после первого закрытого квеста карта показывала «1/1» и
        # падаван читал недопройденный акт как пройденный.
        #
        # Числитель фильтруется по треку вместе со знаменателем: иначе после
        # смены трека закрытый квест старой ветки попадал в счёт списка,
        # в котором его нет, и карта показывала 3/7 вместо 2/7.
        if status == ranks.STATUS_DONE:
            # У закрытого акта счётчик не печатается: галочка самодостаточна.
            # После смены трека дробь была правдива, но читалась как
            # «осталось пять» — а акт закрыт, и на ранг эти квесты уже не
            # влияют. По той же причине здесь не место и строке про
            # невыбранный трек: у пройденного акта нечего выбирать.
            progress = ""
        else:
            try:
                branch = acts.branch_of(data, number)
                total = len(acts.quest_ids(number, branch))
                done = acts.closed_count(data, number, branch)
                progress = " — квестов закрыто: {}/{}".format(done, total)
            except acts.TrackRequiredError:
                # Ловится раньше UnknownActError намеренно: TrackRequiredError
                # от неё наследуется, и в обратном порядке падаван читал бы
                # «квесты ещё не завезены» вместо «выбери трек».
                progress = " — трек не выбран: track craftsman или track founder"
            except acts.DeployRequiredError:
                progress = (
                    " — путь деплоя не назван: project deploy managed|vps"
                )
            except acts.UnknownActError:
                progress = ""
        lines.append(
            "  {} Акт {}. {}{}".format(mark, number, ranks.ACTS[number]["title"], progress)
        )

    artifacts = data.get("artifacts") or []
    lines.append("")
    lines.append(
        "Артефакты: {}".format(", ".join(artifacts) if artifacts else "пока ни одного")
    )
    lines.append(
        "Открыто слов: {}".format(len(data.get("lexicon_unlocked") or []))
    )
    counters = data.get("first_try") or {}
    if counters.get("attempted"):
        lines.append(
            "С первой попытки: {}/{}".format(
                counters.get("passed", 0), counters.get("attempted", 0)
            )
        )
    return "\n".join(lines)


def _project_exists(data):
    """Лежит ли на диске папка, записанная в сохранении.

    Единственное обращение к диску на первом экране, и оно здесь, а не в
    render_status: печать остаётся чистой функцией от сохранения.

    True, False или None — когда пути нет вовсе и смотреть попросту не на
    что; мусор в поле к этому моменту уже прочитан как отсутствие
    (_project_path).
    """
    path = _project_path(data)
    if path is None:
        return None
    return Path(path).is_dir()


def _load(state_path):
    data = st.load(state_path)
    if not data.get("padawan_id"):
        data["padawan_id"] = st.new_padawan_id()
        st.save(data, state_path)
    return data


def _cmd_status(args, state_path, content_root, quests_root):
    data = _load(state_path)
    print(render_status(data, _project_exists(data)))
    # Объяснение печатается после карты: именно на карте человек и видит то,
    # что его удивило — переоткрытый Акт 1 и упавший ранг.
    notices = data.get("notices")
    if not isinstance(notices, list):
        # Поле правили руками: показывать нечего, но и падать перед падаваном
        # из-за этого нельзя. Ниже оно всё равно будет снято.
        notices = []
    for key in notices:
        # Не просто «список», а «список строк»: словарь или список внутри
        # нехешируем, и NOTICES.get уронил бы трейсбеком самую частую команду
        # игры. Показать такой элемент всё равно нечем — пропускаем молча.
        if not isinstance(key, str):
            continue
        text = NOTICES.get(key)
        if text:
            print("")
            print(text)
    if data.get("notices"):
        # Снимаем все, включая незнакомые: показать их нечем, а висеть в
        # состоянии вечно они не должны. Повторять объяснение каждую команду
        # — навязчиво: человеку сказали один раз, дальше он играет.
        data["notices"] = []
        st.save(data, state_path)
    return 0


def _cmd_contract(args, state_path, content_root, quests_root):
    """Контракт — первая команда каждого скилла.

    Поэтому она не имеет права упасть трейсбеком: падаван увидел бы
    FileNotFoundError вместо игры и не понял бы, что делать.
    """
    data = _load(state_path)
    try:
        body = contract.load_behavior(content_root)
        text = contract.render(body, data.get("passport"))
    except (OSError, UnicodeDecodeError):
        print(
            "Не найден или не читается файл контракта: {}/behavior.md. "
            "Похоже, плагин установлен не полностью — переустанови его.".format(
                content_root
            )
        )
        return 1
    except frontmatter.FrontmatterError as exc:
        print(
            "Файл контракта {}/behavior.md испорчен: {}. "
            "Переустанови плагин.".format(content_root, exc)
        )
        return 1
    except contract.ContractError as exc:
        # Квиза и команды правки паспорта в этой версии нет, поэтому сюда
        # попадают только состояния, поправленные руками. Обещать падавану
        # действие, которого в игре не существует, нельзя.
        print(
            "Не смог собрать контракт: в настройках под тебя неизвестное "
            "значение ({}). Это не твоя ошибка — сообщи автору игры.".format(exc)
        )
        return 1
    print(text)
    return 0


def _site_base():
    """Корень сайта без хвостового слэша. Один на все адреса игры.

    Переменная окружения читается здесь, а не у каждого адреса своя: два
    чтения одной переменной — это два места, где она может остаться
    непрочитанной.
    """
    return (os.environ.get("JEDICODER_SITE_URL") or DEFAULT_SITE_URL).rstrip("/")


def _finale_url():
    """Страница финала: автор, его продукты и клуб. Общая для всех.

    Без ключа привязки намеренно (спека #33): игра обязана работать с пустой
    привязкой, и персонального на этой странице нет — персональное лежит у
    падавана в Свитке.
    """
    return "{}/{}".format(_site_base(), FINALE_PATH)


def _book_url(data, act=None):
    """Ссылка на разворот главы. Ключ уходит СЕГМЕНТОМ ПУТИ, не '?key='.

    Причина не косметическая: explorer.exe не открывает URL с query-строкой,
    вместо браузера вылезает окно Проводника (microsoft/WSL#3832). Маршрут
    спроектирован под ограничение опенера, а не чинится потом.

    Номер акта — тем же способом, третьим сегментом, и ТОЛЬКО вместе с
    ключом: адрес /kniga/2 без ключа попал бы в роут kniga/:linkKey, «2»
    прочиталось бы как ключ, и падаван получил бы «Эта глава не открылась»
    вместо витрины.
    """
    base = _site_base()
    key = data.get("link_key")
    if key and _valid_key(key):
        if act:
            return "{}/kniga/{}/{}".format(base, key, act)
        return "{}/kniga/{}".format(base, key)
    return "{}/kniga".format(base)


def _is_wsl():
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        with open("/proc/version", "r") as handle:
            return "microsoft" in handle.read().lower()
    except OSError:
        return False


def _openers():
    """Кандидаты в порядке предпочтения. Платформа раньше POSIX-универсалий:
    поставленный руками xdg-open на WSL находится и проваливается
    (microsoft/WSL#8892), поэтому проверять его первым нельзя."""
    if _is_wsl():
        # cmd.exe последним и с cwd=/mnt/c: из линуксового каталога он
        # печатает предупреждение про UNC-пути, а нам нужна тишина.
        return [["wslview"], ["explorer.exe"], ["cmd.exe", "/c", "start", ""]]
    if sys.platform == "darwin":
        return [["open"]]
    if sys.platform == "win32":
        return []          # там отдельная ветка через os.startfile
    return [["xdg-open"], ["gio", "open"]]


def _open_in_browser(url):
    """Best-effort. Ничего не печатает, ничего не возвращает, не бросает.

    webbrowser из stdlib здесь не годится, хотя правило нуля зависимостей и
    не нарушает: на WSL — основном целевом окружении — он возвращает True,
    ничего не открыв, и печатает чужую диагностику в терминал падавана
    (проверено вживую 2026-07-31, cpython#89752 открыт с 2021 года).

    Исход намеренно не проверяется: explorer.exe возвращает 1 при успешном
    открытии (microsoft/WSL#6565), поэтому любая проверка кода возврата
    печатала бы падавану ложь. Ссылка напечатана строкой выше — этого хватает.
    """
    try:
        if sys.platform == "win32" and hasattr(os, "startfile"):
            os.startfile(url)
            return
        for command in _openers():
            if shutil.which(command[0]) is None:
                continue
            try:
                subprocess.Popen(
                    command + [url],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL, start_new_session=True,
                    cwd="/mnt/c" if command[0] == "cmd.exe" else None,
                )
                return
            except OSError:
                continue
    except Exception:
        # Тот же закон, что у хуков: не смог открыть — не мешаю.
        return


def _parse_act(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError("нет акта {!r}".format(raw))


def _print_quest_list(data, act, content_root):
    branch = acts.branch_of(data, act)
    ids = acts.quest_ids(act, branch)
    titles = {}
    try:
        scene = next(
            (item for item in content.load_acts(content_root) if item.act == act),
            None,
        )
    except (OSError, UnicodeDecodeError, content.ContentError,
            frontmatter.FrontmatterError):
        scene = None
    if scene is not None:
        titles = dict(zip(scene.quests, scene.quest_titles))
    print("")
    print("Квесты акта ({}):".format(len(ids)))
    for quest_id in ids:
        title = titles.get(quest_id, "")
        tail = " — {}".format(title) if title else ""
        if acts.quest_kind(act, quest_id) == acts.KIND_ACK:
            tail += " (без проверки: ack {} {})".format(act, quest_id)
        print("  {}{}".format(quest_id, tail))


def _cmd_enter(args, state_path, content_root, quests_root):
    if not args:
        print("Укажи номер акта: enter 1")
        return 1
    data = _load(state_path)
    # Читаем флаг до любой мутации: ниже мы сами поставим его в True, и
    # тогда «спрашивали ли раньше» будет уже не отличить.
    asked_before = bool(data.get("book_asked"))
    try:
        act = _parse_act(args[0])
    except ValueError as exc:
        print(str(exc))
        return 1
    # Выключенный акт отказывает раньше порядка: тому, кто дошёл до конца,
    # надо услышать «пятый готовится», а не «сперва закрой четвёртый».
    if ranks.is_muted(act):
        info = ranks.ACTS.get(act) or {}
        print(
            "Акт {}. {} — готовится. Игра пока заканчивается Актом {}.".format(
                act, info.get("title", ""), ranks.FINAL_ACT
            )
        )
        print(
            "Деплой, домен и публикацию разбираем в клубе — ссылка в финале: finale."
        )
        return 1
    # Порядок отказов: сначала порядок актов, потом наличие квестов. Тому,
    # кто не закрыл Акт 2, надо услышать про Акт 2 — про то, что Акт 3 ещё
    # не написан, он узнает, когда дойдёт. can_enter_act только читает,
    # поэтому отказ здесь ничего не записывает.
    try:
        allowed, reason = ranks.can_enter_act(data, act)
    except ValueError as exc:
        # «enter 9»: такого акта нет вовсе. Текст берём у ranks — он здесь
        # единственный источник правды о существовании акта.
        print(str(exc))
        return 1
    if not allowed:
        print(reason)
        return 1
    # Трек и наличие квестов спрашиваются до enter_act, чтобы отказ ничего не
    # записал: иначе акт остался бы начатым, а падаван — без списка квестов.
    try:
        acts.quest_ids(act, acts.branch_of(data, act))
    except acts.TrackRequiredError:
        print(
            "Состав Акта {} зависит от трека. Квестов у Ремесленника: {}, "
            "у Основателя: {}.".format(
                act,
                len(acts.quest_ids(act, acts.TRACK_CRAFTSMAN)),
                len(acts.quest_ids(act, acts.TRACK_FOUNDER)),
            )
        )
        print(
            "Выбери: track craftsman — делаю для себя и близких; "
            "track founder — ищу пользователей."
        )
        return 1
    except acts.DeployRequiredError:
        print(
            "Состав Акта {} зависит от пути деплоя. Квестов на managed: {}, "
            "на vps: {}.".format(
                act,
                len(acts.quest_ids(act, acts.DEPLOY_MANAGED)),
                len(acts.quest_ids(act, acts.DEPLOY_VPS)),
            )
        )
        print(
            "Назови путь: project deploy managed — хостинг-панель, как в "
            "рецепте; project deploy vps — свой сервер."
        )
        return 1
    except acts.UnknownActError:
        # Акт объявлен в реестре актов, но квестов для него ещё нет. Пускать
        # туда нельзя: игра объявила бы акт начатым и выдала артефакт, первый
        # же check ответил бы «квесты ещё не завезены», а артефакт остался бы
        # открытым — и отпёрся бы у того, кто акт не проходил. Скилл обязан
        # акты 4–5 не обещать; CLI обязан их не раздавать.
        print(
            "Акта {} «{}» в игре пока нет — его квесты ещё не написаны.".format(
                act, ranks.ACTS[act]["title"]
            )
        )
        print(
            "Пока игра заканчивается Актом {}. Остальное придёт следующими "
            "версиями плагина.".format(max(acts.QUESTS_BY_ACT))
        )
        return 1
    try:
        ranks.enter_act(data, act)
    except (ValueError, ranks.ProgressionError) as exc:
        # Оба случая уже отсеяны проверками выше. Страховка стоит потому, что
        # enter_act — тот, кто пишет состояние: если правило прогрессии
        # ужесточится, падаван должен увидеть фразу, а не traceback.
        print(str(exc))
        return 1
    # Миграция бет: акт мог быть закрыт до появления claude_md_sha (или
    # библиотечным путём). Дозаписываем на входе в следующий — хэш будет
    # текущим, но это честнее, чем оставить босса без точки отсчёта.
    prev_entry = (data.get("acts") or {}).get(str(act - 1))
    if (prev_entry and prev_entry.get("status") == ranks.STATUS_DONE
            and "claude_md_sha" not in prev_entry):
        project_path = (data.get("project") or {}).get("path")
        if project_path:
            prev_entry["claude_md_sha"] = _claude_md_sha(project_path)
    # Флаг «вопрос напечатан» вносится в тот же data, что уходит в st.save
    # ниже: вторая запись состояния расширила бы окно гонки долга №8, а
    # печатать вопрос дважды нельзя. Внутри Голокрона вопрос не задаётся и
    # флаг не ставится: выйдя в обычный терминал, падаван его услышит.
    inside_golokron = _inside_golokron()
    if not asked_before and not inside_golokron:
        data["book_asked"] = True
    st.save(data, state_path)
    info = ranks.ACTS[act]
    print("Акт {}. {} — начат.".format(act, info["title"]))
    print("Артефакт этого акта: {}".format(info["artifact"]))
    print("Ранг за прохождение: {}".format(ranks.RANK_TITLES[info["rank"]]))
    # Состав ветки — здесь, а не только в скилле: после `enter 4` падаван
    # узнавал список квестов из SKILL.md, игра его не называла (живой прогон
    # 2026-09-10). Подписи — из фронтматтера акта; ack помечен прямо в
    # строке, чтобы check не гоняли там, где нужен ack.
    _print_quest_list(data, act, content_root)
    # Все печати — после st.save: если что-то в них взорвётся, акт уже начат
    # и записан. Катсцена — безусловно, никакого «если привязан»: игра
    # обязана быть проходимой непривязанной, и повествование часть игры,
    # а не награда за привязку.
    try:
        scene = next(
            (item for item in content.load_acts(content_root) if item.act == act),
            None,
        )
    except (OSError, UnicodeDecodeError, content.ContentError,
            frontmatter.FrontmatterError):
        # Контент испорчен — акт всё равно начат и записан. Ронять enter
        # из-за текста нельзя: падаван потеряет вход в акт, а не абзац.
        scene = None
    if scene is not None:
        print("")
        print(scene.body)
    if inside_golokron:
        # Книгу показывает Сцена справа; ни ссылки, ни вопроса, ни вкладки.
        return 0
    print("")
    print("Разворот этой главы: {}".format(_book_url(data, act)))
    if not data.get("link_key"):
        print(
            "Прогресс в Книге появится после привязки: ключ выдаёт команда "
            "/link в боте потока, привязывает — link <ключ>."
        )
    if not asked_before:
        # input() здесь невозможен: cli.py запускается инструментом Bash из
        # bash-блока скилла, TTY нет, и input() либо повиснет, либо бросит
        # EOFError. Тот же приём, что у project db / track / project deploy:
        # печатает вопрос CLI, задаёт его падавану модель, пишет ответ ручка.
        print("")
        # Первое место, где падаван видит слово «Книга», — значит здесь
        # и глосса (D-04: слово остаётся, но объясняется при первой встрече).
        # Позднейшие упоминания её не повторяют: поясняют один раз. Имя —
        # из словаря сайта (CONTEXT.md, «Книга»): «Голокрон» там — десктопное
        # приложение, и звать так же браузерную книгу нельзя — падаван
        # внутри Голокрона читал бы «открыть Голокрон в браузере?».
        print(
            "Книга — книга твоего пути: то же, что ты проходишь в "
            "терминале, только страницами и в браузере."
        )
        print("Открывать её на входе в каждую главу?")
        print("  book yes — открывать вкладку самому")
        print("  book no — не открывать, зайду по ссылке сам")
    if data.get("book_open") is True:
        _open_in_browser(_book_url(data, act))
    return 0


def _maybe_close_act(state, act, state_path):
    """Закрыть акт, если все его квесты закрыты, и объявить новый ранг.

    Отдельной команды «закрыть акт» нет намеренно: падаван не должен иметь
    возможности забыть её выполнить и застрять перед следующим актом.
    Акт закрывается тем же действием, которым закрыт последний квест.
    """
    entry = (state.get("acts") or {}).get(str(act)) or {}
    if entry.get("status") == ranks.STATUS_DONE:
        return False
    try:
        if not acts.all_closed(state, act, acts.branch_of(state, act)):
            return False
    except acts.TrackRequiredError:
        # Без трека состав ветвящегося акта неизвестен, поэтому «все квесты
        # закрыты» недоказуемо — акт не закрываем. Клауза выписана отдельно
        # от UnknownActError не ради другого поведения (оно то же), а чтобы
        # отказ был решением, а не побочным эффектом наследования. Сегодня
        # сюда не дойти — _quest_kind отказывает раньше.
        return False
    except acts.DeployRequiredError:
        # То же правило, что для трека: без названного пути состав акта
        # неизвестен, «все квесты закрыты» недоказуемо — акт не закрываем.
        return False
    except acts.UnknownActError:
        return False
    ranks.close_act(state, act)
    # Хэш CLAUDE.md на момент закрытия акта: босс следующего акта сверяется
    # с ним, доказывая, что внешняя память жила, а не лежала мёртвым грузом.
    project_path = (state.get("project") or {}).get("path")
    if project_path:
        entry = state["acts"][str(act)]
        entry["claude_md_sha"] = _claude_md_sha(project_path)
    st.save(state, state_path)
    info = ranks.ACTS[act]
    print("")
    print("Акт {}. {} — закрыт.".format(act, info["title"]))
    # Объявляем ранг из состояния, а не «ранг за этот акт»: ранг считается по
    # непрерывной цепочке закрытых актов, и при пропущенном предыдущем акте
    # эти два значения расходятся. Игра не должна называть ранг, которого нет.
    rank = state.get("rank", st.RANK_YOUNGLING)
    print("Новый ранг: {}.".format(ranks.RANK_TITLES.get(rank, rank)))
    if act == ranks.FINAL_ACT:
        # Последний играбельный акт закрыт — это и есть конец игры. Молчание
        # здесь читалось бы как «игра сломалась»: падаван закрыл акт, дальше
        # тишина, и непонятно, кончилось или оборвалось.
        print("")
        print("Это конец игры — той, что бесплатна и открыта целиком.")
        print("Забери, что унёс: finale — карточка ранга, и scroll — Свиток в твой проект.")
    return True


def _act_started(state, act):
    """Акт начат, если запись о нём есть.

    Проверяется существование записи, а не статус: перепройти проверку в
    закрытом акте нормально, а закрыть Акт 2, ни разу не войдя в Акт 1, — нет.
    """
    return str(act) in (state.get("acts") or {})


def _quest_kind(act, quest_id, branch=None):
    """Вернуть (вид квеста, None) или (None, объяснение для падавана).

    Вид берётся из реестра акта, а не из наличия файла проверки: опечатка в
    имени квеста не должна выглядеть как «квест без автопроверки», иначе её
    можно закрыть подтверждением и получить вечный фальшивый прогресс.
    """
    try:
        allowed = acts.quest_ids(act, branch)
    except acts.TrackRequiredError:
        # Ловится раньше UnknownActError: она её родитель, и в обратном
        # порядке падаван услышал бы «квестов нет» вместо «выбери трек».
        return None, (
            "Состав Акта {} зависит от трека. Выбери трек: "
            "track craftsman или track founder.".format(act)
        )
    except acts.DeployRequiredError:
        return None, (
            "Состав Акта {} зависит от пути деплоя. Назови его: "
            "project deploy managed или project deploy vps.".format(act)
        )
    except acts.UnknownActError:
        return None, (
            "Квесты Акта {} ещё не завезены в игру — проходить пока нечего.".format(act)
        )
    if quest_id not in allowed:
        return None, (
            "В Акте {} нет квеста {}. Доступные сейчас квесты: {}.".format(
                act, quest_id, ", ".join(allowed)
            )
        )
    return acts.quest_kind(act, quest_id), None


def _claude_md_sha(project_dir):
    """git hash-object CLAUDE.md — не sha256: git гарантирован на машине,
    а sha256sum на macOS отсутствует (там shasum), и check.sh считает
    тот же хэш без платформенных ветвлений.
    """
    claude_md = Path(project_dir) / "CLAUDE.md"
    if not claude_md.is_file():
        return ""
    try:
        done = subprocess.run(
            ["git", "hash-object", "CLAUDE.md"],
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if done.returncode != 0:
        return ""
    return done.stdout.strip()


def _env_for(data, act):
    """Окружение check.sh. Ключ без значения не ставится вовсе: скрипт
    отличает «не назван порт» (jc_bail, попытка не в счёт) от «назван
    неверно» (провал проверки).
    """
    env = {}
    project = data.get("project") or {}
    has_db = project.get("has_db")
    if has_db is True:
        env["JEDICODER_HAS_DB"] = "yes"
    elif has_db is False:
        env["JEDICODER_HAS_DB"] = "no"
    port = project.get("port")
    if isinstance(port, int) and 1 <= port <= 65535:
        env["JEDICODER_PORT"] = str(port)
    alias = project.get("ssh_alias")
    # Ведущий «-» отсекается и здесь, а не только в ручке: state.json
    # правится руками, а алиас уходит аргументом в ssh.
    if isinstance(alias, str) and alias and not alias.startswith("-"):
        env["JEDICODER_SSH_ALIAS"] = alias
    prev = (data.get("acts") or {}).get(str(act - 1)) or {}
    sha = prev.get("claude_md_sha")
    if isinstance(sha, str) and sha:
        env["JEDICODER_PREV_CLAUDE_MD_SHA"] = sha
    url = project.get("url")
    # Хвостовой / срезается: скрипты клеят к URL пути («$URL/health»).
    if _valid_link(url):
        env["JEDICODER_URL"] = url.rstrip("/")
    service = project.get("service")
    # Тот же allowlist, что в ручке: state.json правится руками.
    if _valid_service(service):
        env["JEDICODER_SERVICE"] = service
    post = project.get("post_url")
    if _valid_link(post):
        env["JEDICODER_POST_URL"] = post
    deploy = project.get("deploy_path")
    if deploy in acts.DEPLOYS:
        env["JEDICODER_DEPLOY_PATH"] = deploy
    return env


def _cmd_check(args, state_path, content_root, quests_root):
    if len(args) < 2:
        print("Укажи акт и квест: check 2 04-git-init [путь-к-проекту]")
        return 1
    data = _load(state_path)
    try:
        act = _parse_act(args[0])
    except ValueError as exc:
        print(str(exc))
        return 1
    if act not in ranks.ACTS:
        print("нет акта {}".format(act))
        return 1
    if not _act_started(data, act):
        print(
            "Акт {} ещё не начат. Войди в него: enter {}.".format(act, act)
        )
        return 1
    quest_id = args[1]
    kind, problem = _quest_kind(act, quest_id, acts.branch_of(data, act))
    if problem is not None:
        print(problem)
        return 1
    if kind == quests.KIND_ACK:
        print(
            "У квеста {} нет автоматической проверки. Подтверди его командой "
            "ack {} {}.".format(quest_id, act, quest_id)
        )
        return 1
    project_dir = Path(args[2]) if len(args) > 2 else Path(
        (data.get("project") or {}).get("path") or "."
    )
    if not project_dir.is_dir():
        print("Не найдена папка проекта: {}".format(project_dir))
        return 1

    try:
        result = quests.run_check(
            quests_root, ranks.ACTS[act]["slug"], quest_id, project_dir,
            env_extra=_env_for(data, act),
        )
    except quests.QuestError as exc:
        print("Проверка сломана, это баг игры: {}".format(exc))
        return 1
    except subprocess.TimeoutExpired:
        # Контроллерская доработка: поздние акты гоняют ssh/curl, которые
        # умеют висеть. Падаван должен увидеть понятное русское объяснение,
        # а не traceback, и попытка не должна засчитаться — это не его вина.
        print("Проверка выполнялась слишком долго и была прервана. Не смог проверить.")
        print("Попытка не засчитана — это не твоя ошибка.")
        return 1

    if result.kind == quests.KIND_ACK:
        # Реестр обещал скрипт, а файла нет: сборка плагина битая.
        print(
            "Проверка сломана, это баг игры: не найден файл проверки квеста "
            "{}.".format(quest_id)
        )
        return 1

    quests.record_attempt(data, act, quest_id, result)
    st.save(data, state_path)

    if quests.cannot_check(result):
        detail = result.stderr or "проверка завершилась с кодом {}".format(
            result.exit_code
        )
        print("Не смог проверить: {}".format(detail))
        print("Попытка не засчитана — это не твоя ошибка.")
        return 1

    if result.ok:
        print("Квест {} закрыт.".format(quest_id))
        for check in result.checks:
            print("  [x] {}".format(check.get("label", check.get("id"))))
        _maybe_close_act(data, act, state_path)
        return 0

    print("Квест {} пока не закрыт. Не сошлось:".format(quest_id))
    for check in quests.failed_checks(result):
        print("  [ ] {}".format(check.get("label", check.get("id"))))
        hint = check.get("hint")
        if hint:
            print("      {}".format(hint))
    if quests.loop_warning(data, act, quest_id):
        print("")
        print(
            "Третья попытка — стоп. Дальше по кругу: откатись на рабочий "
            "коммит, начни новый чат, дай ошибку целиком и попроси сначала "
            "объяснить причину, а не чинить."
        )
    return 1


def _cmd_ack(args, state_path, content_root, quests_root):
    if len(args) < 2:
        print("Укажи акт и квест: ack 2 06-pipeline")
        return 1
    data = _load(state_path)
    try:
        act = _parse_act(args[0])
    except ValueError as exc:
        print(str(exc))
        return 1
    if act not in ranks.ACTS:
        print("нет акта {}".format(act))
        return 1
    if not _act_started(data, act):
        print(
            "Акт {} ещё не начат. Войди в него: enter {}.".format(act, act)
        )
        return 1
    quest_id = args[1]
    kind, problem = _quest_kind(act, quest_id, acts.branch_of(data, act))
    if problem is not None:
        print(problem)
        return 1
    if kind == quests.KIND_SCRIPT:
        # Центральный инвариант движка: исход скриптового квеста решает
        # exit-код проверки, а не мнение модели. Подтверждение здесь выдало
        # бы ранг за непроверенную работу — в том числе за защиту секретов.
        print(
            "У квеста {} есть автоматическая проверка. Подтвердить его нельзя — "
            "запусти check {} {}.".format(quest_id, act, quest_id)
        )
        return 1
    quests.acknowledge(data, act, quest_id)
    st.save(data, state_path)
    print("Квест {} подтверждён.".format(quest_id))
    _maybe_close_act(data, act, state_path)
    return 0


def _valid_link(value):
    """Ссылка для состояния: http(s), без пробельных символов, непустой хвост."""
    if not isinstance(value, str) or any(ch.isspace() for ch in value):
        return False
    for scheme in ("http://", "https://"):
        if value.startswith(scheme) and len(value) > len(scheme):
            return True
    return False


# Символы, из которых состоит имя systemd-юнита. Строгий allowlist, а не
# чёрный список: значение уходит в командную строку, которую перепарсит
# удалённый shell, — метасимволы ($(), `;`, IFS-трюки) не должны доехать
# туда ни из ручки, ни из правленного руками state.json.
_SERVICE_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.@:-"
)


def _valid_service(value):
    return (
        isinstance(value, str) and value != ""
        and not value.startswith("-")
        and all(ch in _SERVICE_CHARS for ch in value)
    )


def _recipes(content_root):
    """Рецепты из контент-ядра. Отказ чтения — пустой список: игра обязана
    идти дальше без рецептов, а не падать на них трейсбеком."""
    try:
        return list(content.load_recipes(content_root))
    except (OSError, UnicodeDecodeError, content.ContentError,
            frontmatter.FrontmatterError):
        return []


def _recipe_names(content_root):
    return [item.recipe for item in _recipes(content_root)]


def _recipe_by_name(content_root, name):
    for item in _recipes(content_root):
        if item.recipe == name:
            return item
    return None


def _cmd_recipe(args, state_path, content_root, quests_root):
    """Рецепт по типу продукта: стек, грабли, что проверить.

    Рецепты лежали в контент-ядре с самого начала, линтер их валидировал,
    тесты прибивали состав — и показать их падавану было нечем (прогон
    падаваном 2026-09-10). Квест 01 Акта 2 при этом велит «выбрать стек по
    рецепту своего типа продукта».

    Без аргумента — рецепт выбранного типа, а если тип не выбран, список
    того, из чего выбирать: падаван решает, глядя на три названия, а не
    вслепую. С именем — любой рецепт, и выбор при этом не меняется:
    посмотреть чужой можно, не назначая его себе.
    """
    recipes = _recipes(content_root)
    if not recipes:
        print("Рецепты не читаются — похоже, плагин установлен не полностью.")
        return 1
    name = args[0] if args else (_load(state_path).get("project") or {}).get("type")
    if not name:
        print("Тип продукта не выбран. Вот из чего выбирают:")
        for item in recipes:
            print("  {} — {} (деплой: {})".format(item.recipe, item.title, item.deploy_path))
        print("")
        print("Назови свой: project type <имя>. Посмотреть чужой: recipe <имя>.")
        return 0
    item = _recipe_by_name(content_root, name)
    if item is None:
        print("Нет рецепта {!r}. Есть: {}.".format(name, ", ".join(r.recipe for r in recipes)))
        return 1
    print("{} ({})".format(item.title, item.recipe))
    print("Стек: {}".format(", ".join(item.stack)))
    print("Путь деплоя: {}".format(item.deploy_path))
    print("")
    print(_readable(item.body))
    return 0


def _readable(body):
    """Тело контента без служебных строк.

    В рецептах стоят пометки для линтера вида `<!-- lint:novelty-ok: … -->` —
    они объясняют, почему раннее слово здесь допустимо, и адресованы автору,
    а не падавану. Печатать их человеку — то же, что показать ему изнанку
    декорации.
    """
    lines = [line for line in body.strip().split("\n")
             if not line.strip().startswith("<!-- lint:")]
    # Пустая строка, оставшаяся от снятой пометки, не должна разрывать текст.
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines).strip()


def _cmd_project(args, state_path, content_root, quests_root):
    data = _load(state_path)
    if not args:
        project = data.get("project") or {}
        path = project.get("path")
        has_db = project.get("has_db")
        port = project.get("port")
        lines = ["Проект:"]
        if path:
            lines.append("  Папка: {}".format(path))
        else:
            lines.append("  Папка: не установлена")
        if has_db is True:
            lines.append("  База данных: да")
        elif has_db is False:
            lines.append("  База данных: нет")
        else:
            lines.append("  База данных: неизвестно")
        if port:
            lines.append("  Порт: {}".format(port))
        else:
            lines.append("  Порт: не назван")
        kind = project.get("type")
        item = _recipe_by_name(content_root, kind) if kind else None
        if kind:
            lines.append("  Тип продукта: {}".format(item.title if item else kind))
        else:
            lines.append("  Тип продукта: не назван")
        deploy = project.get("deploy_path")
        if deploy:
            lines.append("  Путь деплоя: {}".format(deploy))
        elif item is not None and item.deploy_path:
            # Рецепт уже назвал путь, а «не назван» рядом читалось как
            # противоречие (живой прогон 2026-09-11). Выбор остаётся за
            # падаваном: рецепт советует, ручка записывает.
            lines.append(
                "  Путь деплоя: не назван — рецепт «{}» ждёт {}: "
                "project deploy {}".format(item.title, item.deploy_path, item.deploy_path)
            )
        else:
            lines.append("  Путь деплоя: не назван")
        alias = project.get("ssh_alias")
        if alias:
            lines.append("  SSH-алиас: {}".format(alias))
        url = project.get("url")
        if url:
            lines.append("  URL продукта: {}".format(url))
        else:
            lines.append("  URL продукта: не назван")
        service = project.get("service")
        if service:
            lines.append("  Сервис: {}".format(service))
        post = project.get("post_url")
        if post:
            lines.append("  Публикация: {}".format(post))
        print("\n".join(lines))
        return 0
    if args[0] == "path":
        if len(args) < 2:
            print("Укажи путь: project path /путь/к/проекту")
            return 1
        # resolve() обязателен: относительный путь («.») позже разрешится от
        # каталога, из которого запущен CLI, а не от проекта. Падаван получил
        # бы «репозиторий не инициализирован» на инициализированном проекте.
        path = Path(args[1]).resolve()
        if not path.is_dir():
            print("Не найдена папка: {}".format(args[1]))
            return 1
        data["project"] = data.get("project") or {}
        data["project"]["path"] = str(path)
        st.save(data, state_path)
        print("Папка проекта установлена: {}".format(path))
        return 0
    if args[0] == "db":
        if len(args) < 2:
            print("Укажи ответ: project db yes|no")
            return 1
        if args[1] == "yes":
            data["project"] = data.get("project") or {}
            data["project"]["has_db"] = True
            st.save(data, state_path)
            print("База данных: да")
            return 0
        elif args[1] == "no":
            data["project"] = data.get("project") or {}
            data["project"]["has_db"] = False
            st.save(data, state_path)
            print("База данных: нет")
            return 0
        else:
            print("Укажи 'yes' или 'no', а не {!r}".format(args[1]))
            return 1
    if args[0] == "port":
        if len(args) < 2:
            print("Укажи порт: project port 8000")
            return 1
        try:
            port = int(args[1])
        except ValueError:
            port = -1
        if not (1 <= port <= 65535):
            print("Порт — целое от 1 до 65535, а не {!r}.".format(args[1]))
            return 1
        data["project"] = data.get("project") or {}
        data["project"]["port"] = port
        st.save(data, state_path)
        print("Порт проекта: {}".format(port))
        return 0
    if args[0] == "type":
        names = _recipe_names(content_root)
        if len(args) < 2:
            print("Укажи тип продукта: project type {}".format("|".join(names) or "<имя>"))
            return 1
        item = _recipe_by_name(content_root, args[1])
        if item is None:
            # Состояние не трогаем: мусор не должен затирать выбор.
            print(
                "Не знаю тип продукта {!r}. Допустимые: {}.".format(
                    args[1], ", ".join(names)
                )
            )
            return 1
        data["project"] = data.get("project") or {}
        data["project"]["type"] = item.recipe
        # Паспорт несёт тип в контракт: без него модель получала «Тип
        # продукта: unknown» и выбирала стек наугад.
        data["passport"] = data.get("passport") or {}
        data["passport"]["product_type"] = item.recipe
        st.save(data, state_path)
        print("Тип продукта: {} ({}).".format(item.title, item.recipe))
        print("Стек рецепта: {}".format(", ".join(item.stack)))
        print("Путь деплоя, которого он ждёт: {}".format(item.deploy_path))
        print("Сам рецепт — команда recipe: стек, грабли и что проверить.")
        return 0
    if args[0] == "deploy":
        if len(args) < 2:
            print("Укажи путь: project deploy managed|vps")
            return 1
        choice = args[1]
        if choice not in acts.DEPLOYS:
            # Состояние не трогаем: мусор не должен затирать выбор.
            print(
                "Не знаю пути деплоя {!r}. Допустимые: {}.".format(
                    choice, ", ".join(acts.DEPLOYS)
                )
            )
            return 1
        data["project"] = data.get("project") or {}
        data["project"]["deploy_path"] = choice
        st.save(data, state_path)
        print("Путь деплоя: {}.".format(choice))
        return 0
    if args[0] == "ssh":
        if len(args) < 2:
            print("Укажи алиас из ~/.ssh/config: project ssh <алиас>")
            return 1
        alias = args[1]
        # Ведущий «-» запрещён отдельно от прочего мусора: алиас уходит
        # аргументом в ssh, и «-oProxyCommand=…» стал бы опцией — инъекция
        # команды через состояние.
        if (not alias or alias.startswith("-")
                or " " in alias or "/" in alias):
            print(
                "Алиас — одно слово без пробелов, '/' и ведущего '-', "
                "а не {!r}.".format(alias)
            )
            return 1
        data["project"] = data.get("project") or {}
        data["project"]["ssh_alias"] = alias
        st.save(data, state_path)
        print("SSH-алиас сервера: {}.".format(alias))
        return 0
    if args[0] == "url":
        if len(args) < 2 or not _valid_link(args[1]):
            print(
                "Укажи адрес продукта: project url https://мой-домен — "
                "http(s) и без пробелов."
            )
            return 1
        data["project"] = data.get("project") or {}
        data["project"]["url"] = args[1]
        st.enqueue_event(data, "product_deployed", payload={"url": args[1]})
        st.save(data, state_path)
        print("URL продукта: {}".format(args[1]))
        return 0
    if args[0] == "service":
        if len(args) < 2:
            print("Укажи systemd-юнит: project service myapp")
            return 1
        service = args[1]
        if not _valid_service(service):
            print(
                "Юнит — латиница, цифры и символы _.@:- без пробелов и "
                "ведущего '-', а не {!r}.".format(service)
            )
            return 1
        data["project"] = data.get("project") or {}
        data["project"]["service"] = service
        st.save(data, state_path)
        print("Сервис: {}".format(service))
        return 0
    if args[0] == "post":
        if len(args) < 2 or not _valid_link(args[1]):
            print(
                "Укажи ссылку на публикацию: project post https://… — "
                "http(s) и без пробелов."
            )
            return 1
        data["project"] = data.get("project") or {}
        data["project"]["post_url"] = args[1]
        st.enqueue_event(data, "product_deployed", payload={"post_url": args[1]})
        st.save(data, state_path)
        print("Публикация: {}".format(args[1]))
        return 0
    print("Неизвестная подкоманда 'project {}'. Используй: project [path <путь>|type <тип>|db yes|no|port <номер>|deploy managed|vps|ssh <алиас>|url <адрес>|service <юнит>|post <ссылка>]".format(
        args[0]
    ))
    return 1


def _cmd_track(args, state_path, content_root, quests_root):
    data = _load(state_path)
    if not args:
        track = acts.track_of(data)
        if track is None:
            print("Трек: не выбран.")
            print(
                "Выбери: track craftsman — делаю для себя и близких; "
                "track founder — ищу пользователей."
            )
        else:
            print("Трек: {}.".format(track))
        return 0
    choice = args[0]
    if choice not in acts.TRACKS:
        # Состояние не трогаем: мусорное значение не должно затирать выбор.
        print(
            "Не знаю трек {!r}. Допустимые: {}.".format(
                choice, ", ".join(acts.TRACKS)
            )
        )
        return 1
    data["passport"] = data.get("passport") or {}
    data["passport"]["track"] = choice
    st.enqueue_event(data, "linked", payload=_passport_snapshot(data))
    st.save(data, state_path)
    print("Трек: {}.".format(choice))
    print("Сменить можно в любой момент — уже пройденное при этом не пропадает.")
    return 0


def _cmd_artifact(args, state_path, content_root, quests_root):
    """Замок артефакта-скилла: исход решает exit-код, а не чтение текста.

    Скилл артефакта зовёт эту команду первым делом и на код 1 отвечает в
    характере, не выполняя тело.
    """
    if not args:
        print("Укажи артефакт: artifact brainstorm")
        return 1
    name = args[0]
    known = {info["artifact"] for info in ranks.ACTS.values()}
    if name not in known:
        print(
            "Нет такого артефакта: {}. Есть: {}.".format(
                name, ", ".join(sorted(known))
            )
        )
        return 1
    data = _load(state_path)
    if ranks.artifact_unlocked(data, name):
        print("Артефакт {} открыт.".format(name))
        return 0
    owner = next(
        number for number, info in sorted(ranks.ACTS.items())
        if info["artifact"] == name
    )
    print(
        "Артефакт {} ещё не собран — он выдаётся на входе в Акт {}.".format(
            name, owner
        )
    )
    return 1


# --- Свиток ----------------------------------------------------------------
#
# Единственная команда игры, которая пишет файлы в проект падавана. Ни хук,
# ни проверка, ни вход в акт этого не делают и делать не будут (ADR-0009 в
# репозитории сайта): запрет «проверка не мутирует проект падавана» остаётся
# в силе целиком, а у команды, набранной человеком, его никогда и не было.


def _act_pages(content_root):
    """Катсцены актов — только ради подписей квестов, и молча без них.

    Читающая команда не имеет права умереть от неполной поставки: без
    катсцен в Разборе останутся идентификаторы квестов, и это хуже
    подписей, но лучше трейсбека. Выдача Свитка на том же месте
    отказывается вслух — там речь о файлах в чужом проекте, и молчать
    нельзя.
    """
    try:
        return content.load_acts(content_root)
    except (OSError, content.ContentError):
        return ()


def _debrief_facts(data, content_root, today=None):
    """Страница фактов Разбора — та же, что ляжет в файл Свитка."""
    today = today or st.today_utc()
    return scroll.debrief_page(
        debrief.facts(data, today=today), acts=_act_pages(content_root),
        today=today,
    )


DEBRIEF_USAGE = (
    "Используй: debrief — факты; debrief write — текст поверх них со stdin; "
    "debrief clear — вернуться к молчанию."
)


def _stdin_is_terminal():
    """Ждёт ли stdin, что человек наберёт текст руками. Не знаем — читаем."""
    try:
        return bool(sys.stdin.isatty())
    except (AttributeError, ValueError):
        return False


def _stdin_text():
    """Текст со stdin, прочитанный байтами и раскодированный самим CLI.

    Через `.buffer`, а не `sys.stdin.read()`: у падавана локаль — лотерея, а
    разбор Магистра целиком кириллический. Стандартный поток, открытый под
    локалью ASCII, уронил бы команду на первой русской букве. Ошибочный байт
    заменяем, а не роняем: половина текста в файле лучше, чем трейсбек
    вместо него.
    """
    stream = getattr(sys.stdin, "buffer", None)
    if stream is None:
        # Поток подменён (тесты, вызов из питона) — читаем как есть.
        return sys.stdin.read()
    return stream.read().decode("utf-8", "replace")


def _cmd_debrief(args, state_path, content_root, quests_root):
    """Два приёма Разбора: прочитать факты и положить текст поверх них.

    Движок модель не зовёт и звать не может — здесь нет ни сети, ни ключей.
    Поэтому текст Магистра приходит в Свиток не изнутри, а через эту дверь:
    сначала он читает готовые факты (`debrief`), потом отдаёт написанное
    поверх них (`debrief write`, текст со stdin). Между приёмами написанное
    лежит в сохранении, и в файл его кладёт уже выдача Свитка.

    Текст берётся со stdin, а не аргументом: в разборе переводы строк, а
    аргумент с ними — это цитирование в bash, то есть способ потерять
    половину абзаца на первой же кавычке.
    """
    verb = args[0] if args else ""
    if verb not in ("", "write", "clear") or len(args) > 1:
        # Хвост проглатывать нельзя: `debrief write razbor.md` выглядит
        # рабочей строкой, а текст читался бы всё равно со stdin.
        print("Не знаю команду 'debrief {}'. {}".format(
            " ".join(args), DEBRIEF_USAGE
        ))
        return 1
    if not verb:
        print(_debrief_facts(_load(state_path), content_root))
        return 0
    if verb == "clear":
        with st.update_state(state_path) as fresh:
            fresh["debrief"] = {"text": "", "facts": ""}
        print("Разбор стёрт. Свиток выдастся с фактами и без него.")
        return 0
    if _stdin_is_terminal():
        # Перенаправления нет — чтение stdin повисло бы молча, и повисло бы
        # у падавана в терминале на команде, которую набрала модель.
        print("Текст Разбора подаётся на stdin, а не аргументом:")
        print("  ... cli.py debrief write <<'RAZBOR'")
        return 1
    text = _stdin_text().strip()
    if not text:
        # Пустой ввод — это «текста не приехало», а не «сотри написанное».
        # Строка `… debrief write` без heredoc выглядит рабочей, и молчаливое
        # обнуление кодом 0 не заметил бы никто.
        print("На stdin пусто — записывать нечего, прежний Разбор не тронут.")
        print("Стереть его нарочно: debrief clear")
        return 1
    with st.update_state(state_path) as fresh:
        # Отпечаток снимается с той же страницы, что прочитал Магистр, и
        # снимается ЗДЕСЬ, под замком: между чтением фактов и записью текста
        # падаван мог закрыть квест, и тогда текст отвечает уже не тем числам.
        fresh["debrief"] = {
            "text": text,
            "facts": scroll.fingerprint(_debrief_facts(fresh, content_root)),
        }
    print("Разбор записан: {} строк.".format(len(text.split("\n"))))
    print("В Свиток он ляжет под заголовком «{}» — командой scroll.".format(
        scroll.DEBRIEF_HEADING.lstrip("# ")
    ))
    return 0


def _debrief_text(data):
    """Текст Магистра из сохранения, как есть; чего не разобрали — молчание."""
    written = data.get("debrief")
    if not isinstance(written, dict):
        return ""
    text = written.get("text")
    return text.strip() if isinstance(text, str) else ""


def _debrief_for(data, facts_page):
    """Текст Магистра, если он написан поверх ЭТИХ фактов. Иначе молчание.

    Страница фактов меняется от каждого закрытого квеста и от каждого
    прожитого дня, а текст лежит в сохранении и ждёт выдачи. Пустить
    вчерашний текст под сегодняшние числа значило бы назвать число иначе —
    ровно то, что запрещает ADR-0010, и запрещает не по стилю: падаван
    проверяет каждое число Свитка по своему же сохранению.

    Молчание тут законно (Свиток выдаётся с фактами и без разбора), а сам
    текст никуда не девается — он остаётся в сохранении, и Магистру есть
    что переписать.
    """
    text = _debrief_text(data)
    if not text:
        return ""
    written = data.get("debrief") or {}
    return text if written.get("facts") == scroll.fingerprint(facts_page) else ""


def _roadmap_page(facts, content_root):
    """Дорожная карта под трек падавана — из контента, не от модели.

    Три шага «довести продукт до людей» модель не пишет вовсе: они зависят
    от трека и от того, есть ли у продукта адрес, а не от того, как прошло
    прохождение. Значит это контент, и тогда карта одинаково хороша у всех
    и проверяется составом, а не вкусом.

    Трек не выбран — карта общая (content.TRACK_ANY). Дыра вместо карты не
    заметна никому: Свиток собрался бы на файл короче и промолчал.

    Раздел не читается (плагин установлен не целиком) — молчание, а не
    отказ: карта часть Свитка, а не его условие, и факты падаван унесёт в
    любом случае. Состав раздела стережёт линтер до поставки.

    Трек и адрес берутся из фактов, а не из сохранения второй раз: адрес
    печатается в Свитке дважды — в Разборе и здесь, — и добывать его двумя
    способами значило бы завести второй источник правды об одном числе.
    """
    try:
        cards = content.roadmaps_by_track(content_root)
    except (OSError, content.ContentError):
        return ""
    card = cards.get(facts.get("track")) or cards.get(content.TRACK_ANY)
    if card is None:
        return ""
    return scroll.roadmap_page(card, facts.get("product_url"))


def _scroll_parts(data, content_root, facts=None, facts_page=None,
                  commits=None):
    """Тексты Свитка, которых движок не пишет: см. scroll.PARTS.

    Карточку ранга пишет финал — тем же текстом, что печатает в терминале
    (render_rank_card); коммиты для неё считает git в папке проекта, поэтому
    их передаёт вызывающий: эта функция работает под файловой блокировкой
    состояния, а держать замок на время чужого процесса нельзя.

    Разбор Магистра лежит в сохранении: его положила туда команда
    `debrief write`, и это единственный путь текста модели в Свиток —
    вызвать её изнутри движок не может. В файл он идёт, только если написан
    поверх этих самых фактов (`facts_page`). Дорожная карта приходит с
    другой стороны, из контента: её три шага модель не пишет вовсе.

    Молчание здесь законно: Свиток выдаётся с фактами и без разбора
    (ADR-0010). Обратное невозможно, поэтому сами факты собирает не она.
    """
    # Ничего не передали — соберём сами. Путь запасной: за одну выдачу часы
    # читаются ровно один раз, и собранная здесь заново страница фактов может
    # не совпасть с той, поверх которой писал Магистр. Тогда разбор промолчит,
    # и это законно (ADR-0010), а карточка выйдет всё равно: одна карточка
    # честнее упавшей команды.
    if facts is None:
        facts = debrief.facts(data)
    if facts_page is None:
        facts_page = scroll.debrief_page(
            facts, acts=_act_pages(content_root), today=st.today_utc()
        )
    if commits is None:
        commits = _project_commit_count(data)
    parts = {scroll.PART_RANK_CARD: render_rank_card(facts, commits=commits)}
    text = _debrief_for(data, facts_page)
    if text:
        parts[scroll.PART_DEBRIEF] = text
    card = _roadmap_page(facts, content_root)
    if card:
        parts[scroll.PART_ROADMAP] = card
    return parts


def _scroll_instructions(content_root, data):
    """Инструкции тех артефактов, что у падавана открыты.

    Отбор здесь, а не в сборке: «отдаёт то, что открыто» — вопрос к
    сохранению, а сборка о сохранении не знает вовсе. Артефакт без замка
    (goal) открыт с первого дня, поэтому он не в artifacts_for.
    """
    unlocked = list(ranks.artifacts_for(data))
    for name in ranks.UNLOCKED_ARTIFACTS:
        if name not in unlocked:
            unlocked.append(name)
    known = content.instructions_by_artifact(content_root)
    return dict(
        (name, known[name]) for name in unlocked if name in known
    )


SCROLL_BUCKETS = (
    (scroll.ACTION_CREATED, "Добавлено:"),
    (scroll.ACTION_UPDATED, "Обновлено:"),
    (scroll.ACTION_UNCHANGED, "Без изменений:"),
    (scroll.ACTION_KEPT, "Оставлено как есть — в файле твоя правка:"),
    (scroll.ACTION_FAILED, "Не удалось записать:"),
)


def _scroll_line(row):
    """Строка отчёта про один файл: имя, а у оставленного — куда лёг свежий."""
    if row["action"] != scroll.ACTION_KEPT:
        return "  {}".format(row["name"])
    if row["written"]:
        return "  {} → {}".format(row["name"], row["written"])
    return "  {} — положить свежий рядом не вышло".format(row["name"])


def _scroll_undelivered(report):
    """Файлы, которых у падавана в итоге нет: записать не вышло вовсе."""
    return [
        row for row in report
        if row["action"] == scroll.ACTION_FAILED
        or (row["action"] == scroll.ACTION_KEPT and not row["written"])
    ]


def render_scroll(title, directory, report):
    """Что команда печатает после выдачи. Чистая функция от отчёта."""
    lines = ["{}: {}".format(title, directory), ""]
    for action, header in SCROLL_BUCKETS:
        rows = [row for row in report if row["action"] == action]
        if not rows:
            continue
        lines.append(header)
        lines += [_scroll_line(row) for row in rows]
        lines.append("")
    if any(row["action"] == scroll.ACTION_KEPT for row in report):
        lines.append(
            "Файл с твоей правкой не тронут: свежий лёг рядом, с датой в имени."
        )
    lines.append("Начни с {} — там сказано, что где лежит.".format(
        scroll.INDEX_NAME
    ))
    return "\n".join(lines)


def _cmd_scroll(args, state_path, content_root, quests_root):
    """Выдать Свиток в проект падавана. Пишет только эта команда."""
    data = _load(state_path)
    path = _project_path(data)
    if path is None:
        # Те же слова, что на первом экране: один случай не должен
        # называться на двух экранах по-разному.
        print("Папка проекта не установлена — Свиток класть некуда.")
        print("Назови папку: project path <путь>")
        return 1
    if not Path(path).is_dir():
        print("Папка проекта не найдена: {}".format(path))
        print("Свиток класть некуда, ничего не создано.")
        print("Назови папку заново: project path <путь>")
        return 1
    try:
        instructions = _scroll_instructions(content_root, data)
        act_pages = content.load_acts(content_root)
    except (OSError, content.ContentError) as error:
        print("Не нашёл тексты Свитка: {}".format(error))
        print("Похоже, плагин установлен не целиком. Переустанови его.")
        return 1
    directory = scroll.directory_for(path)
    today = st.today_utc()
    # git читается ДО замка: у него свой таймаут в секундах, а блокировка
    # состояния берётся без таймаута вовсе — хук, подошедший в эту секунду,
    # ждал бы чужой процесс молча.
    commits = _project_commit_count(data)
    title, report, failure, stale = "", [], None, False
    # Читаем состояние и пишем отпечатки одним окном под файловой
    # блокировкой (долг №8): между сборкой и записью отпечатков хук может
    # начислить XP или очко Тёмной стороны, и save устаревшим снимком его
    # бы стёр. Диск внутри окна — намеренно: отпечатки в сохранении обязаны
    # описывать то, что в эту же минуту легло в папку.
    with st.update_state(state_path) as fresh:
        facts = debrief.facts(fresh, today=today)
        facts_page = scroll.debrief_page(facts, acts=act_pages, today=today)
        title = scroll.scroll_title(facts)
        parts = _scroll_parts(
            fresh, content_root, facts=facts, facts_page=facts_page,
            commits=commits,
        )
        stale = bool(_debrief_text(fresh)) and not parts.get(scroll.PART_DEBRIEF)
        files = scroll.build(
            facts, instructions, acts=act_pages, parts=parts, today=today,
        )
        try:
            report, prints = scroll.write(
                directory, files,
                (fresh.get("scroll") or {}).get("files") or {}, today,
            )
        except OSError as error:
            # Папку не создать (нет прав, файл вместо каталога). Сказать
            # словами и уйти: вслепую тут делать нечего.
            failure = error
        else:
            fresh["scroll"] = {"files": prints}
            # Событие для бота: через неделю после выдачи он пишет падавану
            # письмо, и узнать о выдаче ему больше неоткуда — Свиток лёг на
            # диск падавана, не на сервер. Только ранг и дата: ни путей, ни
            # содержимого — что лежит в чужой папке, бота не касается. Без
            # признака «уже объявлено», в отличие от финала: повторная выдача
            # — повторное событие, неделя отсчитывается от последней.
            st.enqueue_event(fresh, "scroll_issued", payload={
                "rank": ranks.rank_for(fresh),
                "date": today,
            })
    if failure is not None:
        print("Не смог создать папку {}: {}".format(directory, failure))
        return 1
    print(render_scroll(title, directory, report))
    if stale:
        # Текст не потерян — он лежит в сохранении и ждёт переписывания.
        # Сказать об этом обязательно: молчаливо выданный Свиток без Разбора
        # читался бы как «Магистр промолчал», а он не молчал.
        print()
        print("Разбор Магистра в Свиток не вошёл: он написан по другим "
              "числам.")
        print("Позови Магистра переписать его по сегодняшним — и выдай "
              "Свиток заново.")
    # Код 1, когда хоть один файл до падавана не доехал. Отчёт при этом
    # печатается целиком: остальное легло и никуда не денется, а нуль на
    # недоставленном файле читался бы как «всё на месте».
    return 1 if _scroll_undelivered(report) else 0


# --- Финал и карточка ранга -------------------------------------------------
#
# Карточка — трофей падавана, а не выписка: её же файлом уносит Свиток
# (scroll.PART_RANK_CARD), и читать её будут через месяцы, когда игры на
# машине уже нет. Поэтому она собирается ОДНОЙ функцией на оба места: два
# текста разошлись бы молча, и падаван увидел бы в терминале одно, а в своей
# папке другое.
#
# Числа приходят из debrief.facts и ниоткуда больше (ADR-0010 в репозитории
# сайта): здесь их произносят, а не пересчитывают. Исключение ровно одно и
# названо вслух — коммиты, их считает git в папке проекта, в сохранении их
# нет вовсе.


def _project_commit_count(data):
    path = (data.get("project") or {}).get("path")
    if not path:
        return None
    try:
        done = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=str(path), capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip() or None


#: Строка трофея по акту, которым кончилась игра. Отсылает к катсцене того
#: же акта — иначе финал поздравляет падавана с чужой победой.
TROPHY_LINES = {
    4: "Щит поставлен: ключи твои, сервер твой, и чужому в него не войти.",
    5: "Клинок собран, и он режет.",
}


def _is_master(facts):
    """Дошёл ли падаван до конца игры. Один предикат на три развилки.

    Сверяется с ranks.FINAL_RANK, а не с последним рангом реестра: пока Акт 5
    выключен (ranks.MUTED_ACTS), последний ранг реестра принадлежит акту, в
    который не войти, и ворота финала по нему не открылись бы никогда.
    Вернётся акт — вернётся и Мастер, без правки здесь.
    """
    rank = facts.get("rank")
    if rank not in ranks.RANKS:
        return False
    return ranks.RANKS.index(rank) >= ranks.RANKS.index(ranks.FINAL_RANK)


def _rank_name(facts):
    """Русское имя ранга из фактов. Та же цепочка, что у scroll.scroll_title."""
    rank = facts.get("rank")
    return facts.get("rank_title") or ranks.RANK_TITLES.get(rank) or rank


def _rank_card_title(facts):
    """«Карточка Мастера» — имя носит ранг владельца, как и у Свитка.

    Склонение берётся у Свитка (scroll.genitive), а не пишется здесь заново:
    второго списка имён рангов в игре нет и быть не должно — он разошёлся бы
    с ranks.RANK_TITLES молча, и падаван прочёл бы в карточке одно имя, а в
    имени Свитка другое.
    """
    title = _rank_name(facts)
    return "Карточка {}".format(scroll.genitive(title)) if title else "Карточка"


def _rank_card_numbers(facts, commits):
    """Числа карточки. Всё из фактов Разбора, кроме коммитов.

    Продукт и дни в пути печатаются, только если они есть: у беты прошлых
    версий нет даты входа в Акт 1, а ссылку на продукт падаван мог и не
    называть. Пустая строка «Дней в пути: —» была бы хуже отсутствующей —
    она читается как поломка там, где игра просто не знает.
    """
    lines = []
    url = facts.get("product_url")
    if url:
        lines.append("Продукт: {}".format(url))
    days = facts.get("days_in_path")
    if days is not None:
        lines.append("Дней в пути: {}".format(days))
    if commits is not None:
        lines.append("Коммитов: {}".format(commits))
    dark = facts.get("dark_side")
    dark = dark if isinstance(dark, dict) else {}
    return lines + [
        "Слов открыто: {}".format(facts.get("terms_unlocked") or 0),
        "XP: {}".format(facts.get("xp") or 0),
        "Тёмная сторона: {}".format(dark.get("points") or 0),
    ]


def render_rank_card(facts, commits=None):
    """Карточка ранга — трофей падавана. Чистая функция от фактов Разбора.

    Выдаётся на ЛЮБОМ ранге, а не одному Мастеру: Свиток тоже выдаётся всем,
    и до Мастера дойдут немногие. Разница между полной карточкой и карточкой
    середины пути — не в жалости, а в двух строках: Мастеру дописана дверь
    в финал, остальным сказано, что в карточку идёт только закрытое.

    Чего здесь нет намеренно: «почти получилось», «осталось совсем немного» и
    любого обещания, что падаван дойдёт. Игра судит по exit-коду проверки, и
    карточка говорит тем же голосом — про сделанное, а не про намерения.

    `commits` — единственное число мимо debrief: их считает git в папке
    проекта, в сохранении их нет. Не передали (git не ответил, папки нет) —
    строки просто не будет.
    """
    facts = facts if isinstance(facts, dict) else {}
    lines = ["=== {} ===".format(_rank_card_title(facts)), ""]
    if _is_master(facts):
        # Трофей — отсылка к катсцене того акта, которым игра кончилась.
        # «Клинок собран, и он режет» — про Акт 5, где продукт вышел к людям;
        # сказать это тому, кто до пятого не дошёл, значит поздравить его с
        # тем, чего не было. Пока акт выключен, финал — Щит, и трофей его.
        lines += [TROPHY_LINES.get(ranks.FINAL_ACT, TROPHY_LINES[4]), ""]
    done = facts.get("acts_completed") or []
    # Знаменатель — играбельные акты, а не весь реестр: пока Акт 5 выключен,
    # «3 из 5» назвало бы падавану дорогу, которой сейчас нет, и его законный
    # финал выглядел бы недоходом.
    lines.append("Закрыто актов: {} из {}.".format(len(done), len(ranks.playable_acts())))
    for number in done:
        title = (ranks.ACTS.get(number) or {}).get("title")
        lines.append(
            "  Акт {}. {}".format(number, title) if title
            else "  Акт {}".format(number)
        )
    lines.append("")
    lines += _rank_card_numbers(facts, commits)
    lines.append("")
    if _is_master(facts):
        lines += [
            "Кто вёл тебя всю игру и куда идти дальше — на странице финала:",
            _finale_url(),
        ]
    else:
        lines += [
            "В карточке только закрытое: незакрытый акт в неё не идёт ни",
            "авансом, ни округлением. Возьмёшь Свиток снова — она соберётся",
            "заново, по закрытому на тот день.",
        ]
    return "\n".join(lines)


def _scroll_folder():
    """Папка Свитка в словах падавана: «docs/jedicoder».

    Собирается из scroll.RELATIVE_DIR, а не набирается заново: имя папки
    падаван прочтёт в приглашении и пойдёт искать её глазами, и разойтись с
    тем, куда Свиток на самом деле ложится, оно не имеет права.
    """
    return "/".join(scroll.RELATIVE_DIR)


def _render_finale_locked(facts):
    """Финал тому, кто до Мастера ещё не дошёл.

    Говорит ровно две вещи: чего не хватает и что Свиток можно забрать уже
    сейчас. Карточки здесь нет намеренно — она лежит в Свитке, а печатать её
    в ответ на «финал» тому, у кого финала ещё не было, значит выдать за
    финал середину пути.
    """
    title = _rank_name(facts)
    playable = ranks.playable_acts()
    closed = [act for act in (facts.get("acts_completed") or []) if act in playable]
    lines = [
        "Финал ждёт {}. Твой ранг сейчас — {}, закрыто актов: {} из {}.".format(
            scroll.genitive(ranks.RANK_TITLES[ranks.FINAL_RANK]),
            title, len(closed), len(playable),
        ),
    ]
    nearest = _nearest_open_act(facts)
    if nearest is not None:
        lines.append("Ближайший незакрытый — Акт {} «{}».".format(*nearest))
    lines += [
        "",
        "Свиток можно забрать уже сейчас: он выдаётся на любом ранге и отдаёт",
        "то, что открыто, — инструкции артефактов, Разбор и твою карточку",
        "{}. Ляжет папкой {} в твой проект.".format(
            scroll.genitive(title), _scroll_folder()
        ),
        "  scroll",
    ]
    return "\n".join(lines)


def _nearest_open_act(facts):
    """Первый акт реестра, которого нет среди закрытых: (номер, название)."""
    done = set(facts.get("acts_completed") or [])
    for number in ranks.playable_acts():
        if number not in done:
            return number, ranks.ACTS[number]["title"]
    return None


def _render_finale_invite():
    """Приглашение забрать Свиток — тому, у кого финал уже случился."""
    return "\n".join([
        "Забери Свиток: он ляжет папкой {} в твой проект — инструкции".format(
            _scroll_folder()
        ),
        "артефактов рабочим языком, Разбор твоего прохождения и эта карточка",
        "отдельным файлом. Игру можно будет удалить, а Свиток останется.",
        "  scroll",
    ])


def _cmd_finale(args, state_path, content_root, quests_root):
    """Финал: карточка ранга, страница финала и приглашение забрать Свиток.

    Ранг берётся из фактов Разбора (ranks.rank_for), а не из поля сохранения:
    правило игры — ранг считается по закрытым актам, и у ворот финала оно
    должно быть тем же, каким его напечатает карточка.
    """
    data = _load(state_path)
    facts = debrief.facts(data)
    if not _is_master(facts):
        print(_render_finale_locked(facts))
        return 1
    # Карточка собирается до блокировки: коммиты считает git в чужой папке,
    # и держать замок состояния на время чужого процесса незачем.
    card = render_rank_card(facts, commits=_project_commit_count(data))
    if not data.get("finale_announced"):
        # update_state, а не save (долг №8): между чтением и записью хук мог
        # начислить XP или очко Тёмной стороны, и устаревший снимок стёр бы
        # их. Признак перечитывается под замком — второй терминал мог успеть
        # объявить финал, и второе событие боту не нужно.
        with st.update_state(state_path) as fresh:
            if not fresh.get("finale_announced"):
                fresh["finale_announced"] = True
                st.enqueue_event(fresh, "finale", payload={
                    # Ранг тем же реестром, что и ворота выше: поле
                    # сохранения здесь было бы вторым источником одного факта.
                    "rank": ranks.rank_for(fresh),
                    "xp": int(fresh.get("xp", 0)),
                })
    print(card)
    print("")
    print(_render_finale_invite())
    return 0


def _cmd_root(args, state_path, content_root, quests_root, plugin_root_path=None):
    marker = Path(plugin_root_path or st.PLUGIN_ROOT_PATH)
    if not marker.exists():
        print(
            "Корень плагина неизвестен. Перезапусти Claude Code — SessionStart "
            "запишет его сам."
        )
        return 1
    print(marker.read_text(encoding="utf-8").strip())
    return 0


_KEY_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)


def _valid_key(value):
    return 4 <= len(value) <= 64 and all(ch in _KEY_CHARS for ch in value)


def _passport_snapshot(data):
    """Снимок паспорта для бота потока — без путей и имён проектов.

    Приватность: это единственное, что уходит по сети про падавана, и в
    нём нет ничего, что раскрывало бы, над каким проектом он работает.
    """
    streak = data.get("streak") or {}
    first_try = data.get("first_try") or {}
    return {
        "padawan_id": data.get("padawan_id"),
        "track": (data.get("passport") or {}).get("track"),
        "rank": data.get("rank", st.RANK_YOUNGLING),
        "xp": int(data.get("xp", 0)),
        "dark_side": int(data.get("dark_side", 0)),
        "streak_current": int(streak.get("current", 0)),
        "streak_best": int(streak.get("best", 0)),
        "first_try_passed": int(first_try.get("passed", 0)),
        "first_try_attempted": int(first_try.get("attempted", 0)),
        "current_act": int(data.get("current_act", 1)),
        # Ось развилки Акта 4 — деплой, а не трек: без этого поля книга не
        # знает, какую из двух веток рисовать, и покажет чужой список
        # квестов. Значение managed|vps не раскрывает ничего о проекте
        # падавана, поэтому приватность снимка не страдает.
        "deploy_path": (data.get("project") or {}).get("deploy_path"),
    }


def _cmd_link(args, state_path, content_root, quests_root):
    if len(args) < 1 or not _valid_key(args[0]):
        print(
            "Укажи ключ из бота: link <ключ>. Ключ выдаёт команда /link "
            "в Telegram-боте потока."
        )
        return 1
    data = _load(state_path)
    data["link_key"] = args[0]
    st.enqueue_event(data, "linked", payload=_passport_snapshot(data))
    st.save(data, state_path)
    sent, dropped, remaining, status = sync.flush(state_path)
    if status == "unknown_key":
        # Ключ уже записан намеренно: падаван мог опечататься или взять
        # старый ключ после /newkey, и повторный `link <ключ>` должен
        # сработать без танцев — переписывать то же значение можно всегда.
        print(
            "Ключ записан, но бот его не узнал. Сверь ключ с командой /link "
            "в боте и повтори: link <ключ>."
        )
        return 1
    if status == "ok" and remaining == 0:
        print("Ключ принят, плагин привязан к боту. Отправлено событий: {}.".format(sent))
    else:
        print(
            "Ключ записан. Бот сейчас недоступен — события отправлю при "
            "следующей команде."
        )
    return 0


def _cmd_sync(args, state_path, content_root, quests_root):
    data = _load(state_path)
    if not data.get("link_key"):
        print(
            "Плагин не привязан к боту. Возьми ключ командой /link в боте "
            "и выполни: link <ключ>."
        )
        return 1
    if not data.get("pending_sync"):
        print("Очередь пуста — всё уже отправлено.")
        return 0
    sent, dropped, remaining, status = sync.flush(state_path)
    if status == "unknown_key":
        print(
            "Бот не узнал ключ. Возьми свежий командой /link в боте (после "
            "/newkey старый умирает) и привяжи заново: link <ключ>."
        )
        return 1
    if status == "ok":
        print("Отправлено событий: {}.".format(sent))
        return 0
    print(
        "Бот недоступен. В очереди осталось {} — отправлю при следующей "
        "команде.".format(remaining)
    )
    return 1


BOOK_ANSWERS = {"yes": True, "no": False}


def _cmd_reset(args, state_path, content_root, quests_root):
    """Начать игру заново: сохранение уходит в архив, не в корзину.

    Двухшаговая нарочно. Команду зовёт модель по слову падавана, и «начни
    заново», сказанное вскользь, не должно стирать месяц пути: без аргумента
    ручка только показывает, что уйдёт в архив, и называет второй шаг —
    `reset confirm`. Скилл обязан переспросить человека до него.

    Архив, а не удаление: файл переименовывается рядом с датой в имени, и
    вернуть его — одно `mv` обратно. Резервная копия `.bak` едет следом с тем
    же хвостом. Ключ привязки к боту уходит в архив вместе со всем — новое
    сохранение привязывается заново командой `link <ключ>`; неотправленные
    боту события пропадают, и об этом говорится, а не умалчивается.

    Файлы проекта падавана не трогаются: они его, а не игры.
    """
    path = Path(state_path) if state_path else st.state_path()
    if not path.exists():
        print("Сохранения нет — начинать заново нечего: игра и так с чистого листа.")
        return 0
    try:
        data = st.load(path)
    except st.StateError:
        data = {}
    rank = data.get("rank", st.RANK_YOUNGLING)
    summary = [
        "Ранг: {}".format(ranks.RANK_TITLES.get(rank, rank)),
        "XP: {}".format(data.get("xp", 0)),
        "Папка проекта: {}".format((data.get("project") or {}).get("path") or "не назначена"),
        "Ключ привязки к боту: {}".format("есть" if data.get("link_key") else "нет"),
        "Событий, не отправленных боту: {}".format(len(data.get("pending_sync") or [])),
    ]
    if not args or args[0] != "confirm":
        print("Начать заново — значит убрать в архив это сохранение:")
        for line in summary:
            print("  " + line)
        print("")
        print("Файлы проекта останутся на месте: они твои, а не игры.")
        print("Подтверждение — reset confirm. Без него ничего не меняется.")
        return 0
    stamp = time.strftime("%Y-%m-%d-%H%M", time.gmtime())
    archive = path.with_name(path.name + ".arhiv-" + stamp)
    # Хвост с секундами — только если минута уже занята: два reset подряд
    # не должны затирать первый архив вторым.
    if archive.exists():
        archive = path.with_name(path.name + ".arhiv-" + time.strftime("%Y-%m-%d-%H%M%S", time.gmtime()))
    os.replace(str(path), str(archive))
    backup = st.backup_path(path)
    if backup.exists():
        os.replace(str(backup), str(archive) + ".bak")
    print("Сохранение убрано в архив: {}".format(archive))
    print("Вернуть, если передумал: mv {} {}".format(archive, path))
    if data.get("link_key"):
        print("Ключ привязки уехал вместе с ним: новое сохранение привяжи заново — link <ключ>.")
    if data.get("pending_sync"):
        print("Неотправленные боту события пропали вместе с архивом — их было {}.".format(
            len(data["pending_sync"])))
    if _inside_golokron():
        # Голокрон закрывает Подготовку в одну сторону и исчезнувшее
        # сохранение не замечает намеренно: заново спросить папку и всё
        # остальное он сможет только с перезапуска.
        print("Теперь закрой Голокрон целиком и открой заново — он спросит папку продукта и всё остальное с начала.")
    else:
        print("Новая игра начнётся с первой же команды: /jedicoder:start.")
    return 0


def _cmd_book(args, state_path, content_root, quests_root):
    """Ответ падавана про Книгу: открывать вкладку или нет.

    Спрашивает модель, отвечает эта ручка — input() из cli.py невозможен
    (TTY нет). Запись идёт через st.update_state: новый код обязан ходить
    под файловой блокировкой, а не повторять load→save (долг №8).
    """
    if not args:
        data = _load(state_path)
        answer = data.get("book_open")
        if answer is True:
            print("Книга: открывается сама на входе в главу.")
        elif answer is False:
            print("Книга: сама не открывается, ссылку печатаю.")
        else:
            print("Книга: не отвечено.")
            print("book yes — открывать вкладку; book no — не открывать.")
        return 0
    choice = args[0]
    if choice not in BOOK_ANSWERS:
        # Состояние не трогаем: мусорное значение не должно затирать выбор.
        print(
            "Не знаю ответ {!r}. Допустимые: yes, no.".format(choice)
        )
        return 1
    with st.update_state(state_path) as fresh:
        fresh["book_open"] = BOOK_ANSWERS[choice]
        # Отвеченный вопрос больше не задаётся, даже если падаван ответил
        # раньше, чем игра успела спросить.
        fresh["book_asked"] = True
    if BOOK_ANSWERS[choice]:
        print("Книгу буду открывать на входе в каждую главу.")
    else:
        print("Не буду открывать — ссылку на разворот всё равно напечатаю.")
    return 0


HANDLERS = {
    "status": _cmd_status,
    "contract": _cmd_contract,
    "enter": _cmd_enter,
    "check": _cmd_check,
    "ack": _cmd_ack,
    "project": _cmd_project,
    "track": _cmd_track,
    "artifact": _cmd_artifact,
    "debrief": _cmd_debrief,
    "scroll": _cmd_scroll,
    "link": _cmd_link,
    "sync": _cmd_sync,
    "finale": _cmd_finale,
    "book": _cmd_book,
    "reset": _cmd_reset,
    "recipe": _cmd_recipe,
}


def main(argv=None, state_path=None, content_root=None, quests_root=None,
         plugin_root_path=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Путь не передан — его считает state.state_path(): та же функция,
    # что у хуков, и та же переменная JEDICODER_STATE_PATH. Прибитое
    # умолчание отправляло бы любой прогон CLI в боевое сохранение.
    state_path = Path(state_path) if state_path else st.state_path()
    content_root = Path(content_root or DEFAULT_CONTENT_ROOT)
    quests_root = Path(quests_root or DEFAULT_QUESTS_ROOT)

    if not argv:
        print(USAGE)
        return 1
    name, args = argv[0], argv[1:]
    if name == "root":
        return _cmd_root(args, state_path, content_root, quests_root, plugin_root_path)
    handler = HANDLERS.get(name)
    if handler is None:
        print("Неизвестная команда {!r}. {}".format(name, USAGE))
        return 1
    code = handler(args, state_path, content_root, quests_root)
    if name not in ("link", "sync"):
        sync.maybe_flush(state_path)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
