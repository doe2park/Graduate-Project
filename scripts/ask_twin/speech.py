"""Short spoken version of an answer card (what the headset reads aloud), made on the server while the text streams.

The card keeps everything (ids, confidence, evidence, limits). The voice says only:
  - the lead sentence ("Most likely the VAV box, 11 steps along the ducts from here."), and
  - at most one "check first" sentence ("First, trace the duct from here to the VAV box on the mechanical drawings.").
Element ids become plain names ("the VAV box"), the selected element becomes "this"/"here", and markdown, [[ids]],
parentheses, CAD layer codes and "confidence: low" are dropped. Nothing is added that is not in the answer text.

SpokenStream turns the streamed text into 'speak' events as soon as each part's line is complete, so the headset can
start talking before the rest of the card has arrived.
"""
from __future__ import annotations

import re

CITE_RX = re.compile(r'\[\[([A-Za-z0-9_.:-]{1,40})\]\]')
MOCK_TAG = re.compile(r'\s*\*\((?:mock mode)[^)]*\)\*')
HEADER_RX = re.compile(r'^\*\*([A-Za-z ]{2,30}):\*\*\s*(.*)$')
CAD_CODE_RX = re.compile(r'\b[A-Z]-[A-Z]{2,}(?:-[A-Z0-9]+)+\b(?:\s+-\s+)?')
# words that, right after an id, describe the element ("[[x]] VAV box with ...", "[[x]] fire sprinkler piping"): the id is
# then dropped and the description kept; otherwise the id is a noun in the sentence and is read as its plain name
DESCRIBING = {'fire', 'sprinkler', 'vav', 'terminal', 'duct', 'ductwork', 'pipe', 'piping', 'air', 'diffuser', 'light',
              'valve', 'fitting', 'flex', 'spiral', 'rectangular', 'recessed', 'isolation', 'ball', 'supply', 'return', 'hot',
              'cold', 'damper', 'coil', 'reheat', 'ceiling', 'ceilings', 'pipe', 'drain', 'water', 'copper', 'cast'}
IMPERATIVE = {'lift', 'open', 'trace', 'check', 'inspect', 'compare', 'look', 'confirm', 'read', 'ask', 'verify', 'measure',
              'find', 'walk', 'test', 'feel', 'listen', 'shut', 'close', 'turn', 'call', 'review', 'pull', 'see', 'use'}
MAX_PART = 220


def spoken_name(summary: dict | None) -> str:
    """A plain name for an element, as a person would say it ('VAV box', 'duct', 'sprinkler pipe')."""
    if not summary:
        return 'element'
    t, layer, name = (summary.get('type') or ''), (summary.get('layer') or ''), (summary.get('name') or '')
    low = f'{t} {name}'.lower()
    if 'coil kit' in low:
        return 'coil connection kit'
    if 'terminal unit' in low or 'sdv' in low or 'vav' in low:
        return 'VAV box'
    if re.search(r'cdff|diffuser|air outlet|grille|register', low):
        return 'diffuser'
    if 'damper' in low:
        return 'damper'
    if 'valve' in low:
        return 'valve'
    if 'flex drop' in low:
        return 'sprinkler drop'
    if 'sprinkler' in low and 'head' in low:
        return 'sprinkler head'
    if layer == 'duct' or 'duct' in low:
        return 'duct'
    if 'fitting' in low:
        return 'sprinkler fitting' if layer == 'fire' else 'pipe fitting'
    if 'pipe' in low or layer in ('fire', 'plumbing', 'hydronic'):
        return 'sprinkler pipe' if layer == 'fire' else 'pipe'
    if 'recessed' in low or 'fixture' in low or layer == 'lighting':
        return 'light'
    if 'ceiling' in low or layer.startswith('ceilings'):
        return 'ceiling'
    if t and not re.search(r'[A-Z]-[A-Z]{2,}', t):
        return t.lower()
    return 'element'


def _describing(summary: dict | None) -> set:
    words = set(DESCRIBING)
    if summary:
        for v in (summary.get('type'), spoken_name(summary), (summary.get('service_hint') or {}).get('service')):
            words |= {w.lower() for w in re.findall(r'[A-Za-z]+', v or '')}
    return words


def _lc(s: str) -> str:
    """Lower-case the first letter unless the word is an acronym (VAV, AHU)."""
    return s if not s or (len(s) > 1 and s[1].isupper()) else s[0].lower() + s[1:]


def _ids_to_words(s: str, type_of, selected) -> str:
    def rep(m):
        cid, start, rest = m.group(1), m.start(), s[m.end():]
        at_start = not s[:start].strip()
        nxt = re.match(r' ([A-Za-z]+)', rest)
        nxt_word = nxt.group(1).lower() if nxt else ''
        if selected is not None and cid == str(selected):
            return 'This' if at_start else 'here'
        summary = type_of(cid)
        if nxt_word and nxt_word in _describing(summary):
            return '\x00'   # a description follows: drop the id, keep the words
        return 'the ' + spoken_name(summary)
    return CITE_RX.sub(rep, s)


def plain(s: str, type_of=lambda _id: None, selected=None) -> str:
    """One answer line -> plain spoken words."""
    s = MOCK_TAG.sub('', str(s or ''))
    s = _ids_to_words(s, type_of, selected)
    s = s.replace('\x00 ', '').replace('\x00', '')
    s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
    s = re.sub(r'\*(.+?)\*', r'\1', s).replace('*', '')
    s = re.sub(r'\s*·\s*confidence:\s*(low|medium|high)\b', '', s, flags=re.I)
    s = re.sub(r'\bconfidence:\s*(low|medium|high)\b', '', s, flags=re.I)
    s = re.sub(r'\bterminal unit\b', 'VAV box', s, flags=re.I)
    s = re.sub(r'\s*\([^()]*\)', '', s)
    s = CAD_CODE_RX.sub('', s)
    s = re.sub(r'\s+-\s+', ', ', s)
    s = s.replace('~', 'about ').replace('·', ',')
    s = re.sub(r'(?<=[a-z])/(?=[a-z])', ' or ', s)
    s = re.sub(r'(\d)\s?°C\b|(\d)\s?degC\b', lambda m: (m.group(1) or m.group(2)) + ' degrees', s)
    s = re.sub(r'(\d)\s?%', r'\1 percent', s)
    s = re.sub(r'(\d)\s?m\b', r'\1 metres', s)
    s = re.sub(r'\bL(\d)\b', r'level \1', s)
    s = re.sub(r'(?<=\b[Aa] )([A-Z])(?=[a-z])|(?<=\b[Aa]n )([A-Z])(?=[a-z])|(?<=: )([A-Z])(?=[a-z]+[ ,.])',
               lambda m: (m.group(1) or m.group(2) or m.group(3)).lower(), s)
    s = re.sub(r'\b([Aa]) (?=[aeiouAEIOU])', lambda m: m.group(1) + 'n ', s)
    s = re.sub(r'\s+([,.;:!?])', r'\1', s)
    s = re.sub(r'([,;:])(?=[,;:.])', '', s)
    s = re.sub(r'\s+', ' ', s).strip(' ,;:')
    return s


def _sentences(s: str, limit=170) -> str:
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', s)
    out = parts[0]
    for p in parts[1:]:
        if len(out) + 1 + len(p) > limit:
            break
        out += ' ' + p
    return out


def _clip(s: str, n=MAX_PART) -> str:
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(' ', 1)[0].rstrip(' ,;:')
    return cut + '.'


def _end(s: str) -> str:
    s = s.strip()
    return s if not s or s[-1] in '.!?' else s + '.'


def lead_sentence(kind: str, line: str, type_of=lambda _id: None, selected=None) -> str:
    raw = MOCK_TAG.sub('', line).strip()
    m = CITE_RX.match(raw)
    conf = re.search(r'confidence:\s*(low|medium|high)', raw, re.I)
    body = plain(raw, type_of, selected)
    if not body:
        return ''
    if m and (selected is None or m.group(1) != str(selected)) and not body.lower().startswith('the '):
        # the lead starts with the element the answer is about, then its description: "Most likely the VAV box ..."
        hedge = kind == 'Most likely source' or (conf and conf.group(1).lower() != 'high')
        body = ('Most likely the ' if hedge else "It's the ") + _lc(body)
    body = body[0].upper() + body[1:]
    return _clip(_end(_sentences(body)))


def check_sentence(line: str, type_of=lambda _id: None, selected=None) -> str:
    body = plain(line, type_of, selected)
    if not body:
        return ''
    first = body.split(' ', 1)[0].lower().strip(',')
    body = _lc(body)
    body = ('First, ' if first in IMPERATIVE else 'First, check ') + body
    if first == 'then':
        body = 'First, ' + body.split(' ', 2)[-1]
    return _clip(_end(_sentences(body, 200)))


class SpokenStream:
    """Feed streamed answer text; get spoken parts as soon as each line is complete.
    type_of(id) -> element summary dict (or None); selected = the element the question was asked about."""

    def __init__(self, type_of=lambda _id: None, selected=None):
        self.type_of, self.selected = type_of, (str(selected) if selected not in (None, '') else None)
        self.reset()
        self.parts = []

    def reset(self):
        """Forget unspoken text (a live model's preamble before its tool calls is not the answer)."""
        self.buf, self.lead_done, self.check_done, self.in_check, self.loose = '', False, False, False, ''

    def _line(self, line: str):
        line = line.strip()
        if not line or self.check_done:
            return []
        out = []
        h = HEADER_RX.match(line)
        if not self.lead_done:
            if h and h.group(1).strip() in ('Most likely source', 'Answer'):
                text = lead_sentence(h.group(1).strip(), h.group(2), self.type_of, self.selected)
            elif h:
                text = self.loose and lead_sentence('Answer', self.loose, self.type_of, self.selected)   # card without a lead line
            else:
                # plain text before the card (e.g. a live model's "Let me check…"): only a fallback lead, used if no card follows
                self.loose = self.loose or line
                return []
            self.lead_done = True
            if text:
                out.append(('lead', text))
            if not h or h.group(1).strip() in ('Most likely source', 'Answer'):
                return out
        if h:
            name = h.group(1).strip()
            self.in_check = name == 'Check first'
            if self.in_check and h.group(2).strip():
                text = check_sentence(h.group(2), self.type_of, self.selected)
                self.check_done = True
                if text:
                    out.append(('check', text))
            return out
        if self.in_check:
            li = re.match(r'^[-•]\s+(.*)$', line)
            text = check_sentence(li.group(1) if li else line, self.type_of, self.selected)
            self.check_done = True
            if text:
                out.append(('check', text))
        return out

    def feed(self, delta: str):
        self.buf += delta or ''
        out = []
        while '\n' in self.buf:
            line, self.buf = self.buf.split('\n', 1)
            out += self._line(line)
        self.parts += out
        return out

    def finish(self):
        out = self._line(self.buf) if self.buf.strip() else []
        self.buf = ''
        if not self.lead_done and self.loose:
            text = lead_sentence('Answer', self.loose, self.type_of, self.selected)
            self.lead_done = True
            if text:
                out.append(('lead', text))
        self.parts += out
        return out

    @property
    def text(self) -> str:
        return ' '.join(t for _, t in self.parts)


def spoken_text(answer: str, type_of=lambda _id: None, selected=None) -> str:
    s = SpokenStream(type_of, selected)
    s.feed(answer)
    s.finish()
    return s.text


def with_speech(events, type_of=lambda _id: None, selected=None):
    """Wrap an agent event stream: after each text delta that completes a spoken part, add
    {'type': 'speak', 'part': 'lead'|'check', 'text'}; the final event gets 'spoken' (the whole short text)."""
    s = SpokenStream(type_of, selected)
    for ev in events:
        if ev.get('type') == 'final':
            for part, text in s.finish():
                yield {'type': 'speak', 'part': part, 'text': text}
            if not s.parts and ev.get('answer'):   # no streamed text (should not happen): speak from the final answer
                for part, text in (s.feed(ev['answer']) + s.finish()):
                    yield {'type': 'speak', 'part': part, 'text': text}
            ev = dict(ev, spoken=s.text)
            yield ev
            continue
        if ev.get('type') == 'tool' and not s.parts:
            s.reset()   # text so far was a preamble to tool calls
        yield ev
        if ev.get('type') == 'text':
            for part, text in s.feed(ev.get('text', '')):
                yield {'type': 'speak', 'part': part, 'text': text}
