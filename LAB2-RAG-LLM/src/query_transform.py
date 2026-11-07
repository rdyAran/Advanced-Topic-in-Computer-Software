"""
query_transform.py
------------------
Improve the query before retrieval (all need an LLM):

  condense : follow-up question + history -> standalone question (memory)
  rewrite  : slang / casual -> clear formal question
  multi    : generate several paraphrases, retrieve each, fuse with RRF
  hyde     : LLM writes a hypothetical answer, embed THAT instead of the question
"""

from src import prompt_templates as P


def _first_line(text):
    for line in text.splitlines():
        line = line.strip().strip('"').strip()
        if line:
            return line
    return text.strip()


def condense(generator, question, history_turns):
    if not history_turns:
        return question
    prompt = P.CONDENSE_TEMPLATE.format(history=P.format_history(history_turns),
                                        question=question)
    return _first_line(generator.generate(prompt, temperature=0.0)) or question


def rewrite(generator, question):
    out = generator.generate(P.REWRITE_TEMPLATE.format(question=question), temperature=0.0)
    return _first_line(out) or question


def multi_query(generator, question, n=3):
    out = generator.generate(P.MULTI_QUERY_TEMPLATE.format(question=question, n=n),
                             temperature=0.5)
    variants = [l.strip("-•*0123456789. ").strip() for l in out.splitlines()]
    variants = [v for v in variants if v]
    return [question] + variants[:n]


def hyde(generator, question):
    return generator.generate(P.HYDE_TEMPLATE.format(question=question), temperature=0.3)
