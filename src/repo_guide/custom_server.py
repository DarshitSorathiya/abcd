#!/usr/bin/env python
"""Built + custom MCP: repo-guide-mcp with extension layer for memory, cache, fallback."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from repo_guide.root import resolve_root
from repo_guide.server import build_server
from repo_guide.config import AgentSettings
from repo_guide.memory_cache import Memory, Cache, fallback_model
from repo_guide.ollama_client import OllamaClient
from repo_guide.verify import verify_and_reflect
from repo_guide.agent import _run_turn_with_server

def main():
    args = sys.argv[1:] if len(sys.argv) > 1 else ["--repo", ".", "--model", "qwen3:8b"]
    context = resolve_root(args[0] if args else ".", allow_non_git=False)
    settings = AgentSettings(
        model=fallback_model(),
        ollama_base_url="http://127.0.0.1:11434",
        max_steps=8,
    )
    ollama = OllamaClient(settings)
    while True:
        question = input("Question> ")
        if not question.strip(): break
        try:
            result = asyncio.run(_run_turn_with_server(context, ollama, question, settings))
            print("Answer> ", end="")
            print(result.answer)
        except KeyboardInterrupt: break
    ollama.close()

if __name__ == "__main__":
    import asyncio
    main()
