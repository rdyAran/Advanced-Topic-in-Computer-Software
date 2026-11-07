"""
rag_pipeline.py
---------------
Orchestrator — wires every stage together:

 User question
   -> (memory: condense follow-up)        USE_MEMORY + USE_LLM
   -> (query_transform)                   USE_QUERY_TRANSFORM
   -> hybrid_retriever (BM25+dense, RRF)  top CANDIDATE_K
   -> (rerankers: cross-encoder)          USE_RERANK  -> TOP_K
   -> generator (LLM)                     USE_LLM
   -> answer + citations [1] [2]
   -> save turn to memory
"""

from src import prompt_templates as P
from src import query_transform as QT
from src.generator import Generator, LLMError
from src.hybrid_retriever import HybridRetriever
from src.memory import ConversationMemory


class RAGPipeline:
    def __init__(self, cfg, verbose=True):
        self.cfg = cfg
        self.retriever = HybridRetriever(
            model_name=cfg.EMBEDDING_MODEL_NAME,
            index_path=cfg.FAISS_INDEX_FILE,
            chunk_store_path=cfg.CHUNK_STORE_FILE,
            bm25_path=cfg.BM25_INDEX_FILE,
            rrf_k=cfg.RRF_K,
            use_hybrid=cfg.USE_HYBRID,
        )

        self.reranker = None
        if cfg.USE_RERANK:
            from src.rerankers import CrossEncoderReranker
            self.reranker = CrossEncoderReranker(cfg.RERANKER_MODEL_NAME)

        self.generator = None
        self.llm_error = None
        if cfg.USE_LLM:
            try:
                self.generator = Generator.from_config(cfg)
                if verbose:
                    print(f"[generator] LLM: {cfg.LLM_PROVIDER} / "
                          f"{cfg.LLM_MODELS[cfg.LLM_PROVIDER]}")
            except LLMError as e:
                self.llm_error = str(e)
                print(f"[generator] LLM disabled: {e}")

        self.memory = ConversationMemory(cfg.MEMORY_TURNS)

    # ------------------------------------------------------------------
    def _transform_query(self, question):
        """returns (queries: list[str], hyde_text: str|None, standalone: str)"""
        cfg, gen = self.cfg, self.generator
        standalone = question

        if gen and cfg.USE_MEMORY and not self.memory.is_empty():
            standalone = QT.condense(gen, question, self.memory.get())

        if not (gen and cfg.USE_QUERY_TRANSFORM):
            return [standalone], None, standalone

        mode = cfg.QUERY_TRANSFORM_MODE
        if mode == "rewrite":
            return [QT.rewrite(gen, standalone)], None, standalone
        if mode == "multi":
            return QT.multi_query(gen, standalone), None, standalone
        if mode == "hyde":
            return [standalone], QT.hyde(gen, standalone), standalone
        return [standalone], None, standalone

    def retrieve(self, question, top_k=None, mode=None):
        """retrieval only (also used by evaluation)"""
        cfg = self.cfg
        top_k = top_k or cfg.TOP_K
        queries, hyde_text, standalone = self._transform_query(question)
        n_candidates = cfg.CANDIDATE_K if self.reranker else max(top_k, cfg.CANDIDATE_K)

        if hyde_text:
            vec = self.retriever.dense.embedding_model.encode_query(hyde_text)
            results = self.retriever.retrieve(standalone, n_candidates, query_vector=vec, mode=mode)
        elif len(queries) > 1:
            lists = [self.retriever.retrieve(q, n_candidates, mode=mode) for q in queries]
            results = self.retriever.fuse(lists, n_candidates)
        else:
            results = self.retriever.retrieve(queries[0], n_candidates, mode=mode)

        if self.reranker:
            results = self.reranker.rerank(standalone, results, top_k)
        else:
            results = results[:top_k]

        return results, {"standalone": standalone, "queries": queries, "hyde": hyde_text}

    def ask(self, question):
        cfg = self.cfg
        chunks, debug = self.retrieve(question)

        if not chunks:
            answer = "ไม่พบข้อมูลนี้ในฐานความรู้"
        elif self.generator:
            prompt = P.ANSWER_TEMPLATE.format(context=P.format_context(chunks),
                                              question=debug["standalone"])
            try:
                answer = self.generator.generate(prompt, system=P.SYSTEM_PROMPT)
            except LLMError as e:
                print(f"[generator] Error: {str(e)[:200]}")
                answer = ("(LLM ไม่พร้อมใช้งานตอนนี้ — แสดงคำตอบที่ใกล้เคียงที่สุดจากฐานข้อมูลแทน)\n"
                          + chunks[0]["answer"] + " [1]")
        else:
            # non-LLM mode: return the best retrieved answer (no mock generation)
            answer = chunks[0]["answer"] + " [1]"

        if cfg.USE_MEMORY:
            self.memory.add(question, answer)

        return {"question": question, "answer": answer, "sources": chunks, "debug": debug}
