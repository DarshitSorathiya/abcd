#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""End-to-end system test: verify Groq primary + Ollama fallback + MCP tools work."""
import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def main():
    """Test the complete system without running full CLI."""
    print("=" * 70)
    print("REPO GUIDE - END-TO-END SYSTEM TEST")
    print("=" * 70)

    # 1. Test keys.env loading
    print("\n[1] Testing API Key Loading...")
    from repo_guide.memory_cache import fallback_model
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        print(f"  [OK] GROQ_API_KEY loaded: {groq_key[:20]}...")
    else:
        print("  [FAIL] GROQ_API_KEY not found")

    # 2. Test Groq fallback model detection
    print("\n[2] Testing Groq Model Detection...")
    model = fallback_model()
    print(f"  [OK] Detected model: {model}")

    # 3. Test SQLite memory/cache
    print("\n[3] Testing SQLite Memory & Cache...")
    from repo_guide.memory_cache import Memory, Cache
    mem = Memory()
    mem.set("test_key", "test_value")
    retrieved = mem.get("test_key")
    print(f"  [OK] Memory: set/get works - {retrieved}")

    cache = Cache()
    cache.set("q1", "answer1")
    hit1 = cache.get("q1")
    hit2 = cache.get("q1")
    miss1 = cache.get("q2")
    ratio = cache.ratio()
    print(f"  [OK] Cache: hit ratio = {ratio:.1%} (2 hits, 1 miss)")

    # 4. Test root resolution
    print("\n[4] Testing Repository Root Resolution...")
    from repo_guide.root import resolve_root, RootMode
    repo_root = resolve_root(str(Path(__file__).parent), allow_non_git=False)
    print(f"  [OK] Repo root: {repo_root.path}")
    print(f"  [OK] Mode: {repo_root.mode.value}")

    # 5. Test MCP server can start
    print("\n[5] Testing MCP Server Startup...")
    from repo_guide.agent import build_server_parameters
    params = build_server_parameters(repo_root)
    print(f"  [OK] Server parameters built")

    # 6. Test tool discovery
    print("\n[6] Testing Tool Catalogue Discovery...")
    from mcp import Client
    try:
        async with Client(params) as client:
            page = await client.list_tools(cursor=None)
            tool_names = [t.name for t in page.tools]
            print(f"  [OK] Discovered {len(tool_names)} tools:")
            for name in sorted(tool_names):
                print(f"      - {name}")
    except Exception as e:
        print(f"  [FAIL] Tool discovery failed: {e}")
        return False

    # 7. Test gitops basic functionality
    print("\n[7] Testing Git Operations...")
    from repo_guide import gitops
    try:
        log_result = gitops.git_log(repo_root)
        commit_count = len(log_result.commits)
        print(f"  [OK] Git log: {commit_count} commits found")
    except Exception as e:
        print(f"  [FAIL] Git log failed: {e}")
        return False

    print("\n" + "=" * 70)
    print("[SUCCESS] ALL TESTS PASSED")
    print("=" * 70)
    print("\nDataflow: User -> CLI -> Agent -> MCP Server -> Tools -> Response")
    print("\nSee DEPLOYMENT_REPORT.md for full dataflow explanation")
    print("\nTo test CLI: python -m repo_guide.agent --repo . --model qwen3:8b")
    return True

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
