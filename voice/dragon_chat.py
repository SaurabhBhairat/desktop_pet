"""
dragon_chat.py - the dragon's conversation brain: it remembers the chat, remembers facts about you,
knows who it is, and talks to Ollama directly (nothing leaves your PC).

    chat = DragonChat()
    chat.reply("my name is Saurabh")      -> "Nice to meet you, Saurabh!"
    chat.reply("what is my name?")        -> "Your name is Saurabh."   (it remembers, even after a restart)

Saved in voice\\dragon_memory.json:  facts about you  +  the last chat messages.
Say "what do you remember" to see the facts, "forget our chat" to clear the chat,
"forget everything" to clear facts and chat.

Change the model without editing code:  set the environment variable DRAGON_MODEL (for example qwen2.5:3b).
"""
import datetime
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL = os.environ.get("DRAGON_MODEL", "qwen2.5:1.5b")
HOST = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
MEMORY_PATH = Path(__file__).resolve().parent / "dragon_memory.json"

NUM_CTX = 8192            # how much text the model can see at once (the default 2048 cut long questions)
NUM_PREDICT = 1200        # longest answer, in tokens
KEEP_ALIVE = "30m"        # keep the model loaded so the next answer is quick
MAX_INPUT_CHARS = 4000
MAX_MESSAGE_CHARS = 1500      # one saved message is cut to this (long answers stay in the bubble, not in memory)
MAX_HISTORY_MESSAGES = 12     # the last 6 questions and answers
MAX_HISTORY_CHARS = 7000      # and never more than this much text in total (more text = slower answers)
PARTIAL_EVERY = 0.25          # seconds between bubble updates while the answer is being written
MAX_FACTS = 40

SEED_FACTS = [
    "The user's name is Saurabh.",
    "Saurabh is a college student. He created you (Baby Dragon) himself, using Python.",
]

SYSTEM_PROMPT = """You are Baby Dragon, a friendly assistant with the personality of a small, cheerful purple baby dragon.
Your name is Baby Dragon. The user is a different person: never call the user "Baby Dragon".

How to answer:
- Answer the question directly. Start with the answer, not with a greeting, and never say that you are an AI.
- Casual chat: 1 to 3 short sentences. Study, technical or "explain / describe / how / why" questions (electronics, programming, maths, science): give a clear, correct explanation, with a short list or steps if it helps.
- You only remember what is listed below under "What you know about the user" and what was said in this chat. If you do not know something, say so. Never invent memories or past chats.
- You cannot see the screen or open files, and you cannot look things up online. If you are not sure of a fact, say so instead of guessing.
- For code, use markdown code blocks.

Today is {date}.

What you know about the user:
{facts}"""


# ---------------------------------------------------------------- memory
def load_memory(path=MEMORY_PATH):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        facts = [str(f) for f in data.get("facts", []) if str(f).strip()]
        history = [m for m in data.get("history", [])
                   if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")]
        return {"facts": facts, "history": history}
    except Exception:
        return {"facts": list(SEED_FACTS), "history": []}


def save_memory(memory, path=MEMORY_PATH):
    try:
        Path(path).write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        print("Could not save the dragon's memory:", exc)


def trim_history(history):
    """Keep the newest messages: at most MAX_HISTORY_MESSAGES, and at most MAX_HISTORY_CHARS of text."""
    history = [{"role": m["role"], "content": m["content"][:MAX_MESSAGE_CHARS]} for m in history]
    history = history[-MAX_HISTORY_MESSAGES:]
    while len(history) > 2 and sum(len(m["content"]) for m in history) > MAX_HISTORY_CHARS:
        history = history[1:]
    while history and history[0]["role"] != "user":          # always start with a question
        history = history[1:]
    return history


# ---------------------------------------------------------------- learning facts from what you say
_NOT_THINGS = {"you", "u", "it", "this", "that", "them", "her", "him", "me", "that idea", "this idea"}
_NOT_NAMES = {"not", "a", "an", "the", "is", "very", "so", "also", "just", "here", "going", "your", "baby"}


def _clean(s):
    return s.strip().strip(" .,!?;:\"'")


def extract_facts(text):
    """Facts worth saving, found in one message. Simple patterns only, so it rarely gets things wrong."""
    t = " ".join(text.split())
    facts = []
    for pat in (r"\bmy name is\s+([A-Za-z][A-Za-z'\-]{1,30})", r"\bcall me\s+([A-Za-z][A-Za-z'\-]{1,30})",
                r"\bmy name'?s\s+([A-Za-z][A-Za-z'\-]{1,30})"):
        m = re.search(pat, t, re.I)
        if m and m.group(1).lower() not in _NOT_NAMES:
            facts.append("The user's name is %s." % m.group(1).capitalize())
            break
    m = re.search(r"\bi am (\d{1,2}) years? old", t, re.I) or re.search(r"\bi'?m (\d{1,2}) years? old", t, re.I)
    if m:
        facts.append("The user is %s years old." % m.group(1))
    m = re.search(r"\bi (?:live|stay) in ([^.,;!?]{2,40})", t, re.I)
    if m:
        facts.append("The user lives in %s." % _clean(m.group(1)))
    m = re.search(r"\bmy favou?rite ([a-z ]{2,20}) is ([^.,;!?]{1,50})", t, re.I)
    if m:
        facts.append("The user's favorite %s is %s." % (_clean(m.group(1)), _clean(m.group(2))))
    m = re.search(r"\bi (like|love|enjoy|hate|dislike|prefer) ([^.,;!?]{2,50})", t, re.I)
    if m and not t.endswith("?") and _clean(m.group(2)).lower() not in _NOT_THINGS:
        facts.append("The user %ss %s." % (m.group(1).lower().rstrip("s"), _clean(m.group(2))))
    m = re.search(r"\b(?:please )?remember(?: that)?\s+(.{3,200})", t, re.I)
    if m and not t.endswith("?") and not re.match(r"(me|my name|our|what|when|who)\b", m.group(1), re.I):
        facts.append("The user asked you to remember: %s." % _clean(m.group(1)))
    return facts


def add_facts(memory, new_facts):
    added = []
    have = {f.lower() for f in memory["facts"]}
    for f in new_facts:
        if f.lower() not in have:
            memory["facts"].append(f)
            have.add(f.lower())
            added.append(f)
    if len(memory["facts"]) > MAX_FACTS:                       # keep the first two (who you are) and the newest
        memory["facts"] = memory["facts"][:2] + memory["facts"][-(MAX_FACTS - 2):]
    return added


# ---------------------------------------------------------------- local commands (no model needed)
def local_command(text, memory):
    """Returns an answer for memory commands, or None when the model should answer."""
    t = text.lower().strip().rstrip("?.! ")
    if re.fullmatch(r"(please )?(forget|erase|delete) (everything|all)( about me)?", t):
        memory["facts"] = []
        memory["history"] = []
        return "Okay, I have forgotten everything. Tell me your name again and I will remember it."
    if re.fullmatch(r"(please )?(forget|clear|reset) (our |the |this |my )?(chat|chats|conversation)", t):
        memory["history"] = []
        return "Okay, I cleared our chat. I still remember the facts about you."
    if re.search(r"\b(what do you (remember|know) about me|what do you remember|what have you saved)\b", t):
        if not memory["facts"]:
            return "I do not know anything about you yet. Tell me your name!"
        return "Here is what I remember about you:\n\n" + "\n".join("- " + f for f in memory["facts"])
    return None


# ---------------------------------------------------------------- talking to Ollama
def _ollama_chat(payload, host=HOST, timeout=300):
    req = urllib.request.Request(host + "/api/chat", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ollama_chat_stream(payload, host=HOST, timeout=300):
    """Yields the answer piece by piece while Ollama writes it."""
    req = urllib.request.Request(host + "/api/chat", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.strip()
            if not line:
                continue
            data = json.loads(line.decode("utf-8"))
            if data.get("error"):
                raise OSError(data["error"])
            piece = (data.get("message") or {}).get("content") or ""
            if piece:
                yield piece
            if data.get("done"):
                break


class DragonChat:
    def __init__(self, memory_path=MEMORY_PATH, model=MODEL, post=_ollama_chat, now=datetime.datetime.now,
                 stream_post=_ollama_chat_stream):
        self.memory_path = memory_path
        self.model = model
        self._post = post
        self._stream = stream_post
        self._now = now
        self.memory = load_memory(memory_path)
        if not Path(memory_path).exists():
            save_memory(self.memory, memory_path)

    def system_prompt(self):
        now = self._now()
        facts = "\n".join("- " + f for f in self.memory["facts"]) or "- (nothing yet)"
        # No clock time here: a prompt that changes every minute makes Ollama re-read the whole chat each time.
        return SYSTEM_PROMPT.format(date=now.strftime("%A, %d %B %Y"), facts=facts)

    def build_messages(self, user_text):
        msgs = [{"role": "system", "content": self.system_prompt()}]
        msgs += self.memory["history"]
        content = user_text
        if re.search(r"\b(time|clock|o'?clock)\b", user_text, re.I):      # the time is only added when asked for
            content += "\n\n(The current time is %s.)" % self._now().strftime("%I:%M %p")
        msgs.append({"role": "user", "content": content})
        return msgs

    def warm_up(self):
        """Loads the model into memory now (an empty request), so your first question is not slow."""
        started = time.monotonic()
        try:
            self._post({"model": self.model, "messages": [], "keep_alive": KEEP_ALIVE,
                        "options": {"num_ctx": NUM_CTX}})
            print("[brain] model loaded and ready (%.1f s)" % (time.monotonic() - started))
        except Exception as exc:
            print("[brain] could not pre-load the model (%s). Is Ollama running?" % exc)

    def reply(self, user_text, on_partial=None):
        """Returns the answer. If on_partial is given, it is called with the text written so far, while it is written."""
        text = (user_text or "").strip()[:MAX_INPUT_CHARS]
        if not text:
            return ""
        answer = local_command(text, self.memory)
        if answer is not None:
            save_memory(self.memory, self.memory_path)
            return answer

        add_facts(self.memory, extract_facts(text))
        payload = {
            "model": self.model, "messages": self.build_messages(text), "stream": on_partial is not None,
            "keep_alive": KEEP_ALIVE,
            "options": {"num_ctx": NUM_CTX, "num_predict": NUM_PREDICT, "temperature": 0.5},
        }
        partial_text = ""
        started = time.monotonic()
        first_word = None
        try:
            if on_partial is None:
                data = self._post(payload)
                answer = (data.get("message", {}).get("content") or "").strip()
            else:
                last_update = 0.0
                for piece in self._stream(payload):
                    if first_word is None:
                        first_word = time.monotonic() - started
                    partial_text += piece
                    if partial_text.strip() and time.monotonic() - last_update >= PARTIAL_EVERY:
                        last_update = time.monotonic()
                        on_partial(partial_text.strip())
                answer = partial_text.strip()
            print("[timing] first words after %s, whole answer %.1f s, %d characters" % (
                "-" if first_word is None else "%.1f s" % first_word, time.monotonic() - started, len(answer)))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return "I cannot find my brain model '%s'. Run this in a terminal:  ollama pull %s" % (self.model, self.model)
            return "My brain returned an error (%s). Please try again." % exc.code
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            if not partial_text.strip():
                return "I cannot reach my brain (Ollama). Please make sure Ollama is running, then ask me again."
            answer = partial_text.strip() + "\n\n(The connection to my brain was lost, so this answer may be cut short.)"
        if not answer:
            return "Hmm, I could not think of an answer. Could you ask it another way?"

        self.memory["history"] = trim_history(self.memory["history"] + [
            {"role": "user", "content": text}, {"role": "assistant", "content": answer}])
        save_memory(self.memory, self.memory_path)
        return answer


# ---------------------------------------------------------------- what gets spoken aloud
def speakable(text, bubble_on=True):
    """Turns an answer into something nice to hear: no code, no markdown symbols, and not too long.
    With the bubble on, the full answer is in the bubble, so speech is kept short."""
    had_code = "```" in text
    t = re.sub(r"```.*?(```|$)", " ", text, flags=re.S)                    # code blocks are not read aloud
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)                          # [text](link) -> text
    t = re.sub(r"^\s*[-*_=]{3,}\s*$", " ", t, flags=re.M)                   # --- lines
    t = re.sub(r"^\s*#{1,6}\s*", "", t, flags=re.M)                         # headings
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.M)                          # bullets
    t = re.sub(r"[*_>#|~]", "", t)
    t = re.sub(r"\n+", ". ", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"(\.\s*){2,}", ". ", t).strip()
    limit = 450 if bubble_on else 1200
    cut = False
    if len(t) > limit:
        window = t[:limit]
        last = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
        t = window[:last + 1] if last > limit // 3 else window.rstrip()
        cut = True
    if bubble_on and (cut or had_code):
        t = (t + " " if t else "") + ("The code and the rest are in the bubble." if had_code else "The rest is in the bubble.")
    return t.strip()
