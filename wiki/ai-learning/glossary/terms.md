---
title: "AI/ML Glossary"
type: glossary
difficulty: beginner
prerequisites: []
tags:
  - reference
  - terminology
last_updated: "2026-04-09"
sources: []
amprealize_relevance: "Quick reference for AI/ML terminology used across Amprealize's codebase and documentation."
visibility: public
---

# AI/ML Glossary

Quick reference for core terminology. Each entry links to a deeper concept page where available.

---

**Attention** — Mechanism that lets a model weigh the importance of different parts of input relative to each other. Core of the [Transformer](../concepts/attention.md) architecture.

**BCI (Behavior-Conditioned Inference)** — Amprealize's RAG implementation for retrieving and injecting procedural behaviors into agent context. See [BCI In Practice](../in-practice/bci-in-amprealize.md).

**Chain of Thought (CoT)** — Prompting technique that asks the model to show its reasoning step by step, improving accuracy on complex tasks. See [Prompt Engineering](../concepts/prompt-engineering.md).

**Context Window** — Maximum number of tokens a model can process in a single call. Ranges from 4K to 200K+ depending on model.

**Cosine Similarity** — Measure of angle between two vectors. Used to compare [embeddings](../concepts/embeddings.md). Range: -1 (opposite) to 1 (identical).

**Embedding** — Dense vector representation of text that captures semantic meaning. See [Embeddings](../concepts/embeddings.md).

**FAISS** — Facebook AI Similarity Search. Library for efficient nearest-neighbor search over vectors. See [FAISS](../technologies/faiss.md).

**Few-Shot** — Providing examples in the prompt to guide model behavior. Zero-shot = no examples, one-shot = one example.

**Fine-Tuning** — Continuing to train a pre-trained model on domain-specific data. Expensive but bakes knowledge into weights.

**Hallucination** — When a model generates confident but factually incorrect content. Caused by autoregressive generation without knowledge grounding.

**Hybrid Retrieval** — Combining semantic (vector) search with keyword (BM25/TF-IDF) search. See [Hybrid Retrieval](../concepts/hybrid-retrieval.md).

**Inference** — Running a trained model to produce output. See [Inference & Generation](../concepts/inference.md).

**LLM (Large Language Model)** — Neural network with billions of parameters trained on text to predict next tokens. GPT-4, Claude, Llama are LLMs.

**MCP (Model Context Protocol)** — Standard for tools and resources that LLMs can access. Amprealize exposes its functionality as MCP tools.

**Multi-Agent** — System where multiple specialized AI agents collaborate on tasks. See [Multi-Agent Orchestration](../concepts/multi-agent.md).

**RAG (Retrieval-Augmented Generation)** — Pattern of retrieving relevant context before generating to improve accuracy. See [RAG](../concepts/rag.md).

**Temperature** — Parameter controlling randomness in generation. 0 = deterministic, 1 = sample from distribution. See [Inference](../concepts/inference.md).

**Token** — Basic unit of text that LLMs process. ~4 characters or ¾ of a word. See [Tokenization](../concepts/tokenization.md).

**Top-p (Nucleus Sampling)** — Sampling strategy that considers tokens until cumulative probability exceeds p. See [Inference](../concepts/inference.md).

**Transformer** — Neural network architecture based on self-attention. Foundation of all modern LLMs. See [Transformers](../concepts/transformers.md).

**Vector Database** — Storage system optimized for similarity search over embedding vectors. See [FAISS](../technologies/faiss.md).
