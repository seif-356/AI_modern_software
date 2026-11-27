"""Shared, crash-safe ceiling for the two additional OpenAI profiles."""
import sqlite3
from contextlib import closing


# Nanodollars per token at the standard, uncached text rate.
RATES = {"gpt-4o-mini-2024-07-18": (150, 600), "gpt-4.1-mini-2025-04-14": (400, 1600)}
CAP = 1_500_000_000


class CreditLimitReached(RuntimeError):
    pass


class CreditLedger:
    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY, model TEXT NOT NULL, amount INTEGER NOT NULL,
                prompt_tokens INTEGER, completion_tokens INTEGER)""")

    def reserve(self, model, messages, output_limit):
        input_rate, output_rate = RATES[model]
        # Each content byte is an upper bound of one text token. Allow ample
        # additional framing tokens for each plain system/user message.
        input_bound = 256 + sum(len(m["content"].encode("utf-8")) + 64 for m in messages)
        bound = input_bound * input_rate + output_limit * output_rate
        with closing(sqlite3.connect(self.path, timeout=60)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            used, = db.execute("SELECT COALESCE(SUM(amount), 0) FROM calls").fetchone()
            if used + bound > CAP:
                raise CreditLimitReached("Combined OpenAI ceiling reached")
            return db.execute("INSERT INTO calls(model, amount) VALUES(?, ?)", (model, bound)).lastrowid

    def settle(self, request, model, usage):
        # Ambiguous failures, interrupted workers and missing usage keep the
        # entire reservation. Discounts are deliberately ignored.
        if usage is None or usage.prompt_tokens is None or usage.completion_tokens is None:
            return
        prompt, output = usage.prompt_tokens, usage.completion_tokens
        if min(prompt, output) < 0:
            raise ValueError("Provider returned negative usage")
        a, b = RATES[model]
        with closing(sqlite3.connect(self.path, timeout=60)) as db, db:
            reserved, = db.execute("SELECT amount FROM calls WHERE id=?", (request,)).fetchone()
            cost = a * prompt + b * output
            db.execute("UPDATE calls SET amount=?, prompt_tokens=?, completion_tokens=? WHERE id=?",
                       (cost, prompt, output, request))
        if cost > reserved:
            raise RuntimeError("Reported cost exceeded the preflight reservation")
