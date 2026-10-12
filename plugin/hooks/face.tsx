// Лицо игры внутри Claude Code: Полоса над полем ввода, всплывающие сообщения
// о закрытом квесте и новом ранге, подсказка в поле ввода, контракт игры в
// системном промпте и Инструменты игры (ADR-0019, спека #89).
//
// Правило слоя. Модуль рисует и подаёт. Он не пишет в сохранение, не решает
// исход квеста, не считает чисел и не держит текстов игры: всё, что стоит на
// экране, отдаёт команда игры `cli.py face` одним снимком в JSON, текст
// контракта — `cli.py contract --section`, перечень инструментов —
// `cli.py tools`. Инструмент — та же команда игры, вызванная без терминала:
// `cli.py tool <имя>`. Сохранение пишет она, и квест судит она.
//
// Закон лица. Любая ошибка здесь — тишина: Полосы нет, игра идёт. Одно
// исключение — инструмент, чья команда не выполнилась: модель обязана это
// узнать, иначе несостоявшийся вызов сошёл бы за сделанный.
//
// Команда игры зовётся по пути своего плагина. Файл-маркер в домашней папке
// модулю не нужен и им не читается.
//
// Память. Всё, что модуль знает о разговоре, лежит в состоянии сессии, и движок
// вправе его стереть. Замер 2026-10-12, Claude Code 2.1.296: на `/clear` он
// зовёт `session.end` с причиной `clear`, затем стирает состояние целиком —
// и то, что записано в самом `session.end`, — затем зовёт прежнее событие
// старта с источником `clear`. `session.start` не приходит. Поэтому память
// восстанавливается лениво (`wake`): хук, которому она нужна, сам замечает,
// что её нет, и спрашивает игру заново. Вне состояния модуль держит одно:
// прошёл ли его старт в этом процессе.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Face, GameTool, Voice } from '../types'

const face = atom({ plugin: 'jedicoder', key: 'face' } as const, null)
const called = atom({ plugin: 'jedicoder', key: 'called' } as const, false)
const game = atom({ plugin: 'jedicoder', key: 'game' } as const, false)
const said = atom({ plugin: 'jedicoder', key: 'said' } as const, '')
const voice = atom({ plugin: 'jedicoder', key: 'voice' } as const, null)
const look = atom({ plugin: 'jedicoder', key: 'look' } as const, 'none')
const KIT = { plugin: 'jedicoder', key: 'tools' } as const
const kit = atom(KIT, [])
const awake = atom({ plugin: 'jedicoder', key: 'awake' } as const, false)

// Имя раздела системного промпта с контрактом игры: <плагин>:<раздел>.
const CONTRACT_SECTION = 'jedicoder:contract'

// Команды плагина Claude Code зовёт как /<плагин>:<команда>.
const GAME_COMMAND = '/jedicoder:'

// Инструменты игры движок зовёт как mcp__<плагин>__<имя>. Имён модуль не
// знает: один хук обслуживает всё, что начинается так, а перечень приходит
// от команды.
const TOOL_PREFIX = 'mcp__jedicoder__'
const OWN_TOOLS = /^mcp__jedicoder__/

// Сколько ждать команду инструмента. Проверка квеста внутри команды сама
// прерывается через минуту, ещё пять секунд берёт отправка событий: две
// минуты дают команде договорить своими словами. Проверкам поздних актов
// (свой сервер, минуты) понадобится больше — движок даёт до десяти минут.
const TOOL_MS = 120000

// Что читает модель, когда команда инструмента не выполнилась. Не слова
// игры: человеку этот текст не адресован, модель по нему идёт в терминал.
const TOOL_FAILED =
  'jedicoder: the game command did not run or did not finish, so nothing is known about its outcome. Run the same game command in the terminal instead, as the skill of the act says.'

// Что напечатала команда: объект снимка — или null, когда это не снимок.
function parse(text: string): Partial<Face> | null {
  const data = JSON.parse(text)

  return data === null || typeof data !== 'object' ? null : data
}

// Игровая ли сессия. Признак отдельный от Полосы: рисовать бывает нечего и
// в Игровой сессии, а догадке движка в поле ввода там всё равно не место.
function isGame(data: Partial<Face> | null): boolean {
  return data !== null && data.is_game === true
}

// Снимок, по которому можно рисовать, — или null, когда рисовать нечего.
function drawable(data: Partial<Face> | null): Face | null {
  if (data === null || !isGame(data)) return null
  if (!Array.isArray(data.next) || data.next.length === 0) return null
  if (!data.next.every((line: unknown) => typeof line === 'string')) return null

  return data as Face
}

// Фраза, которую игра предлагает сказать, — или пусто. Слово — из снимка,
// как пришло; вне Игровой сессии фразы нет.
function phrase(data: Partial<Face> | null): string {
  return data !== null && isGame(data) && typeof data.say === 'string' ? data.say : ''
}

// Сколько всплывающее стоит на экране. Оно приходит вместе с ответом модели,
// и человек сперва читает ответ: четырёх секунд движка на это мало.
const TOAST_MS = 8000

// Подпись всплывающего при переходе от прежнего снимка к новому — или пусто.
// Повод один: закрытых квестов стало больше. Сменился при этом ранг — подпись
// о ранге, и она одна: ранг главнее квеста. Прежнего снимка нет (сессия только
// началась, команда упала, сессия была не игровой) — сравнивать не с чем.
// Слова — из нового снимка, как пришли.
function raised(before: Face | null, now: Face | null): string {
  if (before === null || now === null) return ''
  if (typeof now.quests_closed !== 'number' || typeof before.quests_closed !== 'number') return ''
  if (!(now.quests_closed > before.quests_closed)) return ''
  const caption = now.rank === before.rank ? now.toast_quest : now.toast_rank

  return typeof caption === 'string' ? caption : ''
}

// Единственный процесс модуля: команда игры по пути своего плагина. Оболочки
// нет: каждое слово — отдельный аргумент, как пришло.
function ask($: EngineInterface, words: string[], init = {}) {
  const argv = ['python3', `${$.plugin.root}/lib/jedicoder/cli.py`, ...words]

  return $.process.run(argv, init)
}

// Запись перечня, которой можно верить: все четыре поля на месте.
function isTool(item: unknown): item is GameTool {
  if (item === null || typeof item !== 'object') return false
  const tool = item as Partial<GameTool>
  if (typeof tool.name !== 'string' || tool.name === '') return false
  if (typeof tool.description !== 'string' || tool.description === '') return false
  if (tool.inputSchema === null || typeof tool.inputSchema !== 'object') return false

  return Array.isArray(tool.input) && tool.input.every(key => typeof key === 'string')
}

// Перечень инструментов, как его напечатала команда, — или пусто: команда
// упала или не запустилась, ответ обрезан, хоть одна запись испорчена.
// Половины перечня нет.
async function listed($: EngineInterface): Promise<GameTool[]> {
  try {
    const ran = await ask($, ['tools'])
    if (ran.exitCode !== 0 || ran.isStdoutTruncated) return []
    const data: unknown = JSON.parse(ran.stdout)
    if (!Array.isArray(data) || !data.every(isTool)) return []

    return data.map(({ name, description, inputSchema, input }) => ({
      name,
      description,
      inputSchema,
      input,
    }))
  } catch {
    return []
  }
}

// Объявить инструменты игры: что команда перечислила, то и объявлено, её
// словами. Схема видна модели с первого запроса — за ToolSearch инструмент
// игры искать некому. Перечня нет — инструментов нет, и модель зовёт команды
// игры в терминале, как велит скилл.
async function declare($: EngineInterface) {
  const declared: GameTool[] = []
  for (const tool of await listed($)) {
    try {
      const { name, description, inputSchema } = tool
      await $.tool.register({ name, description, inputSchema, isDeferred: false })
      declared.push(tool)
    } catch {
      // Тишина: этот инструмент не объявлен, его команду модель наберёт сама.
    }
  }
  await update($, kit, () => declared)
}

// Выполнить инструмент: команда игры `tool <имя>` и значения входа — каждое
// отдельным аргументом, в порядке перечня. Подкоманду игры модуль не
// называет: её по имени инструмента выбирает сама команда, и только из
// своего перечня. Значение не строка — дальше ничего не кладётся.
//
// Ответ — всё, что команда напечатала, и её код возврата. Код едет рядом с
// ответом, строкой для модели: человек под вызовом видит только слова игры.
// Модуль ничего не толкует: «не сошлось» (1) и «не смог проверить» — ответ,
// а не ошибка.
// Команда не запустилась или не уложилась во время — вызов бросает, и хук
// отвечает честным отказом.
async function serve($: EngineInterface, tool: GameTool, e: Record<string, unknown>) {
  const words = ['tool', tool.name]
  for (const key of tool.input) {
    const value = e[key]
    if (typeof value !== 'string') break
    words.push(value)
  }
  const ran = await ask($, words, { cwd: await $.session.cwd(), timeoutMs: TOOL_MS })
  try {
    // Команду игры позвали — сессия игровая; Полоса и всплывающее следуют
    // за тем, что команда записала.
    await update($, called, () => true)
    await refresh($, false)
  } catch {
    // Тишина: команда выполнена, Полоса догонит после хода.
  }

  return { result: `${ran.stdout}${ran.stderr}`, context: [`exit code: ${ran.exitCode}`] }
}

// Игровая ли сессия, решает команда: модуль передаёт ей то, что знает сам, —
// папку сессии и позвана ли в ней команда игры.
async function snapshot($: EngineInterface): Promise<Partial<Face> | null> {
  const words = ['face', '--cwd', await $.session.cwd()]
  if (await read($, called)) words.push('--called')
  const ran = await ask($, words)
  if (ran.exitCode !== 0) return null

  return parse(ran.stdout)
}

// Раздел с контрактом, как его напечатала команда, — или null: команда упала,
// ответ обрезан, текста нет. Половины контракта в системном промпте не бывает.
async function section($: EngineInterface): Promise<Voice | null> {
  const ran = await ask($, ['contract', '--section'])
  if (ran.exitCode !== 0 || ran.isStdoutTruncated) return null
  const data = parse(ran.stdout) as Partial<Voice> | null
  if (data === null || typeof data.text !== 'string' || data.text === '') return null

  return { stamp: typeof data.stamp === 'string' ? data.stamp : '', text: data.text }
}

// Контракт для системного промпта. Правило: раздел читается один раз и
// перечитывается, только когда снимок принёс другой отпечаток, — контракт
// велик и меняется редко (паспорт, режим разрешений). Отпечаток считает
// команда; модуль лишь сравнивает две строки. Вне Игровой сессии раздел не
// читается вовсе.
// Отпечатка в снимке нет — раздела нет. Команда раздела упала — раздела нет,
// и следующий снимок попросит его снова.
// Модель видит раздел, каким он был на первом запросе сессии (см. хук
// `prompt.compose`): перечитанное позже доходит только до рендера, который
// меряет место, и держится наготове, если движок соберёт промпт заново.
async function speak($: EngineInterface, now: Partial<Face> | null) {
  if (now === null || !isGame(now)) return
  const stamp = typeof now.contract === 'string' ? now.contract : ''
  const held = await read($, voice)
  if (stamp === '') {
    if (held !== null) await update($, voice, () => null)

    return
  }
  if (held !== null && held.stamp === stamp) return
  let heard: Voice | null = null
  try {
    heard = await section($)
  } catch {
    heard = null
  }
  await update($, voice, () => heard)
}

// Фраза игры — серым в поле ввода, Tab берёт. Правило: фраза предлагается
// один раз на каждое своё появление в снимке, а не на каждом ходу. Полоса
// называет то же слово всё время, пока оно в силе; серое слово, которое
// возвращается после каждого ответа, человек принимал бы не глядя — от этого
// поле ввода и чистится. Встала ли фраза, говорит движок: не встала (в поле
// текст, идёт ход) — она не предложена, и следующий снимок предложит её снова.
// Фраза ушла из снимка — память о ней стирается: вернётся — встанет заново.
//
// Предлагается фраза только после хода главного разговора. На старте сессии
// рано: игру запускают сразу с командой, первый ход смёл бы фразу с поля, а
// модуль считал бы её показанной. Посреди хода подчинённого агента поле занято.
async function offer($: EngineInterface, say: string) {
  if (say === '') {
    await update($, said, () => '')

    return
  }
  if ((await read($, said)) === say) return
  const { isShown } = await $.prompt.suggest({ text: say })
  if (isShown) await update($, said, () => say)
}

async function refresh($: EngineInterface, isOfferTime: boolean) {
  let before: Face | null = null
  let now: Partial<Face> | null = null
  try {
    before = await read($, face)
    now = await snapshot($)
  } catch {
    now = null
  }
  const drawn = drawable(now)
  try {
    await update($, face, () => drawn)
  } catch {
    // Тишина: прежняя Полоса останется до следующего хода.
  }
  try {
    // Раньше признака игры: кто увидел Игровую сессию, тот видит и раздел.
    await speak($, now)
  } catch {
    // Тишина: модель загрузит контракт командой, как без модуля.
  }
  try {
    // Команда упала — сессия не считается игровой: догадку движка модуль
    // не трогает, как если бы его не было.
    await update($, game, () => isGame(now))
  } catch {
    // Тишина: прежний признак останется до следующего хода.
  }
  try {
    const caption = raised(before, drawn)
    if (caption !== '') await $.ui.toast(caption, { timeoutMs: TOAST_MS })
  } catch {
    // Тишина: квест закрыт и без всплывающего, Полоса уже сменилась.
  }
  try {
    // Команда упала — о фразе ничего не известно: память о ней не стирается.
    if (isOfferTime && now !== null) await offer($, phrase(now))
  } catch {
    // Тишина: слово названо Полосой, человек наберёт его сам.
  }
}

// Перечень инструментов заново, когда его в состоянии нет вовсе: память
// стёрта. Движку инструменты при этом не объявляются: они объявлены этому
// процессу на старте, стирание памяти их не снимает, и вызовы по-прежнему
// идут сюда. Пустой перечень старта («инструментов нет») — не «нет вовсе»,
// и заново не спрашивается. Команда упала или ответ испорчен — не пишется
// ничего: следующий вызов инструмента спросит снова.
async function recall($: EngineInterface) {
  if ((await $.state.get(KIT)).value !== undefined) return
  const tools = await listed($)
  if (tools.length > 0) await update($, kit, () => tools)
}

// Память сессии стёрта — снимок берётся заново, как на старте: с ним Полоса,
// признак игры и раздел с контрактом. Перечень инструментов возвращает их хук,
// когда инструмент позван (`recall`).
// Примета — пометка, которую ставит старт и ставит эта функция: стёрта память —
// стёрта и она. Память на месте — ни одной команды, и на стёртую память
// снимок берётся один раз, а не на каждое событие. Любая ошибка — тишина.
async function wake($: EngineInterface) {
  try {
    if (await read($, awake)) return
    await update($, awake, () => true)
    await refresh($, false)
  } catch {
    // Тишина: Полоса вернётся после хода.
  }
}

export const register: Register = on => {
  // Прошёл ли старт модуля в этом процессе: память есть чему возвращать.
  let isStarted = false

  on('session.start', async ($, e, next) => {
    try {
      // Сессию продолжили или начали заново: первый запрос снова ждёт снимка.
      // Пометку запроса, который успел раньше, не стираем.
      await update($, look, was => (was === 'done' ? 'none' : was))
    } catch {
      // Тишина.
    }
    await refresh($, false)
    try {
      await declare($)
    } catch {
      // Тишина: без инструментов игра идёт командами в терминале.
    }
    try {
      await update($, awake, () => true)
    } catch {
      // Тишина: лишний снимок на следующем событии.
    }
    isStarted = true

    return next(e)
  })

  // Разговор начат заново под живым процессом (`/clear`): `session.start` не
  // придёт, а это событие приходит уже после стирания памяти — и Полоса
  // встаёт до первого запроса. На старте процесса оно приходит раньше
  // `session.start` и ничего не делает; после сжатия память на месте.
  on('classic.SessionStart', async ($, e, next) => {
    if (isStarted) await wake($)

    return next(e)
  }).catch(($, e, next) => next(e))

  // Руки: Инструменты игры. Хук один на все: имя вызванного ищется в
  // перечне, который игра отдала этому процессу. Чужого имени с тем же началом
  // хук не знает и отдаёт вызов дальше — как и при собственной ошибке: совет
  // «набери команду в терминале» получает только тот, чей инструмент есть в
  // перечне, а команда не выполнилась. Память стёрта — перечень сперва
  // спрашивается заново: объявленный инструмент обязан ответить.
  on('tool.call', { tool: OWN_TOOLS }, async ($, e, next) => {
    const name = e.tool.slice(TOOL_PREFIX.length)
    try {
      await recall($)
    } catch {
      // Тишина: без перечня вызов уйдёт дальше.
    }
    const tool = (await read($, kit)).find(item => item.name === name)
    if (tool === undefined) return next(e)
    try {
      return await serve($, tool, e)
    } catch {
      return { deny: TOOL_FAILED }
    }
  }).catch(($, e, next) => next(e))

  // Третий признак игровой сессии: человек позвал команду игры.
  // Запрос человека идёт дальше в любом случае — и когда хук упал.
  //
  // Там, где игра идёт или только что позвана, первый такой запрос человека
  // оставляет пометку: системный промпт этого хода собирается по свежему
  // снимку (ниже, `prompt.compose`). Сам снимок здесь не берётся: режим
  // разрешений пишет в сохранение прежний хук на этом же событии, уже после
  // модуля. Исключение — стёртая память, которую не вернуло событие старта:
  // без снимка не узнать, игровая ли сессия, и пометку не поставить. Режим
  // в том снимке прежний; свежий возьмёт `prompt.compose`.
  on('prompt.submit', async ($, e, next) => {
    try {
      const isCalled = e.text.trimStart().startsWith(GAME_COMMAND)
      if (isCalled) await update($, called, () => true)
      // Память стёрта — признак игры и раздел возвращаются до пометки.
      await wake($)
      if ((isCalled || (await read($, game))) && (await read($, look)) === 'none') {
        await update($, look, () => 'due')
      }
    } catch {
      // Тишина.
    }

    return next(e)
  }).catch(($, e, next) => next(e))

  on('turn.complete', async ($, e, next) => {
    await refresh($, e.agentId === undefined)

    return next(e)
  })

  // Догадка движка о следующем ответе человека в Игровой сессии не встаёт:
  // принятая клавишей Tab, она проходила квест за человека. Что предлагает
  // модуль — этот или чужой — идёт дальше нетронутым. Хук упал — догадка
  // встаёт, как без модуля.
  on('prompt.suggest', async ($, e, next) => {
    if (e.origin.kind !== 'suggestion') return next(e)
    if (!(await read($, game))) return next(e)

    return { isShown: false }
  }).catch(($, e, next) => next(e))

  // Голос: в Игровой сессии контракт игры лежит в системном промпте, и модель
  // не грузит его командой. Раздел — последним, после всего чужого, и на той
  // стороне, что своя у каждой сессии. Вне Игровой сессии, без текста и при
  // любой ошибке системный промпт тот же, каким был бы без модуля.
  //
  // Раздел нужен всякому, кто говорит с человеком, — и измеряющему рендеру
  // тоже: он показывает, сколько места промпт занимает на самом деле. Не
  // нужен он одному: помощнику из команды агентов, который с человеком не
  // говорит.
  //
  // Замер 2026-10-10, Claude Code 2.1.296. Движок зовёт этот хук на каждый
  // запрос человека — после прежних хуков и до обращения к модели. Но до
  // модели доходит только ответ на первый запрос сессии: системный промпт на
  // нём застывает, и что хук отвечает позже, она не видит. Отсюда правило:
  // снимок перечитывается здесь один раз — на первом запросе, где игра идёт
  // или позвана. Сессия, начатая командой игры, получает контракт с первого
  // же хода, а режим разрешений в разделе — тот, что прежний хук записал
  // секунду назад, а не тот, что остался от прошлой сессии. Игру позвали
  // посреди чужого разговора — раздела модель не увидит и загрузит контракт
  // командой, как велит скилл.
  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)
    try {
      if (e.traits.includes('teammate')) return composed
      if ((await read($, look)) === 'due') {
        await update($, look, () => 'done')
        await refresh($, false)
      }
      if (!(await read($, game))) return composed
      const held = await read($, voice)
      if (held === null) return composed
      const others = composed.sections.filter(part => part.id !== CONTRACT_SECTION)
      const own = { id: CONTRACT_SECTION, text: held.text, scope: 'session' } as const

      return { sections: [...others, own] }
    } catch {
      return composed
    }
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const now = e.props.hasSurvey ? null : await read($, face)
    if (now === null) return next(e)

    const { Box, Text } = $.ui.resolve(e)
    // Чужую полосу не прячем: что нарисовали под нами, встаёт над нашими
    // строками. Наши — последние, у самого поля ввода.
    const below = await next(e)

    return (
      <Box flexDirection="column">
        {below}
        <Text bold>{now.next[0]}</Text>
        {now.next.length > 1 ? <Text dimColor>{now.next[1]}</Text> : null}
      </Box>
    )
    // Упали, пока рисовали, — на экране то, что было бы без нас.
  }).catch(($, e, next) => next(e))
}
