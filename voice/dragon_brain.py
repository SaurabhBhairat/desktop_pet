"""
dragon_brain.py - the dragon's inner life: needs, moods and what it decides to do.

Pure Python (no Qt), so it is easy to test. The window calls tick() once a second
and acts on the events it returns:

    ("activity", "wander" | "fly" | "sleep" | "sit")
    ("mood",     "happy" | "excited" | "curious" | "bored" | "sad" | "sleepy")
    ("say",      "lonely")          # reserved: the dragon wants to start a chat

Needs:   energy (drops while awake, refills while asleep)
         happiness
         loneliness (grows while you ignore it, drops when you talk or touch it)
"""
import datetime
import random

# How fast things change, per second. Raise SPEED to watch it all happen quickly.
SPEED = 1.0
DRAIN = 0.0007 * SPEED        # energy lost while awake (about 15 min from 0.85 to 0.2)
RECHARGE = 0.005 * SPEED      # energy gained while asleep (about 2-3 min from 0.2 to 0.9)
LONELY = 0.0015 * SPEED       # loneliness gained per second (about 8 min to "sad")

MOODS = ("happy", "excited", "curious", "bored", "sad", "sleepy")
ACTIVITIES = ("wander", "fly", "sleep", "sit")


class DragonBrain:
    def __init__(self, rng=None, hour_fn=None):
        self.rng = rng or random.Random()
        self.hour_fn = hour_fn or (lambda: datetime.datetime.now().hour)
        self.energy = 0.85
        self.happiness = 0.7
        self.loneliness = 0.1
        self.activity = "wander"
        self.mood = "happy"
        self._activity_left = self.rng.uniform(20, 45)
        self._curious_left = 0.0
        self._forced_mood_left = 0.0
        self._say_cooldown = 240.0

    # ---------------- outside world ----------------
    def on_interaction(self, kind):
        """kind: 'talk' (you spoke to it) or 'touch' (you clicked/dragged it)."""
        events = []
        if kind == "talk":
            self.happiness = min(1.0, self.happiness + 0.25)
            self.loneliness = max(0.0, self.loneliness - 0.6)
        else:
            self.happiness = min(1.0, self.happiness + 0.06)
            self.loneliness = max(0.0, self.loneliness - 0.2)
        if self.activity in ("sleep", "fly", "sit"):
            self.energy = max(self.energy, 0.4)           # being woken up
            self._set_activity("wander", events, self.rng.uniform(20, 45))
        self._refresh_mood(events)
        return events

    def force_activity(self, name, seconds=40.0):
        events = []
        if name == "sleep":
            self.energy = min(self.energy, 0.2)
        self._set_activity(name, events, seconds)
        return events

    def force_mood(self, name, seconds=25.0):
        events = []
        self._forced_mood_left = seconds
        if name != self.mood:
            self.mood = name
            events.append(("mood", name))
        return events

    # ---------------- time passes ----------------
    def tick(self, dt, busy=False):
        events = []
        if busy:                                         # we are in a conversation
            self.loneliness = max(0.0, self.loneliness - 0.05 * dt)
            if self.activity != "wander":
                self._set_activity("wander", events, 30.0)
            self._refresh_mood(events)
            return events

        sleeping = self.activity == "sleep"
        if sleeping:
            self.energy = min(1.0, self.energy + RECHARGE * dt)
        else:
            self.energy = max(0.0, self.energy - DRAIN * dt)
        self.loneliness = min(1.0, self.loneliness + LONELY * dt * (0.3 if sleeping else 1.0))

        target = 0.75 - 0.55 * self.loneliness
        self.happiness += (target - self.happiness) * min(1.0, 0.01 * dt)
        self.happiness = max(0.0, min(1.0, self.happiness))

        self._activity_left -= dt
        self._forced_mood_left = max(0.0, self._forced_mood_left - dt)

        night = self.hour_fn() >= 23 or self.hour_fn() < 6
        if sleeping:
            if self.energy >= 0.9 and self._activity_left <= 0:
                self._set_activity("wander", events, self.rng.uniform(30, 60))
        elif self.energy < 0.2 or (night and self.energy < 0.6 and self.rng.random() < 0.01 * dt):
            self._set_activity("sleep", events, 60.0)
        elif self._activity_left <= 0:
            self._pick_next(events)

        # a little curiosity now and then
        if self._curious_left > 0:
            self._curious_left = max(0.0, self._curious_left - dt)
        elif self.mood == "happy" and self.rng.random() < 0.004 * dt:
            self._curious_left = self.rng.uniform(15, 25)

        self._say_cooldown = max(0.0, self._say_cooldown - dt)
        if self.loneliness > 0.7 and self._say_cooldown <= 0 and not sleeping:
            self._say_cooldown = 300.0
            events.append(("say", "lonely"))

        self._refresh_mood(events)
        return events

    # ---------------- internals ----------------
    def _compute_mood(self):
        if self._forced_mood_left > 0:
            return self.mood
        if self.activity == "sleep" or self.energy < 0.3:
            return "sleepy"
        if self.loneliness > 0.7 or self.happiness < 0.3:
            return "sad"
        if self.loneliness > 0.4:
            return "bored"
        if self.happiness > 0.85:
            return "excited"
        if self._curious_left > 0:
            return "curious"
        return "happy"

    def _refresh_mood(self, events):
        new = self._compute_mood()
        if new != self.mood:
            self.mood = new
            events.append(("mood", new))

    def _set_activity(self, name, events, seconds):
        self._activity_left = seconds
        if name != self.activity:
            self.activity = name
            events.append(("activity", name))

    def _pick_next(self, events):
        w = {"wander": 5.0, "fly": 1.0, "sit": 1.0}
        if self.mood in ("happy", "excited"):
            w["fly"] += 3.0 if self.mood == "happy" else 5.0
        if self.mood in ("sad", "bored"):
            w["sit"] += 5.0
            w["fly"] = 0.0
            w["wander"] = 2.0
        if self.mood == "sleepy":
            w["sit"] += 4.0
            w["fly"] = 0.0
        names = list(w)
        choice = self.rng.choices(names, weights=[w[n] for n in names])[0]
        seconds = {"wander": (25, 60), "fly": (15, 30), "sit": (15, 30)}[choice]
        self._set_activity(choice, events, self.rng.uniform(*seconds))
        if choice == self.activity and not events:
            # same activity picked again: just restart its timer
            pass