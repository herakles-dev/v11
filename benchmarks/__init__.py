"""
V11 Benchmark System — tracks quality over time with composite scoring.

Three tiers:
  0: Smoke ($0, every commit) — hooks, tasks, schemas, latency
  1: Integration (~$0.30, daily) — real claude -p with Haiku
  2: Full (~$15, weekly) — SWE-bench through V11 CLI
"""

__version__ = "1.0.0"
