"""
memory.py
---------
Conversation history: keep only the last N turns (default 6),
used to understand follow-up questions such as "แล้วต้องเปลี่ยนบ่อยแค่ไหน".
"""

from collections import deque


class ConversationMemory:
    def __init__(self, max_turns=6):
        self.turns = deque(maxlen=max_turns)

    def add(self, question, answer):
        self.turns.append({"question": question, "answer": answer})

    def get(self):
        return list(self.turns)

    def is_empty(self):
        return len(self.turns) == 0

    def clear(self):
        self.turns.clear()
