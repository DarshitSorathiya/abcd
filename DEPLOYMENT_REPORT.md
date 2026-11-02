# Repo Guide - Deployment Report & Analysis

## Project Overview

**What is this project?**

Repo Guide is a local, read-only repository onboarding assistant that helps developers understand codebases by answering questions about code structure, history, and issues. It combines:
- An MCP (Model Context Protocol) server exposing safe, bounded repository tools
- An AI agent using local Ollama or cloud Groq API to interpret questions and call tools
- Verification layer to ensure answers cite real code/commits

**In simple words:** You ask "Where is authentication handled?" and it searches the repo, reads relevant files, checks git history, and answers with exact file paths and line numbers.

## Use Cases Beyond Repository Questions

While designed for repository onboarding, this architecture can be extended to:

1. **Documentation Q&A**: Index docs and answer questions about internal wikis, API specs
2. **Code Review Assistant**: Analyze PRs, suggest improvements based on project patterns
3. **Compliance Checker**: Scan codebases for security patterns, licensing issues
4. **Migration Helper**: Find all uses of deprecated APIs, suggest replacements
5. **Onboarding Automation**: Generate personalized learning paths for new developers
6. **Technical Debt Tracker**: Identify patterns like TODOs, code smells, test gaps

## Architecture: Servers vs Tools

### Servers Built

1. **Built-in MCP Server** (`src/repo_guide/server.py`)
   - Exposes 6 read-only repository tools via MCP protocol
   - Runs as subprocess with stdio transport
   - Bound to single repository root for safety

2. **Custom Server** (`src/repo_guide/custom_server.py`)
   - Adds memory/cache/Groq integration
   - Can be extended with custom tools
   - Currently unified entry point

### Tools Available

**From Built-in MCP Server:**
1. `list_tree` - List directory contents (max depth 4, bounded entries)
2. `read_file` - Read UTF-8 text files (with line ranges, size limits)
3. `search_code` - Search file contents with bounded results
4. `git_log` - Show commit history (bounded, hash-only references)
5. `repo_overview` - Get repository structure summary
6. `list_issues` - Fetch public GitHub issues (unauthenticated, bounded)

**Difference between Servers and Tools:**
- **Server** = The process that hosts and exposes tools over a protocol (MCP)
- **Tool** = Individual function the agent can call (like `list_tree`, `read_file`)
- One server can expose multiple tools
- The agent discovers tools dynamically and chooses which to call

Think of it like a restaurant:
- **Server** = The waiter who takes orders and brings food
- **Tools** = The menu items (burger, pizza, salad)

## Dataflow: User Query to Response

### Current Architecture (Local stdio MCP)

```
┌─────────────────────────────────────────────────────────────────┐
│ USER                                                            │
│   Inputs: "Where is authentication handled?"                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ CLI AGENT (agent.py:main)                                       │
│  1. Resolves repository root                                    │
│  2. Creates OllamaClient or GroqClient                         │
│  3. Starts MCP server as subprocess                             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ MCP CLIENT (mcp SDK)                                            │
│  - Connects to server via stdio (stdin/stdout pipes)            │
│  - Calls client.list_tools() to discover available tools        │
│  - Returns tool catalogue to agent                              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ AGENT LOOP (agent.py:run_agent_turn)                           │
│  Step 1: Send question + tool catalogue to LLM                  │
│    → LLM returns: {"action":"search_code","args":{"query":"auth"}}│
│  Step 2: Validate arguments against tool schema                 │
│  Step 3: Call MCP client.call_tool("search_code", {...})       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ MCP SERVER (server.py)                                          │
│  - Receives tool call over stdio                                │
│  - Executes bounded safe operation:                             │
│    * resolve_repo_path() - validate path in repo                │
│    * deny symlinks, sensitive files (.env, .git)                │
│    * cap file sizes, entry counts                               │
│  - Returns result as JSON over stdio                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ AGENT LOOP (continued)                                          │
│  Step 4: Receive tool result from MCP server                    │
│  Step 5: Add to evidence ledger                                 │
│  Step 6: If more steps needed, repeat from Step 1               │
│  Step 7: LLM returns: {"action":"final","answer":"..."}        │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ VERIFICATION (verify.py)                                        │
│  - Extract citations from answer (file:line format)             │
│  - Read cited files to verify claims match actual code          │
│  - Flag hallucinations, missing citations                       │
│  - Return verified answer or request reflection                 │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ USER                                                            │
│   Output: "Authentication is handled in src/auth.py:45-67      │
│           using JWT tokens validated in middleware.py:12"       │
└─────────────────────────────────────────────────────────────────┘
```

### Code-Level Dataflow

**1. User Input → Agent**
```python
# agent.py:main()
question = sys.stdin.readline()  # User types question
context = resolve_root(args.repo)  # Find git repo root
ollama = OllamaClient(settings)   # Create LLM client
```

**2. Agent → MCP Server Startup**
```python
# agent.py:_run_turn_with_server()
parameters = build_server_parameters(context)
# parameters = StdioServerParameters(
#   command="python",
#   args=["-m", "repo_guide.server", "--repo", "/path/to/repo"]
# )
async with Client(parameters) as client:
    catalogue = await discover_tools(client, settings)
    # catalogue = [
    #   ToolDefinition("list_tree", "List directory...", {...schema}),
    #   ToolDefinition("read_file", "Read a file...", {...schema}),
    #   ...
    # ]
```

**3. Agent Loop → LLM Decision**
```python
# agent.py:run_agent_turn()
user_prompt = (
    f"User question: {question}\n"
    f"Available tools: {json.dumps(catalogue)}\n"
    f"Recent observations: {ledger.context_text()}"
)
response = await ollama.chat([
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": user_prompt}
])
action = parse_action(response)  
# action = {"action": "search_code", "args": {"query": "authentication"}}
```

**4. Agent → MCP Server Tool Call**
```python
# agent.py:run_agent_turn() continued
result = await client.call_tool(
    "search_code", 
    {"query": "authentication", "path": "src"}
)
# This sends JSON-RPC over stdin to server subprocess:
# {"method": "tools/call", "params": {"name": "search_code", "arguments": {...}}}
```

**5. MCP Server Executes Tool**
```python
# server.py:_handle_search_code()
async def _handle_search_code(context, query, path, limit):
    safe_path = resolve_repo_path(context, path)  # Validate path
    # Reject: symlinks, paths outside repo, sensitive files
    matches = gitops.search_content(context, query, safe_path, limit)
    # Bounded: max 100 results, max 10k chars per match
    return matches
# Returns JSON to agent over stdout
```

**6. Agent Records Evidence**
```python
# agent.py:run_agent_turn() continued
ledger.record("search_code", arguments, payload, is_error=False)
# ledger.observations = [
#   Observation(tool="search_code", result={...}, generation=1)
# ]
```

**7. Agent → LLM Final Answer**
```python
# After multiple tool calls, LLM returns final action
action = {"action": "final", "answer": "Authentication is in src/auth.py:45"}
```

**8. Verification**
```python
# verify.py:verify_and_reflect()
citations = extract_citations(answer)
# citations = [Citation(path="src/auth.py", start_line=45, end_line=67)]
for cite in citations:
    actual_content = read_file(context, cite.path, cite.start_line, cite.end_line)
    # Verify claim matches actual code
verified_answer = sanitize_answer(answer, verified_citations)
```

**9. Output to User**
```python
# agent.py:main() continued
print(result.answer, file=sys.stdout)
# User sees: "Authentication is handled in src/auth.py:45-67..."
```

### HTTP Alternative (Not Currently Implemented)

If this were HTTP instead of stdio:

```
┌──────────┐  HTTP POST /query      ┌──────────────┐
│  Client  │ ────────────────────>  │  Agent API   │
│  (Web)   │  {"question": "..."}   │  (FastAPI)   │
└──────────┘                         └──────┬───────┘
                                            │
                                            ▼
                                     ┌──────────────┐
                                     │  MCP Client  │
                                     │  (SSE/HTTP)  │
                                     └──────┬───────┘
                                            │ HTTP POST
                                            ▼
                                     ┌──────────────┐
                                     │  MCP Server  │
                                     │  (REST API)  │
                                     └──────────────┘
```

**Key differences:**
- stdio: Subprocess pipes, single-user, local-only
- HTTP: Network transport, multi-user, can be remote
- stdio: Lower latency, simpler auth (none needed)
- HTTP: Load balancing, scaling, authentication required

**To make it HTTP:** 
1. Replace `StdioServerParameters` with HTTP endpoint URL
2. Use SSE (Server-Sent Events) for streaming tool results
3. Add authentication layer (JWT, API keys)
4. Deploy MCP server separately from agent

## Current Issues & Fixes Applied

### Issue 1: Syntax Error in github_api.py ✅ FIXED
**Problem:** Duplicate `_retry_with_backoff` definition, missing `Callable` import, broken indentation in `list_issues`
**Fix:** Removed duplicate, added `Callable` to imports, fixed try/except/finally structure

### Issue 2: Test Failure in test_m2_gitops.py ⚠️ IN PROGRESS
**Problem:** `list_tree` filters out `.git` but still counts it toward truncation, causing `a.txt` to be excluded
**Root Cause:** `heapq.nsmallest` fetches entries before filtering, then truncation logic counts all fetched entries including excluded ones
**Fix Needed:** Filter excluded directories BEFORE counting for truncation

### Issue 3: Groq Model Deprecation ✅ FIXED
**Problem:** `llama3-70b-8192` model was decommissioned
**Fix:** Updated to `qwen/qwen3.8-27b` (current valid model)

### Issue 4: API Key Not Loaded from Environment ✅ FIXED
**Problem:** Hardcoded API key in code instead of reading from env
**Fix:** Load from `GROQ_API_KEY` environment variable

### Issue 5: CLI Hangs on Startup ⚠️ INVESTIGATING
**Problem:** `repo-guide --repo . --model qwen3:8b` hangs after "Question>"
**Likely Cause:** Ollama connection timeout or MCP server stdio deadlock
**Next Steps:** Add timeout, debug stdio communication

## Pre-Built MCP Service Integration

**Status:** Repo Guide already includes 6 pre-built MCP tools (see "Tools Available" section above)

**To add another service** (example: Weather MCP):
1. Install MCP server: `pip install mcp-server-weather`
2. Modify `agent.py:build_server_parameters()` to start multiple servers
3. Agent discovers all tools from all servers
4. LLM chooses appropriate tool for query

**Example addition:**
```python
# In agent.py
async def discover_all_tools(contexts):
    all_tools = []
    # Built-in repo tools
    async with Client(build_server_parameters(repo_context)) as repo_client:
        all_tools.extend(await discover_tools(repo_client))
    # Weather service
    async with Client(weather_server_parameters()) as weather_client:
        all_tools.extend(await discover_tools(weather_client))
    return all_tools
```

## Deployment Checklist

- [x] Syntax errors fixed in all Python files
- [x] Groq API integration with valid model
- [x] API key loaded from environment
- [ ] Test suite passing (1 test still failing)
- [ ] CLI runs end-to-end without hanging
- [ ] Memory/cache SQLite DB working
- [ ] Groq primary, Ollama fallback working
- [ ] Documentation complete (this file)

## Next Steps to Make It Production-Ready

1. **Fix test_m2_gitops.py failure** - Adjust truncation logic in `list_tree`
2. **Debug CLI hang** - Add timeout, verify Ollama connectivity
3. **Load Groq key from src/repo_guide/keys.env** - Add dotenv loader
4. **End-to-end test** - Run actual query and verify response
5. **Add health checks** - Verify Ollama/Groq connectivity on startup
6. **Improve error messages** - Surface root cause when tools fail
7. **Add logging** - Debug agent decisions and tool calls
8. **Rate limiting** - Prevent API abuse for Groq calls
9. **Caching** - Store common queries in SQLite cache
10. **Monitoring** - Track cache hit ratio, tool latency

---

**Generated:** 2026-11-01  
**Status:** Deployment-ready pending final fixes  
**Contact:** See CLAUDE.md for contribution guidelines
