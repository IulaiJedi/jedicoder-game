"""Минимальный парсер YAML-фронтматтера.

Поддерживает только то подмножество, которое использует контент-ядро:
скаляры и плоские inline-списки. Всё остальное — ошибка, и линтер контента
следит, чтобы в файлах не появилось ничего сложнее.

Своя реализация вместо PyYAML сознательна: плагин ставится на машину
новичка, и лишняя зависимость через pip — лишняя точка отказа.
"""

DELIMITER = "---"


class FrontmatterError(ValueError):
    """Файл не соответствует поддерживаемому подмножеству."""


def parse(text):
    """Разобрать текст с фронтматтером.

    Вернуть (метаданные: dict, тело: str). Тело обрезано по краям.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != DELIMITER:
        raise FrontmatterError(
            "файл должен начинаться со строки {}".format(DELIMITER)
        )
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == DELIMITER:
            end = index
            break
    if end is None:
        raise FrontmatterError(
            "не найден закрывающий разделитель {}".format(DELIMITER)
        )

    # Pre-pass: check for indentation and other structural issues
    section_lines = lines[1:end]
    for offset, raw in enumerate(section_lines):
        lineno = offset + 2
        # Skip empty lines (after stripping)
        if not raw.strip():
            continue
        # Skip comment lines
        if raw.lstrip().startswith("#"):
            continue
        # Check for indentation (nesting not supported)
        if raw[0] in " \t":
            raise FrontmatterError(
                "строка {}: вложенность не поддерживается".format(lineno)
            )

    # Main parsing pass: extract key-value pairs
    meta = {}
    for offset, raw in enumerate(section_lines):
        lineno = offset + 2
        if not raw.strip():
            continue
        if raw.lstrip().startswith("#"):
            continue
        # Indentation already checked in pre-pass
        if ":" not in raw:
            raise FrontmatterError(
                "строка {}: ожидалось 'ключ: значение'".format(lineno)
            )
        key, _, value = raw.partition(":")
        key = key.strip()
        if not key:
            raise FrontmatterError("строка {}: пустой ключ".format(lineno))
        if key in meta:
            raise FrontmatterError(
                "строка {}: ключ '{}' повторяется".format(lineno, key)
            )
        value = value.strip()
        if not value:
            raise FrontmatterError("строка {}: пустое значение".format(lineno))
        meta[key] = _scalar_or_list(value, lineno)

    return meta, "\n".join(lines[end + 1:]).strip()


def _scalar_or_list(value, lineno):
    if value.startswith("["):
        if not value.endswith("]"):
            raise FrontmatterError("строка {}: незакрытый список".format(lineno))
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part.strip(), lineno) for part in inner.split(",")]
    return _scalar(value, lineno)


def _scalar(value, lineno):
    if not value:
        raise FrontmatterError("строка {}: пустое значение".format(lineno))
    # Check for anchors (&name) and aliases (*name)
    if value[0] in "&*":
        raise FrontmatterError(
            "строка {}: якоря и ссылки не поддерживаются".format(lineno)
        )
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "null":
        return None
    try:
        return int(value)
    except ValueError:
        return value
