#!/usr/bin/env python
"""
Claude CLI Integration with Repo-Guide MCP Server

Usage:
    python claude-repo.py "Your question about the repository"

This script:
1. Starts the repo-guide MCP server
2. Connects to it as a client
3. Sends your question
4. Uses Ollama to get answers
5. Cleans up
"""

import subprocess
import sys
import json
import asyncio
from pathlib import Path

# Configuration
REPO_PATH = "C:\\Users\\mahip\\OneDrive\\Desktop\\Projectttttttttt\\abcd"
OLLAMA_MODEL = "qwen3:8b"  # or al:7mistrb for faster responses

async def ask_repo_question(question: str) -> str:
    """Send a question to the repo and get an answer using Ollama."""
    try:
        # Read repo overview files
        import os
        files_to_read = ["README.md", "pyproject.toml"]

        context_parts = []
        for filename in files_to_read:
            filepath = Path(REPO_PATH) / filename
            if filepath.exists():
                content = filepath.read_text(encoding="utf-8")
                context_parts.append(f"=== {filename} ===\n{content[:2000]}\n")

        # Create a simple prompt (bypassing MCP, using direct file access)
        prompt = f"""You are a helpful assistant helping a user understand their codebase.
Answer this question about the repository at {REPO_PATH}:

Question: {question}

Relevant repository files:
{chr(10).join(context_parts)}

Provide a concise, helpful answer based on the repository files."""

        # Call Ollama directly
        import requests

        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            },
            timeout=(5, 60)
        )

        if response.status_code == 200:
            data = response.json()
            return data.get('message', {}).get('content', 'No response')
        else:
            return f"Error: Ollama returned {response.status_code}"

    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"

def main():
    if len(sys.argv) < 2:
        print("Usage: python claude-repo.py \"Your question here\"")
        print("Example: python claude-repo.py \"What is this project about?\"")
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    print(f"Question: {question}\n")
    print("Thinking...\n")

    answer = asyncio.run(ask_repo_question(question))
    print(f"Answer:\n{answer}")

if __name__ == "__main__":
    main()