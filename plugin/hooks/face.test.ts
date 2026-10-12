// Тесты Лица — Полосы, всплывающих, подсказки в поле ввода, контракта в
// системном промпте и Инструментов игры: `claude plugin test plugin/`.
//
// Тест стоит на месте движка: его хуки лежат под модулем и отвечают за всё,
// что модуль просит у `$`. Команда игры подменена — слова и числа приходят
// только из её ответа, и тест проверяет, что на экране стоят именно они.
import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const STEP = ['NEXT: quest one', 'do the first thing']
const OTHER = 'BAND OF ANOTHER MODULE'
const BAND = {
  plugin: 'jedicoder',
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isWorking: false,
    maxRows: 10,
    bodyColumns: 80,
    scroll: { offset: 0, bodyRows: 9 },
    view: {},
  },
} as const

const QUEST_DONE = 'QUEST DONE'
const RANK_UP = 'RANK UP: second'

type Ran = { exitCode: number; stdout: string; stderr?: string; isStdoutTruncated?: boolean }
type Spec = { name: string; description: string; inputSchema: unknown; isDeferred?: boolean }

type Game = {
  answer: () => Ran
  calls: string[][]
  // Команда раздела с контрактом: её ответ, её вызовы и то, что собрал движок.
  voice: () => Ran
  voiceCalls: string[][]
  sections: { id: string; text: string; scope: string }[]
  // Инструменты игры: перечень от команды, что объявлено движку, вызовы
  // команды инструмента (целиком, с папкой и временем) и её ответ.
  list: () => Ran
  listCalls: string[][]
  registered: Spec[]
  isRegisterRefused: boolean
  ran: () => Ran
  runs: { argv: string[]; cwd?: string; timeoutMs?: number }[]
  toasts: string[]
  isToastRefused: boolean
  shown: { text: string; origin: { kind: string; name?: string } }[]
  isBoxBusy: boolean
  isBoxBroken: boolean
}

function snapshot(next: string[], isGame = true, more: Record<string, unknown> = {}) {
  const body = {
    is_game: isGame,
    next,
    rank: isGame ? 'first' : '',
    quests_closed: 0,
    say: '',
    toast_quest: isGame ? QUEST_DONE : '',
    toast_rank: isGame ? 'RANK UP: first' : '',
    contract: isGame ? STAMP : '',
    ...more,
  }

  return { exitCode: 0, stdout: `${JSON.stringify(body)}\n` }
}

// Перечень, каким его печатает команда: слова выдуманы, состав — два
// инструмента, один со значением входа.
const LISTED = [
  {
    name: 'probe',
    description: 'PROBE THE QUEST',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
    input: [],
  },
  {
    name: 'place',
    description: 'NAME THE PLACE',
    inputSchema: {
      type: 'object',
      properties: { where: { type: 'string', description: 'WHERE' } },
      additionalProperties: false,
    },
    input: ['where'],
  },
]
const tools = (list: unknown = LISTED) => ({ exitCode: 0, stdout: `${JSON.stringify(list)}\n` })
const PROBE = 'mcp__jedicoder__probe'
const PLACE = 'mcp__jedicoder__place'

// Контракт, каким его печатает команда раздела: отпечаток и текст.
const STAMP = 'stamp-one'
const CONTRACT = '# THE MARKER LINE\n\nrule one\nrule two\n'
const spoken = (text = CONTRACT, stamp = STAMP) => ({
  exitCode: 0,
  stdout: `${JSON.stringify({ stamp, text })}\n`,
})
// Что движок собрал сам: общая часть, затем своя у сессии.
const ENGINE_SECTIONS = [
  { id: 'intro', text: 'INTRO', scope: 'shared' },
  { id: 'tools', text: 'TOOLS', scope: 'shared' },
  { id: 'memory', text: 'MEMORY', scope: 'session' },
  { id: 'other:rules', text: 'RULES OF ANOTHER MODULE', scope: 'session' },
]
const OWN_SECTION = { id: 'jedicoder:contract', text: CONTRACT, scope: 'session' }
const composed = async ($: any, traits: string[] = []) => {
  const facts = { model: 'm', promptModel: 'm', surfaces: ['terminal'], tools: [], outputStyle: null }

  return (await $.prompt.compose({ ...facts, traits })).sections
}

// Снимок, каким он бывает после проверки квеста: закрыто больше, ранг тот же или новый.
const closed = (count: number, rank = 'first') =>
  snapshot(STEP, true, { quests_closed: count, rank, toast_rank: `RANK UP: ${rank}` })

// Всё, что под модулем: папка сессии, команда игры и полоса другого модуля.
function engine(on: On, first: Game['answer']): Game {
  const game: Game = {
    answer: first,
    calls: [],
    voice: () => spoken(),
    voiceCalls: [],
    sections: ENGINE_SECTIONS,
    list: () => tools(),
    listCalls: [],
    registered: [],
    isRegisterRefused: false,
    ran: () => ({ exitCode: 0, stdout: 'DONE\n' }),
    runs: [],
    toasts: [],
    isToastRefused: false,
    shown: [],
    isBoxBusy: false,
    isBoxBroken: false,
  }
  const bottom = on as any
  // Поле ввода движка: что до него дошло, то и встало бы серым, — если поле свободно.
  bottom('prompt.suggest', (_$: unknown, e: Game['shown'][number]) => {
    if (game.isBoxBroken) throw new Error('no box here')
    if (game.isBoxBusy) return { isShown: false }
    game.shown.push({ text: e.text, origin: e.origin })

    return { isShown: true }
  })
  bottom('ui.toast', (_$: unknown, e: { text: string }) => {
    if (game.isToastRefused) throw new Error('no toasts here')
    game.toasts.push(e.text)

    return { value: undefined }
  })
  bottom('session.cwd', () => ({ value: '/work/project' }))
  bottom('session.start', (_$: unknown, e: unknown) => e)
  bottom('turn.complete', () => ({ text: '' }))
  bottom('prompt.submit', (_$: unknown, e: { text: string }) => ({ text: e.text }))
  bottom('process.run', (_$: unknown, e: { argv: string[]; init?: { cwd?: string; timeoutMs?: number } }) => {
    const word = e.argv[2]
    let said: Ran
    if (word === 'contract') {
      game.voiceCalls.push(e.argv)
      said = game.voice()
    } else if (word === 'tools') {
      game.listCalls.push(e.argv)
      said = game.list()
    } else if (word === 'tool') {
      game.runs.push({ argv: e.argv, cwd: e.init?.cwd, timeoutMs: e.init?.timeoutMs })
      said = game.ran()
    } else {
      game.calls.push(e.argv)
      said = game.answer()
    }
    const ran = { stderr: '', isStdoutTruncated: false, isStderrTruncated: false, ...said }

    return { value: ran }
  })
  bottom('tool.register', (_$: unknown, e: Spec) => {
    if (game.isRegisterRefused) throw new Error('no tools here')
    game.registered.push(e)

    return { value: { tool: `mcp__jedicoder__${e.name}` } }
  })
  // Под модулем инструмента нет: вызов, на который модуль не ответил, падает.
  bottom('tool.call', (_$: unknown, e: { tool: string }) => {
    throw new Error(`nobody answers ${e.tool}`)
  })
  bottom('prompt.compose', () => ({ sections: game.sections }))
  bottom('ui.render', { component: 'AbovePrompt' }, ($: any, e: unknown) => {
    const { Text } = $.ui.resolve(e)

    return Text({ children: OTHER })
  })

  return game
}

const start = ($: any) => $.session.start({ cwd: '/work/project' })
const turn = ($: any) =>
  $.turn.complete({ reason: 'answer', answer: '', durationMs: 1, isAborted: false, turnId: 't1' })
const subagentTurn = ($: any) =>
  $.turn.complete({
    reason: 'answer',
    answer: '',
    durationMs: 1,
    isAborted: false,
    turnId: 't2',
    agentId: 'a1',
  })
const typed = ($: any, text: string) =>
  $.prompt.submit({ text, wait: false, origin: { kind: 'composer' } })

// Догадка движка о следующем ответе человека и предложение другого модуля.
const GUESS = 'yes, right here'
const guessed = ($: any) => $.prompt.suggest({ text: GUESS, origin: { kind: 'suggestion' } })
const proposed = ($: any, name: string) =>
  $.prompt.suggest({ text: 'TRY ME', origin: { kind: 'plugin', name } })
const SAY = 'LET US BEGIN'
const saying = (say: string) => snapshot(STEP, true, { say })
const said = (game: Game) => game.shown.filter(e => e.origin.kind === 'plugin').map(e => e.text)

async function texts($: any, surface: string, props = BAND.props) {
  const ui = await $.ui.mount({ ...BAND, props, surface })
  const found = (await ui.findAll({ type: 'Text' })).map((item: { text: string }) => item.text)
  await ui.unmount()

  return found
}

test('the band draws the two lines the game printed, under the band of another module', async ($, on) => {
  engine(on, () => snapshot(STEP))
  await start($)
  for (const surface of ['terminal', 'desktop']) {
    expect(await texts($, surface)).toEqual([OTHER, ...STEP])
  }
})

test('the game is asked by the path of its own plugin, with the session folder', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  expect(game.calls.length).toBe(1)
  const [python, cli, ...rest] = game.calls[0]
  expect(python).toBe('python3')
  expect(cli.endsWith('/lib/jedicoder/cli.py')).toBe(true)
  expect(cli.includes('.jedicoder')).toBe(false)
  expect(rest).toEqual(['face', '--cwd', '/work/project'])
})

test('the band follows the game after every turn', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  game.answer = () => snapshot(['NEXT: quest two'])
  await turn($)
  expect(await texts($, 'terminal')).toEqual([OTHER, 'NEXT: quest two'])
})

test('outside a game session nothing is drawn', async ($, on) => {
  engine(on, () => snapshot([], false))
  await start($)
  await turn($)
  expect(await texts($, 'terminal')).toEqual([OTHER])
})

test('a game command typed in the session is told to the game from then on', async ($, on) => {
  const game = engine(on, () => snapshot([], false))
  await start($)
  await typed($, 'just a question')
  await turn($)
  expect(game.calls[1].includes('--called')).toBe(false)
  await typed($, '/jedicoder:start')
  await turn($)
  expect(game.calls[2].slice(-1)).toEqual(['--called'])
  await typed($, 'another question')
  await turn($)
  expect(game.calls[3].slice(-1)).toEqual(['--called'])
})

test('any failure of the game command is silence, and the session goes on', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  const failures = [
    () => ({ exitCode: 1, stdout: 'Traceback' }),
    () => ({ exitCode: 0, stdout: 'not json' }),
    () => ({ exitCode: 0, stdout: '{"is_game": true, "next": "a string"}' }),
    () => ({ exitCode: 0, stdout: 'null' }),
    () => {
      throw new Error('no python3')
    },
  ]
  for (const failure of failures) {
    game.answer = failure
    expect(await turn($)).toEqual({ text: '' })
    expect(await texts($, 'terminal')).toEqual([OTHER])
  }
  game.answer = () => snapshot(STEP)
  await turn($)
  expect(await texts($, 'terminal')).toEqual([OTHER, ...STEP])
})

test('the band yields to a survey', async ($, on) => {
  engine(on, () => snapshot(STEP))
  await start($)
  expect(await texts($, 'terminal', { ...BAND.props, hasSurvey: true })).toEqual([OTHER])
})

test('a closed quest raises one toast, in the words of the game', async ($, on) => {
  const game = engine(on, () => closed(0))
  await start($)
  game.answer = () => closed(1)
  await turn($)
  expect(game.toasts).toEqual([QUEST_DONE])
  await turn($)
  expect(game.toasts).toEqual([QUEST_DONE])
})

test('a new rank raises one toast, about the rank and not about the quest', async ($, on) => {
  const game = engine(on, () => closed(4))
  await start($)
  game.answer = () => closed(5, 'second')
  await turn($)
  expect(game.toasts).toEqual([RANK_UP])
})

test('nothing changed, nothing is raised', async ($, on) => {
  const game = engine(on, () => closed(2))
  await start($)
  await turn($)
  game.answer = () => snapshot(['NEXT: quest two'], true, { quests_closed: 2 })
  await turn($)
  expect(game.toasts).toEqual([])
})

test('the first snapshot of a session raises nothing', async ($, on) => {
  const game = engine(on, () => closed(3, 'second'))
  await start($)
  expect(game.toasts).toEqual([])
})

test('a session that becomes a game session raises nothing about the past', async ($, on) => {
  const game = engine(on, () => snapshot([], false))
  await start($)
  game.answer = () => closed(3, 'second')
  await turn($)
  expect(game.toasts).toEqual([])
})

test('outside a game session nothing is raised', async ($, on) => {
  const game = engine(on, () => snapshot([], false))
  await start($)
  game.answer = () => snapshot([], false, { quests_closed: 1, rank: 'second', toast_quest: QUEST_DONE })
  await turn($)
  expect(game.toasts).toEqual([])
})

test('a game restarted from zero raises nothing', async ($, on) => {
  const game = engine(on, () => closed(5, 'second'))
  await start($)
  game.answer = () => closed(0)
  await turn($)
  expect(game.toasts).toEqual([])
})

test('a failed game command raises nothing, then and on the turn after', async ($, on) => {
  const game = engine(on, () => closed(0))
  await start($)
  game.answer = () => ({ exitCode: 1, stdout: 'Traceback' })
  expect(await turn($)).toEqual({ text: '' })
  game.answer = () => closed(1)
  expect(await turn($)).toEqual({ text: '' })
  expect(game.toasts).toEqual([])
  // Дальше Лицо живёт как прежде: следующий закрытый квест всплывает.
  game.answer = () => closed(2)
  await turn($)
  expect(game.toasts).toEqual([QUEST_DONE])
})

test('a rank that changed with no quest closed raises nothing', async ($, on) => {
  const game = engine(on, () => closed(5, 'second'))
  await start($)
  game.answer = () => closed(5, 'first')
  await turn($)
  expect(game.toasts).toEqual([])
})

test('a snapshot without captions raises nothing', async ($, on) => {
  const game = engine(on, () => closed(0))
  await start($)
  game.answer = () => {
    const body = { is_game: true, next: STEP, rank: 'second', quests_closed: 1, say: '' }

    return { exitCode: 0, stdout: JSON.stringify(body) }
  }
  await turn($)
  expect(game.toasts).toEqual([])
})

test('a toast the engine refuses is silence, and the band still follows', async ($, on) => {
  const game = engine(on, () => closed(0))
  game.isToastRefused = true
  await start($)
  game.answer = () => snapshot(['NEXT: quest two'], true, { quests_closed: 1 })
  expect(await turn($)).toEqual({ text: '' })
  expect(await texts($, 'terminal')).toEqual([OTHER, 'NEXT: quest two'])
})

test('in a game session the guess of the engine does not reach the prompt box', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  expect(await guessed($)).toEqual({ isShown: false })
  await turn($)
  expect(await guessed($)).toEqual({ isShown: false })
  expect(game.shown).toEqual([])
})

test('a game session with nothing to draw still keeps the guess out', async ($, on) => {
  const game = engine(on, () => snapshot([], true))
  await start($)
  expect(await guessed($)).toEqual({ isShown: false })
  expect(game.shown).toEqual([])
})

test('outside a game session the guess stands as it would without the module', async ($, on) => {
  const game = engine(on, () => snapshot([], false))
  await start($)
  await turn($)
  expect(await guessed($)).toEqual({ isShown: true })
  expect(game.shown).toEqual([{ text: GUESS, origin: { kind: 'suggestion' } }])
})

test('the guess is kept out from the turn the session became a game session', async ($, on) => {
  const game = engine(on, () => snapshot([], false))
  await start($)
  expect(await guessed($)).toEqual({ isShown: true })
  game.answer = () => snapshot(STEP)
  await turn($)
  expect(await guessed($)).toEqual({ isShown: false })
  expect(game.shown.length).toBe(1)
})

test('what another module proposes is not touched, in a game session or outside', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  expect(await proposed($, 'other')).toEqual({ isShown: true })
  game.answer = () => snapshot([], false)
  await turn($)
  expect(await proposed($, 'other')).toEqual({ isShown: true })
  expect(game.shown.map(e => e.origin)).toEqual([
    { kind: 'plugin', name: 'other' },
    { kind: 'plugin', name: 'other' },
  ])
})

test('a failed game command leaves the guess to the engine', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  game.answer = () => ({ exitCode: 1, stdout: 'Traceback' })
  await turn($)
  expect(await guessed($)).toEqual({ isShown: true })
  game.answer = () => {
    throw new Error('no python3')
  }
  await turn($)
  expect(await guessed($)).toEqual({ isShown: true })
  game.answer = () => snapshot(STEP)
  await turn($)
  expect(await guessed($)).toEqual({ isShown: false })
})

test('the phrase of the game is proposed exactly as the game printed it', async ($, on) => {
  const game = engine(on, () => saying(SAY))
  await start($)
  await turn($)
  expect(game.shown).toEqual([{ text: SAY, origin: { kind: 'plugin', name: 'jedicoder' } }])
})

test('the phrase waits for the end of a turn of the main conversation', async ($, on) => {
  const game = engine(on, () => saying(SAY))
  await start($)
  expect(said(game)).toEqual([])
  await subagentTurn($)
  expect(said(game)).toEqual([])
  await turn($)
  expect(said(game)).toEqual([SAY])
})

test('no phrase in the snapshot, nothing is proposed', async ($, on) => {
  const game = engine(on, () => saying(''))
  await start($)
  await turn($)
  game.answer = () => snapshot(STEP, true, { say: 7 })
  await turn($)
  game.answer = () => {
    const body = { is_game: true, next: STEP, rank: 'first', quests_closed: 0 }

    return { exitCode: 0, stdout: JSON.stringify(body) }
  }
  await turn($)
  expect(game.shown).toEqual([])
})

test('outside a game session a phrase is not proposed', async ($, on) => {
  const game = engine(on, () => snapshot([], false, { say: SAY }))
  await start($)
  await turn($)
  expect(game.shown).toEqual([])
})

test('a phrase once shown is not proposed again on every turn', async ($, on) => {
  const game = engine(on, () => saying(SAY))
  await start($)
  await turn($)
  await turn($)
  expect(said(game)).toEqual([SAY])
})

test('a phrase the box could not show is proposed again after the next turn', async ($, on) => {
  const game = engine(on, () => saying(SAY))
  game.isBoxBusy = true
  await start($)
  await turn($)
  expect(said(game)).toEqual([])
  game.isBoxBusy = false
  await turn($)
  await turn($)
  expect(said(game)).toEqual([SAY])
})

test('a phrase that went away and came back is proposed anew', async ($, on) => {
  const game = engine(on, () => saying(SAY))
  await start($)
  await turn($)
  game.answer = () => saying('')
  await turn($)
  game.answer = () => saying(SAY)
  await turn($)
  game.answer = () => saying('ANOTHER')
  await turn($)
  expect(said(game)).toEqual([SAY, SAY, 'ANOTHER'])
})

test('a prompt box that refuses the phrase is silence, and the band still follows', async ($, on) => {
  const game = engine(on, () => saying(SAY))
  game.isBoxBroken = true
  await start($)
  game.answer = () => snapshot(['NEXT: quest two'], true, { say: SAY })
  expect(await turn($)).toEqual({ text: '' })
  expect(await texts($, 'terminal')).toEqual([OTHER, 'NEXT: quest two'])
})

test('a failed game command does not bring a shown phrase back', async ($, on) => {
  const game = engine(on, () => saying(SAY))
  await start($)
  await turn($)
  game.answer = () => ({ exitCode: 1, stdout: 'Traceback' })
  await turn($)
  game.answer = () => saying(SAY)
  await turn($)
  expect(said(game)).toEqual([SAY])
})

test('in a game session the contract is the last section of the system prompt', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  expect(await composed($)).toEqual([...ENGINE_SECTIONS, OWN_SECTION])
  const [python, cli, ...rest] = game.voiceCalls[0]
  expect(python).toBe('python3')
  expect(cli.endsWith('/lib/jedicoder/cli.py')).toBe(true)
  expect(cli.includes('.jedicoder')).toBe(false)
  expect(rest).toEqual(['contract', '--section'])
})

test('outside a game session the system prompt is left as it was, and the contract is not read', async ($, on) => {
  const game = engine(on, () => snapshot([], false))
  await start($)
  await typed($, 'just a question')
  await turn($)
  expect(await composed($)).toEqual(ENGINE_SECTIONS)
  expect(game.voiceCalls).toEqual([])
})

test('the contract is read once, not on every render of the prompt and not on every turn', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  for (let i = 0; i < 3; i++) {
    await typed($, 'a question')
    await composed($)
    await composed($)
    await turn($)
  }
  expect(game.voiceCalls.length).toBe(1)
  // Снимок — на старте, на первом запросе человека и после каждого хода:
  // не на рендер и не на каждый запрос.
  expect(game.calls.length).toBe(1 + 1 + 3)
  expect(await composed($)).toEqual([...ENGINE_SECTIONS, OWN_SECTION])
  expect(game.calls.length).toBe(5)
})

test('the contract is read again when the game says it has changed', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  game.answer = () => snapshot(STEP, true, { contract: 'stamp-two' })
  game.voice = () => spoken('# THE MARKER LINE\n\nanother mode\n', 'stamp-two')
  await turn($)
  expect(game.voiceCalls.length).toBe(2)
  expect((await composed($)).slice(-1)).toEqual([
    { ...OWN_SECTION, text: '# THE MARKER LINE\n\nanother mode\n' },
  ])
  await turn($)
  expect(game.voiceCalls.length).toBe(2)
})

test('the first prompt of a game session brings the contract up to date before the model answers', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  game.answer = () => snapshot(STEP, true, { contract: 'stamp-two' })
  game.voice = () => spoken('# THE MARKER LINE\n\nanother mode\n', 'stamp-two')
  await typed($, 'go on')
  expect((await composed($)).slice(-1)[0].text).toBe('# THE MARKER LINE\n\nanother mode\n')
})

test('a session started by a game command has the contract before the first answer', async ($, on) => {
  const game = engine(on, () => snapshot([], false))
  await start($)
  expect(await composed($)).toEqual(ENGINE_SECTIONS)
  game.answer = () => snapshot(STEP)
  expect(await typed($, '/jedicoder:start')).toEqual({ text: '/jedicoder:start' })
  expect(await composed($)).toEqual([...ENGINE_SECTIONS, OWN_SECTION])
  expect(game.calls[1].slice(-1)).toEqual(['--called'])
})

test('outside a game session a typed prompt runs nothing, and neither does the prompt', async ($, on) => {
  const game = engine(on, () => snapshot([], false))
  await start($)
  await typed($, 'just a question')
  expect(await composed($)).toEqual(ENGINE_SECTIONS)
  expect(game.calls.length).toBe(1)
})

test('a teammate render does not spend the fresh look the next prompt is owed', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  await typed($, 'go on')
  await composed($, ['teammate'])
  expect(game.calls.length).toBe(1)
  await composed($)
  expect(game.calls.length).toBe(2)
})

test('a game called in the middle of a session is looked at before that answer too', async ($, on) => {
  const game = engine(on, () => snapshot([], false))
  await start($)
  await typed($, 'just a question')
  await composed($)
  await turn($)
  game.answer = () => snapshot(STEP)
  await typed($, '/jedicoder:start')
  expect(game.calls.length).toBe(2)
  expect(await composed($)).toEqual([...ENGINE_SECTIONS, OWN_SECTION])
  expect(game.calls.length).toBe(3)
})

test('an empty or failed contract is no section and no error', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  const failures: Game['voice'][] = [
    () => ({ exitCode: 1, stdout: '' }),
    () => ({ exitCode: 0, stdout: '' }),
    () => ({ exitCode: 0, stdout: 'not json' }),
    () => ({ exitCode: 0, stdout: 'null' }),
    () => ({ exitCode: 0, stdout: JSON.stringify({ stamp: STAMP, text: '' }) }),
    () => ({ exitCode: 0, stdout: JSON.stringify({ stamp: STAMP }) }),
    () => ({ ...spoken(), isStdoutTruncated: true }),
    () => {
      throw new Error('no python3')
    },
  ]
  game.voice = failures[0]
  await start($)
  for (const failure of failures) {
    game.voice = failure
    expect(await turn($)).toEqual({ text: '' })
    expect(await composed($)).toEqual(ENGINE_SECTIONS)
  }
  // Команда ожила — раздел встаёт на следующем же снимке.
  game.voice = () => spoken()
  await turn($)
  expect(await composed($)).toEqual([...ENGINE_SECTIONS, OWN_SECTION])
})

test('a game that prints no stamp takes the section away', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  game.answer = () => snapshot(STEP, true, { contract: '' })
  await turn($)
  expect(await composed($)).toEqual(ENGINE_SECTIONS)
  const body = { is_game: true, next: STEP, rank: 'first', quests_closed: 0, say: '' }
  game.answer = () => ({ exitCode: 0, stdout: JSON.stringify(body) })
  await turn($)
  expect(await composed($)).toEqual(ENGINE_SECTIONS)
})

test('a session that stops being a game session loses the section', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  game.answer = () => snapshot([], false)
  await turn($)
  expect(await composed($)).toEqual(ENGINE_SECTIONS)
  game.answer = () => ({ exitCode: 1, stdout: 'Traceback' })
  await turn($)
  expect(await composed($)).toEqual(ENGINE_SECTIONS)
})

test('sections of the engine and of other modules are kept, in their order', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  game.sections = [{ id: 'bare', text: 'ONE LINE', scope: 'session' }]
  expect(await composed($, ['bare'])).toEqual([game.sections[0], OWN_SECTION])
  game.sections = []
  expect(await composed($)).toEqual([OWN_SECTION])
  // Раздел с таким именем уже есть — он один, и это свежий текст.
  game.sections = [{ id: 'jedicoder:contract', text: 'STALE', scope: 'session' }, ENGINE_SECTIONS[2]]
  expect(await composed($)).toEqual([ENGINE_SECTIONS[2], OWN_SECTION])
})

test('the measuring render and a session with no terminal get the section, a teammate does not', async ($, on) => {
  engine(on, () => snapshot(STEP))
  await start($)
  for (const traits of [['analysis'], ['print'], ['lean', 'skills'], ['sdk-preset']]) {
    expect((await composed($, traits)).slice(-1)).toEqual([OWN_SECTION])
  }
  expect(await composed($, ['teammate'])).toEqual(ENGINE_SECTIONS)
})

test('a session started again owes its first prompt a fresh look once more', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  await typed($, 'go on')
  await composed($)
  await typed($, 'and on')
  await composed($)
  expect(game.calls.length).toBe(2)
  await start($)
  await typed($, 'here again')
  await composed($)
  expect(game.calls.length).toBe(4)
})

// --- Инструменты игры ---------------------------------------------------------

test('every tool the game listed is declared, in its words, with the schema up front', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  expect(game.listCalls.length).toBe(1)
  expect(game.listCalls[0].slice(2)).toEqual(['tools'])
  expect(game.listCalls[0][1].endsWith('/lib/jedicoder/cli.py')).toBe(true)
  expect(game.registered).toEqual(
    LISTED.map(({ name, description, inputSchema }) => ({
      name,
      description,
      inputSchema,
      isDeferred: false,
    })),
  )
})

test('tools are declared outside a game session too', async ($, on) => {
  const game = engine(on, () => snapshot([], false))
  await start($)
  expect(game.registered.length).toBe(LISTED.length)
})

test('a tool runs the game command by its name, from the session folder', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  const answer = await $.tool.call({ tool: PROBE })
  expect(game.runs.length).toBe(1)
  const { argv, cwd, timeoutMs } = game.runs[0]
  expect(argv[0]).toBe('python3')
  expect(argv[1].endsWith('/lib/jedicoder/cli.py')).toBe(true)
  expect(argv[1].includes('.jedicoder')).toBe(false)
  expect(argv.slice(2)).toEqual(['tool', 'probe'])
  expect(cwd).toBe('/work/project')
  expect(timeoutMs).toBe(120000)
  expect(answer.deny).toBe(undefined)
  expect(answer.isError).toBe(undefined)
  expect(answer.result).toBe('DONE\n')
  expect(answer.context).toEqual(['exit code: 0'])
})

test('the value of the input rides as one argument, whatever is in it', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  for (const where of ['/home/me/my project', 'a; touch pwned', '$(reboot) `id` && x', '--help', '-rf', '']) {
    game.runs = []
    await $.tool.call({ tool: PLACE, where })
    expect(game.runs[0].argv.slice(2)).toEqual(['tool', 'place', where])
  }
})

test('the name of the quest rides to the command as one argument', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  // Инструмент с обязательным значением `quest`, как его объявляет игра.
  game.list = () =>
    tools([
      {
        name: 'judge',
        description: 'JUDGE THE QUEST',
        inputSchema: {
          type: 'object',
          properties: { quest: { type: 'string', description: 'ITS NAME' } },
          additionalProperties: false,
          required: ['quest'],
        },
        input: ['quest'],
      },
    ])
  await start($)
  expect(game.registered[0].inputSchema).toEqual({
    type: 'object',
    properties: { quest: { type: 'string', description: 'ITS NAME' } },
    additionalProperties: false,
    required: ['quest'],
  })
  for (const quest of ['The Folder', 'An idea for the evening', '"Stop; and undo"']) {
    game.runs = []
    await $.tool.call({ tool: 'mcp__jedicoder__judge', quest })
    expect(game.runs[0].argv.slice(2)).toEqual(['tool', 'judge', quest])
  }
})

test('nothing but the listed input reaches the command', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  await $.tool.call({ tool: PROBE, where: '/x', quest: 'q', command: 'reset' })
  expect(game.runs[0].argv.slice(2)).toEqual(['tool', 'probe'])
  await $.tool.call({ tool: PLACE, command: 'reset', where: '/x', act: '2' })
  expect(game.runs[1].argv.slice(2)).toEqual(['tool', 'place', '/x'])
  // Значения нет или оно не строка — в команду не кладётся ничего.
  await $.tool.call({ tool: PLACE })
  await $.tool.call({ tool: PLACE, where: ['reset', 'confirm'] })
  await $.tool.call({ tool: PLACE, where: 7 })
  expect(game.runs.slice(2).map(run => run.argv.slice(2))).toEqual([
    ['tool', 'place'],
    ['tool', 'place'],
    ['tool', 'place'],
  ])
})

test('a quest that did not close and a check that could not run are answers, not errors', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  for (const exitCode of [1, 2]) {
    game.ran = () => ({ exitCode, stdout: 'NOT YET\n', stderr: 'WHY\n' })
    const answer = await $.tool.call({ tool: PROBE })
    expect(answer.deny).toBe(undefined)
    expect(answer.isError).toBe(undefined)
    expect(answer.result).toBe('NOT YET\nWHY\n')
    expect(answer.context).toEqual([`exit code: ${exitCode}`])
  }
})

test('a command that did not run is an honest refusal, not an answer', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  game.ran = () => {
    throw new Error('timed out')
  }
  const answer = await $.tool.call({ tool: PROBE })
  expect(answer.result).toBe(undefined)
  expect(typeof answer.deny).toBe('string')
  expect(answer.deny.includes('did not run')).toBe(true)
  expect(answer.deny.includes('terminal')).toBe(true)
})

test('after a tool the band follows the game and a closed quest is toasted', async ($, on) => {
  const game = engine(on, () => closed(0))
  await start($)
  game.answer = () => snapshot(['NEXT: quest two'], true, { quests_closed: 1 })
  await $.tool.call({ tool: PROBE })
  expect(game.toasts).toEqual([QUEST_DONE])
  expect(await texts($, 'terminal')).toEqual([OTHER, 'NEXT: quest two'])
  // Ход кончился — второго всплывающего о том же квесте нет.
  await turn($)
  expect(game.toasts).toEqual([QUEST_DONE])
})

test('a tool is a game command called: the session becomes a game session', async ($, on) => {
  const game = engine(on, () => snapshot([], false))
  await start($)
  expect(game.calls[0].slice(2)).toEqual(['face', '--cwd', '/work/project'])
  await $.tool.call({ tool: PROBE })
  expect(game.calls[1].slice(2)).toEqual(['face', '--cwd', '/work/project', '--called'])
})

test('a snapshot that fails after a tool does not spoil the answer', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  game.answer = () => {
    throw new Error('no python here')
  }
  const answer = await $.tool.call({ tool: PROBE })
  expect(answer.result).toBe('DONE\n')
})

test('a tool of that prefix the game did not list is not answered by the module', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  let failure = ''
  try {
    const answer = await $.tool.call({ tool: 'mcp__jedicoder__reset' })
    failure = answer.deny ?? ''
  } catch (error) {
    failure = String(error)
  }
  expect(failure).not.toBe('')
  // Совет идти в терминал — не для инструмента, которого игра не называла.
  expect(failure.includes('terminal')).toBe(false)
  expect(game.runs).toEqual([])
})

for (const [name, list] of [
  ['a command that failed', () => ({ exitCode: 1, stdout: 'Traceback' })],
  ['not json', () => ({ exitCode: 0, stdout: 'hello' })],
  ['not a list', () => tools({ name: 'probe' })],
  ['an empty list', () => tools([])],
  ['a cut answer', () => ({ ...tools(), isStdoutTruncated: true })],
  ['an entry with no words', () => tools([LISTED[0], { name: 'place', input: [] }])],
  ['an entry with a broken input', () => tools([{ ...LISTED[1], input: 'where' }])],
  [
    'a command that throws',
    () => {
      throw new Error('no python here')
    },
  ],
] as const) {
  test(`no tools when the list is ${name}; the rest of the face works`, async ($, on) => {
    const game = engine(on, () => snapshot(STEP))
    game.list = list as Game['list']
    await start($)
    expect(game.registered).toEqual([])
    expect(await texts($, 'terminal')).toEqual([OTHER, ...STEP])
    expect((await composed($)).slice(-1)).toEqual([OWN_SECTION])
    await turn($)
    expect(await texts($, 'terminal')).toEqual([OTHER, ...STEP])
  })
}

test('an engine that refuses tools leaves the face working', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  game.isRegisterRefused = true
  await start($)
  expect(game.registered).toEqual([])
  expect(await texts($, 'terminal')).toEqual([OTHER, ...STEP])
  // Необъявленный инструмент модуль не обслуживает.
  let failure = ''
  try {
    const answer = await $.tool.call({ tool: PROBE })
    failure = answer.deny ?? ''
  } catch (error) {
    failure = String(error)
  }
  expect(failure).not.toBe('')
  // Совет идти в терминал — не для инструмента, которого игра не называла.
  expect(failure.includes('terminal')).toBe(false)
  expect(game.runs).toEqual([])
})

test('a session started again declares the tools again', async ($, on) => {
  const game = engine(on, () => snapshot(STEP))
  await start($)
  game.list = () => tools([LISTED[0]])
  await start($)
  expect(game.registered.length).toBe(LISTED.length + 1)
  let failure = ''
  try {
    const answer = await $.tool.call({ tool: PLACE, where: '/x' })
    failure = answer.deny ?? ''
  } catch (error) {
    failure = String(error)
  }
  expect(failure).not.toBe('')
  // Совет идти в терминал — не для инструмента, которого игра не называла.
  expect(failure.includes('terminal')).toBe(false)
  expect(game.runs).toEqual([])
})
