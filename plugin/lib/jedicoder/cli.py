#!/usr/bin/env python3
"""Единая точка входа для скиллов и команд плагина.

Скиллы — markdown, поэтому вся логика вызывается отсюда одной командой,
а скилл только пересказывает вывод падавану по правилам контракта.
"""
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jedicoder import acts, content, contract, frontmatter, quests, ranks, sync  # noqa: E402
from jedicoder import state as st  # noqa: E402

SUBCOMMANDS = (
    "status", "contract", "enter", "check", "ack", "project", "track",
    "artifact", "link", "sync", "finale", "book", "root",
)

# Адрес Голокрона. Переменная окружения — по образцу sync.endpoint(): нужна
# тестам и локальной проверке, падавану про неё знать незачем.
DEFAULT_SITE_URL = "https://jedicoder.store"

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


def render_status(data):
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
    lines += [
        "Тёмная сторона: {}".format(data.get("dark_side", 0)),
        # «Сохранений», а не «коммитов»: эта строка печатается на самом
        # первом экране, до любого акта, а слово «коммит» падаван получает
        # только в Акте 2. Игра сама называет коммит точкой сохранения —
        # значит на первом экране у счётчика есть честное имя, которое ничего
        # не должно объяснять заранее. Регрессия закрыта тестом первого
        # экрана в tests/test_cli.py: линтер контента сюда не дотягивается.
        "Серия сохранений: {} (лучшая {})".format(
            data.get("streak", {}).get("current", 0),
            data.get("streak", {}).get("best", 0),
        ),
        "",
        "Карта:",
    ]
    for number in sorted(ranks.ACTS):
        entry = (data.get("acts") or {}).get(str(number)) or {}
        status = entry.get("status")
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


def _load(state_path):
    data = st.load(state_path)
    if not data.get("padawan_id"):
        data["padawan_id"] = st.new_padawan_id()
        st.save(data, state_path)
    return data


def _cmd_status(args, state_path, content_root, quests_root):
    data = _load(state_path)
    print(render_status(data))
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
    base = (os.environ.get("JEDICODER_SITE_URL") or DEFAULT_SITE_URL).rstrip("/")
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
    # печатать вопрос дважды нельзя.
    if not asked_before:
        data["book_asked"] = True
    st.save(data, state_path)
    info = ranks.ACTS[act]
    print("Акт {}. {} — начат.".format(act, info["title"]))
    print("Артефакт этого акта: {}".format(info["artifact"]))
    print("Ранг за прохождение: {}".format(ranks.RANK_TITLES[info["rank"]]))
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
    print("")
    print("Разворот этой главы: {}".format(_book_url(data, act)))
    if not data.get("link_key"):
        print(
            "Прогресс в книге появится после привязки: ключ выдаёт команда "
            "/link в боте потока, привязывает — link <ключ>."
        )
    if not asked_before:
        # input() здесь невозможен: cli.py запускается инструментом Bash из
        # bash-блока скилла, TTY нет, и input() либо повиснет, либо бросит
        # EOFError. Тот же приём, что у project db / track / project deploy:
        # печатает вопрос CLI, задаёт его падавану модель, пишет ответ ручка.
        print("")
        # Первое место, где падаван видит слово «Голокрон», — значит здесь
        # и глосса (D-04: слово остаётся, но объясняется при первой встрече).
        # Позднейшие упоминания её не повторяют: поясняют один раз.
        print(
            "Голокрон — книга твоего пути: то же, что ты проходишь в "
            "терминале, только страницами и в браузере."
        )
        print("Открывать его на входе в каждую главу?")
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
        deploy = project.get("deploy_path")
        if deploy:
            lines.append("  Путь деплоя: {}".format(deploy))
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
    print("Неизвестная подкоманда 'project {}'. Используй: project [path <путь>|db yes|no|port <номер>|deploy managed|vps|ssh <алиас>|url <адрес>|service <юнит>|post <ссылка>]".format(
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


def _days_in_path(data):
    """Дней от входа в Акт 1 до закрытия Акта 5, включительно; None, если
    отметок нет (беты прошлых версий) — карточка молча пропускает строку.
    """
    acts_map = data.get("acts") or {}
    start = (acts_map.get("1") or {}).get("started_at")
    end = (acts_map.get("5") or {}).get("completed_at")
    try:
        d0 = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ")
        d1 = datetime.strptime(end, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None
    return max(1, (d1 - d0).days + 1)


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


def _cmd_finale(args, state_path, content_root, quests_root):
    """Карточка Мастера. Оффер клуба — будущая версия игры."""
    data = _load(state_path)
    rank = data.get("rank", st.RANK_YOUNGLING)
    if rank != "master":
        print("Финал ждёт Мастера. Твой ранг сейчас — {}.".format(
            ranks.RANK_TITLES.get(rank, rank)
        ))
        print("Карточка рисуется, когда закрыт Акт 5 «Выход в свет».")
        return 1
    if not data.get("finale_announced"):
        data["finale_announced"] = True
        st.enqueue_event(data, "finale", payload={
            "rank": data.get("rank"), "xp": int(data.get("xp", 0)),
        })
        st.save(data, state_path)
    lines = ["=== Карточка Мастера ==="]
    url = (data.get("project") or {}).get("url")
    if url:
        lines.append("Продукт: {}".format(url))
    days = _days_in_path(data)
    if days is not None:
        lines.append("Дней в пути: {}".format(days))
    commits = _project_commit_count(data)
    if commits is not None:
        lines.append("Коммитов: {}".format(commits))
    lines.append("Слов открыто: {}".format(len(data.get("lexicon_unlocked") or [])))
    lines.append("XP: {}".format(data.get("xp", 0)))
    lines.append("Тёмная сторона: {}".format(data.get("dark_side", 0)))
    print("\n".join(lines))
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


def _cmd_book(args, state_path, content_root, quests_root):
    """Ответ падавана про Голокрон: открывать вкладку или нет.

    Спрашивает модель, отвечает эта ручка — input() из cli.py невозможен
    (TTY нет). Запись идёт через st.update_state: новый код обязан ходить
    под файловой блокировкой, а не повторять load→save (долг №8).
    """
    if not args:
        data = _load(state_path)
        answer = data.get("book_open")
        if answer is True:
            print("Голокрон: открывается сам на входе в главу.")
        elif answer is False:
            print("Голокрон: сам не открывается, ссылку печатаю.")
        else:
            print("Голокрон: не отвечено.")
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
        print("Голокрон буду открывать на входе в каждую главу.")
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
    "link": _cmd_link,
    "sync": _cmd_sync,
    "finale": _cmd_finale,
    "book": _cmd_book,
}


def main(argv=None, state_path=None, content_root=None, quests_root=None,
         plugin_root_path=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    state_path = Path(state_path or st.STATE_PATH)
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
