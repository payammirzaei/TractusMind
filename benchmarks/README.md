# TractusMind Benchmarks

This directory contains fixed evaluation sets used to prevent retrieval regressions.

Current categories include:

- Tractus-X concepts
- EDC coding and configuration
- Debugging and exact identifier lookup
- Architecture and dataspace flows
- Semantic Models / SAMM
- Version-specific questions

`dense_v0.jsonl` is the first retrieval seed. Each case declares the expected source IDs and optional terms that must appear in the same returned chunk.

Run the same indexed hybrid collection through both retrieval modes:

```bash
tractusmind-benchmark --mode both --k 5
```

The current runner reports Recall@K/evidence hit rate, MRR, NDCG@K, first relevant rank, and the top source IDs for every question. Future evaluation layers will add reranker comparisons, citation correctness, answer groundedness, and version correctness.
