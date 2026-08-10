"""Предикаты _lib/md.sh на фикстурах.

Гоняются через bash, а не имитируются на Python: проверки падавана
исполняет bash, и расхождение диалектов должно ловиться здесь.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

MD_LIB = Path(__file__).resolve().parents[1] / "plugin" / "quests" / "_lib" / "md.sh"


def run(snippet, tmp_path, env=None):
    """Выполнить bash-фрагмент с загруженным md.sh. Вернуть код возврата.

    env=None — унаследовать окружение процесса (обычный случай). Передашь
    свой словарь — подменится целиком, не слиянием: так тесты на локаль
    гоняют md.sh в намеренно урезанном окружении, а не в реальном плюс одна
    переменная поверх.
    """
    script = 'source "{}"\n{}\n'.format(MD_LIB, snippet)
    done = subprocess.run(
        ["bash", "-c", script], cwd=str(tmp_path), capture_output=True, text=True,
        env=env,
    )
    return done.returncode


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# Хвост "Почему сейчас" специально длинный (за счёт повтора, не опечатка):
# если jc_section перестанет останавливаться на следующем заголовке и
# утечёт до конца файла, эти слова добавятся к подсчёту "Для кого" и
# перетащат итог через порог 40 в тесте ниже. Без длинного хвоста тест
# проходил бы и на сломанной версии: своих 11 слов плюс короткий чужой
# хвост давали в сумме меньше 40, и утечка была не отличима от нормы.
IDEA = """# Идея

## Боль
Каждый вечер вручную свожу расходы семьи из трёх банковских приложений
в одну таблицу, и это занимает почти час.

## Для кого
Я и жена. Ещё двое друзей просили сделать им такое же.

## Почему сейчас
Два банка открыли API в этом году, раньше это было невозможно.
""" + ("Ещё слов до кучи, чтобы хвост был заведомо длинным. " * 15)


def test_has_heading_finds_section(tmp_path):
    write(tmp_path, "IDEA.md", IDEA)
    assert run("jc_has_heading IDEA.md '[Бб]оль'", tmp_path) == 0


def test_has_heading_missing_section(tmp_path):
    write(tmp_path, "IDEA.md", IDEA)
    assert run("jc_has_heading IDEA.md '[Кк]анал'", tmp_path) == 1


def test_has_heading_accepts_lowercase_first_letter(tmp_path):
    write(tmp_path, "IDEA.md", "## боль\nтекст тут\n")
    assert run("jc_has_heading IDEA.md '[Бб]оль'", tmp_path) == 0


def test_has_heading_accepts_tail_after_word(tmp_path):
    write(tmp_path, "IDEA.md", "## Боль — что именно бесит\nтекст тут\n")
    assert run("jc_has_heading IDEA.md '[Бб]оль'", tmp_path) == 0


def test_section_words_counts_only_its_own_section(tmp_path):
    write(tmp_path, "IDEA.md", IDEA)
    assert run("jc_section_words IDEA.md '[Дд]ля кого' 8", tmp_path) == 0
    assert run("jc_section_words IDEA.md '[Дд]ля кого' 40", tmp_path) == 1


def test_section_words_rejects_stub_words(tmp_path):
    write(tmp_path, "IDEA.md", "## Боль\nTODO\n\n## Для кого\n—\n")
    assert run("jc_section_words IDEA.md '[Бб]оль' 1", tmp_path) == 1
    assert run("jc_section_words IDEA.md '[Дд]ля кого' 1", tmp_path) == 1


def test_section_words_on_missing_file(tmp_path):
    assert run("jc_section_words NOPE.md '[Бб]оль' 1", tmp_path) == 1


def test_section_matches_content(tmp_path):
    write(tmp_path, "SLICE.md", "## Оценка\nОдин вечер, часа три.\n")
    assert run("jc_section_matches SLICE.md '[Оо]ценка' '[0-9]|вечер'", tmp_path) == 0


def test_section_matches_rejects_other_section(tmp_path):
    write(tmp_path, "SLICE.md", "## Войдёт\n42 экрана\n\n## Оценка\nнепонятно\n")
    assert run("jc_section_matches SLICE.md '[Оо]ценка' '[0-9]'", tmp_path) == 1


def test_section_one_line(tmp_path):
    write(tmp_path, "CHANNEL.md", "## Канал\nТелеграм-канал про финансы\n")
    assert run("jc_section_one_line CHANNEL.md '[Кк]анал[[:space:]]*$'", tmp_path) == 0


def test_section_one_line_rejects_three(tmp_path):
    write(
        tmp_path, "CHANNEL.md",
        "## Канал\n- телеграм\n- ютуб\n- хабр\n",
    )
    assert run("jc_section_one_line CHANNEL.md '[Кк]анал[[:space:]]*$'", tmp_path) == 1


def test_section_one_line_rejects_empty(tmp_path):
    write(tmp_path, "CHANNEL.md", "## Канал\n\n## Почему он\nтам моя аудитория\n")
    assert run("jc_section_one_line CHANNEL.md '[Кк]анал[[:space:]]*$'", tmp_path) == 1


def test_section_skips_empty_document_title(tmp_path):
    """Заголовок документа в тон квесту не должен перехватывать секцию.

    Падаван почти всегда называет файл словом из квеста, и «# Канал» стоит
    строкой выше «## Канал». Под заголовком документа пусто — и проверка
    валила написанное, а подсказка звала добавить раздел, который уже есть.
    """
    write(
        tmp_path, "CHANNEL.md",
        "# Канал\n\n## Канал\nТелеграм-канал про финансы\n\n"
        "## Почему он\nтам моя аудитория\n",
    )
    assert run("jc_section_one_line CHANNEL.md '[Кк]анал[[:space:]]*$'", tmp_path) == 0


def test_section_skips_empty_title_for_words_and_matches(tmp_path):
    """Тот же перехват ломал и подсчёт слов, и поиск по содержимому."""
    write(tmp_path, "IDEA.md", "# Боль\n\n" + IDEA)
    assert run("jc_section_words IDEA.md '[Бб]оль' 8", tmp_path) == 0
    write(
        tmp_path, "UNIT.md",
        "# CAC, LTV и стоимость токенов\n\n## CAC\n300 рублей на рекламу\n",
    )
    assert run("jc_section_matches UNIT.md 'CAC' '[0-9]'", tmp_path) == 0


def test_section_prefers_two_hashes_over_filled_document_title(tmp_path):
    """Заголовок документа проигрывает разделу, даже когда под ним есть текст.

    Это и есть правило: судят раздел «## Боль», как и написано в подсказке.
    «Первое непустое совпадение» здесь выбрало бы заголовок документа —
    и падаван не мог бы узнать, какой из двух кусков ему оценивают.
    """
    write(
        tmp_path, "IDEA.md",
        "# Боль\nсемья тонет в трёх банковских приложениях каждый вечер\n\n"
        "## Боль\nдругой текст\n",
    )
    assert run("jc_section_matches IDEA.md '[Бб]оль' 'другой'", tmp_path) == 0
    assert run("jc_section_matches IDEA.md '[Бб]оль' 'семья'", tmp_path) == 1
    assert run("jc_section_words IDEA.md '[Бб]оль' 8", tmp_path) == 1


def test_section_prefers_two_hashes_for_one_line_predicate(tmp_path):
    """Тот же выбор для «ровно одной строки» — предиката, который ломается
    не в ту же сторону, что счётчики слов.

    Одна строка вступления под «# Канал» не должна выигрывать у настоящего
    раздела с тремя каналами: квест существует ради правила «пять каналов —
    это ноль каналов», и три канала обязаны оставаться провалом.
    """
    write(
        tmp_path, "CHANNEL.md",
        "# Канал\nПока не решил окончательно.\n\n"
        "## Канал\n- телеграм\n- ютуб\n- хабр\n",
    )
    assert run("jc_section_one_line CHANNEL.md '[Кк]анал[[:space:]]*$'", tmp_path) == 1


def test_section_one_line_passes_under_wordy_document_title(tmp_path):
    """Обратная сторона того же: раздел оформлен верно — значит зачёт,
    сколько бы строк ни было во вступлении под заголовком документа."""
    write(
        tmp_path, "CHANNEL.md",
        "# Канал\nДолго выбирал между вариантами.\nВ итоге остановился на одном.\n\n"
        "## Канал\nТелеграм-канал про финансы\n",
    )
    assert run("jc_section_one_line CHANNEL.md '[Кк]анал[[:space:]]*$'", tmp_path) == 0


def test_section_falls_back_to_single_hash_when_no_deeper_heading(tmp_path):
    """Разделы одной решёткой — рабочий сегодня путь, и он обязан остаться.

    Требование «уровень ≥2» без этого отката отобрало бы его: падаван,
    оформивший «# Боль», «# Для кого», «# Почему сейчас» с текстом под
    каждым, получил бы провал всех трёх проверок разом.
    """
    write(
        tmp_path, "IDEA.md",
        "# Боль\nКаждый вечер свожу расходы семьи из трёх банков в таблицу вручную.\n\n"
        "# Для кого\nЯ и жена, ещё двое друзей просили сделать им такое же.\n",
    )
    assert run("jc_section_words IDEA.md '[Бб]оль' 8", tmp_path) == 0
    assert run("jc_section_words IDEA.md '[Дд]ля кого' 8", tmp_path) == 0
    assert run("jc_section_matches IDEA.md '[Бб]оль' 'расходы'", tmp_path) == 0
    write(tmp_path, "CHANNEL.md", "# Канал\nТелеграм-канал про финансы\n")
    assert run("jc_section_one_line CHANNEL.md '[Кк]анал[[:space:]]*$'", tmp_path) == 0


def test_section_stays_empty_when_every_match_is_empty(tmp_path):
    """Пусто везде — значит пусто: правило не выдаёт незаполненное за готовое."""
    write(tmp_path, "IDEA.md", "# Боль\n\n## Боль\n\n## Для кого\nя и жена\n")
    assert run("jc_section_words IDEA.md '[Бб]оль' 1", tmp_path) == 1
    assert run("jc_section_one_line IDEA.md '[Бб]оль'", tmp_path) == 1


def _fat_body():
    """Тело секции заведомо больше буфера трубы (64 КБ) — с запасом.

    Запас нужен, чтобы сторож падал на сломанной версии всегда: предел тут
    не фиксированный, а гонка. На 64 КБ проверка проваливалась в 19 прогонах
    из 20, на 32 КБ — в 3 из 20. Сторож, срабатывающий через раз, — не сторож.
    """
    line = "Каждый вечер вручную свожу расходы семьи из трёх банков в таблицу.\n"
    return line * (200 * 1024 // len(line.encode("utf-8")) + 1)


def test_section_matches_survives_section_larger_than_pipe_buffer(tmp_path):
    """У jc_section_matches читателем стоит grep, и он тоже обязан дочитывать.

    Отдельный тест, потому что отдельная причина: здесь ранний выход не в
    пробе тела внутри jc_section, а в самом предикате — `grep -q` бросал
    писателя с EPIPE уже на выходе из секции. Этот отказ старше прошлой
    волны правок: раздел «## CAC» на 200 КБ валил 06f-unit в 10 прогонах
    из 10 и до неё.
    """
    write(tmp_path, "UNIT.md", "## CAC\n" + _fat_body() + "\n## LTV\n1200 рублей\n")
    assert run(
        "set -o pipefail; jc_section_matches UNIT.md 'CAC' 'расходы'", tmp_path
    ) == 0
    assert run(
        "set -o pipefail; jc_section_matches UNIT.md 'CAC' 'ничегонетакого'", tmp_path
    ) == 1, "дочитывание до конца не должно превратить предикат в «всегда да»"


def test_section_predicates_survive_section_larger_than_pipe_buffer(tmp_path):
    """У разбора секции не должно быть верхнего предела по размеру.

    Проверки падавана гоняются с `set -o pipefail`. Любая проба тела через
    конвейер, правая часть которого выходит рано (`grep -q`), упирается в
    буфер трубы: писатель получает EPIPE, ловит SIGPIPE, конвейер отдаёт
    141, и полностью написанная секция считается пустой. Предел при этом
    не фиксированный, а гонка — на одном и том же файле проверка то
    проходит, то нет.

    Размер взят с большим запасом (200 КБ против 64 КБ буфера), чтобы тест
    падал на сломанной версии всегда, а не в девятнадцати случаях из
    двадцати: сторож, срабатывающий через раз, — не сторож.
    """
    write(tmp_path, "IDEA.md", "## Боль\n" + _fat_body() + "\n## Для кого\nя и жена\n")
    assert run("set -o pipefail; jc_section_words IDEA.md '[Бб]оль' 8", tmp_path) == 0
    write(tmp_path, "CHANNEL.md", "## Канал\n" + _fat_body())
    assert run(
        "set -o pipefail; jc_section_one_line CHANNEL.md '[Кк]анал[[:space:]]*$'",
        tmp_path,
    ) == 1, "одна строка из тысяч — по-прежнему провал, а не срыв разбора"


def test_sourcing_emit_after_md_does_not_wipe_collected_rows(tmp_path):
    """Порядок source не должен решать судьбу уже собранных проверок.

    md.sh — надстройка над emit.sh и сорсит его сам. Если следом сорснуть
    emit.sh второй раз, он обязан быть пустышкой: повторный прогон обнулил
    бы JC_ROWS, и результаты проверок молча пропали бы из JSON.
    """
    snippet = (
        'jc_init "act1/пример"\n'
        'jc_check first "первая" "подсказка" true\n'
        'source "{}/emit.sh"\n'
        'jc_check second "вторая" "подсказка" true\n'
        "jc_finish\n"
    ).format(MD_LIB.parent)
    done = subprocess.run(
        ["bash", "-c", 'source "{}"\n{}'.format(MD_LIB, snippet)],
        cwd=str(tmp_path), capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr
    payload = json.loads(done.stdout)
    assert [c["id"] for c in payload["checks"]] == ["first", "second"]


def test_file_words_boundary(tmp_path):
    write(tmp_path, "ICP.md", " ".join(["слово"] * 60))
    assert run("jc_file_words ICP.md 60", tmp_path) == 0
    assert run("jc_file_words ICP.md 61", tmp_path) == 1


def test_min_matches_boundary(tmp_path):
    write(tmp_path, "MARKET.md", "TAM 50000, SAM 5000, SOM 500")
    assert run("jc_min_matches 3 '[0-9]+' MARKET.md", tmp_path) == 0
    assert run("jc_min_matches 4 '[0-9]+' MARKET.md", tmp_path) == 1


def test_min_urls_counts_distinct(tmp_path):
    write(
        tmp_path, "COMPETITORS.md",
        "https://a.example https://b.example https://c.example",
    )
    assert run("jc_min_urls 3 COMPETITORS.md", tmp_path) == 0


def test_min_urls_rejects_repeated_same_url(tmp_path):
    write(
        tmp_path, "COMPETITORS.md",
        "https://a.example https://a.example https://a.example",
    )
    assert run("jc_min_urls 3 COMPETITORS.md", tmp_path) == 1


def test_predicates_survive_hostile_ambient_locale(tmp_path):
    """md.sh сам подбирает рабочую UTF-8-локаль из тех, что реально есть на
    машине (см. начало md.sh) — вместо того, чтобы полагаться на локаль,
    унаследованную от вызывающего. Здесь этот механизм и проверяем: гоняем
    bash в намеренно урезанном окружении (только PATH, как на машине, где
    никто никогда не настраивал LANG) и убеждаемся, что кириллица всё равно
    матчится. Без самопочинки внутри md.sh это упало бы: класс [Бб]оль в
    голой C-локали режет буквы на байты и заголовок не находится.

    Настоящей macOS отсюда не проверить (см. отчёт задачи) — эта версия
    защиты пинит только то, что можно честно воспроизвести на этой машине.
    """
    write(tmp_path, "IDEA.md", IDEA)
    hostile_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    assert run("jc_has_heading IDEA.md '[Бб]оль'", tmp_path, env=hostile_env) == 0
    assert run("jc_section_words IDEA.md '[Дд]ля кого' 8", tmp_path, env=hostile_env) == 0
    assert run("jc_section_words IDEA.md '[Дд]ля кого' 40", tmp_path, env=hostile_env) == 1
