# Hacxgent

[![PyPI Version](https://img.shields.io/pypi/v/hacxgent)](https://pypi.org/project/hacxgent)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/release/python-3120/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

```text
██╗  ██╗ █████╗  ██████╗██╗  ██╗ ██████╗ ███████╗███╗   ██╗████████╗
██║  ██║██╔══██╗██╔════╝╚██╗██╔╝██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
███████║███████║██║      ╚███╔╝ ██║  ███╗█████╗  ██╔██╗ ██║   ██║   
██╔══██║██╔══██║██║      ██╔██╗ ██║   ██║██╔══╝  ██║╚██╗██║   ██║   
██║  ██║██║  ██║╚██████╗██╔╝ ██╗╚██████╔╝███████╗██║ ╚████║   ██║   
╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   
```

**The Professional CLI Coding Agent for Precision Engineering.**

Hacxgent is a high-performance, open-source CLI coding assistant designed for deep interaction with local codebases. Built for precision and speed, it features **industry-leading smart memory management**, an **expanded toolset**, and **zero provider lock-in** (use any OpenAI-compatible API completely free).

Hacxgent goes beyond simple chat—it is an autonomous agent capable of structural analysis, surgical code modification, and long-horizon task execution with unmatched context efficiency.

---

## 🌟 Key Innovations

1. **Smart Context Compaction**: Normal agents read a file and leave the massive output in the context window, quickly exhausting memory. Hacxgent intelligently compresses these histories. Heavy tool outputs are surgically replaced with tiny memory markers (e.g., *"You read `src/main.py`. Key context extracted."*). The agent never forgets its steps, but memory stays infinitely lean.
2. **Zero Provider Lock-In**: Complete freedom. Connect to OpenAI, Anthropic, Ollama, Groq, or any OpenAI-compatible local/remote model via a lightweight JSON configuration.
3. **Advanced Matrix-Grade CLI**: A professional terminal UI featuring auto-completion, collapsible tool outputs, persistent history, and surgical file patching tools.
4. **JSON-First Configuration**: Streamlined, standard, and easy to parse. All configurations (`settings.json`, `trusted_folders.json`) are purely JSON.

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Smart Memory Architecture](#smart-memory-architecture)
- [Usage & CLI Features](#usage--cli-features)
- [Built-in Agents & Subagents](#built-in-agents--subagents)
- [The Hacxgent Toolset](#the-hacxgent-toolset)
- [Configuration (JSON)](#configuration-json)
- [Skills System](#skills-system)
- [MCP Server Integration](#mcp-server-integration)
- [License](#license)
- [Documentation](#documentation)

---

## Installation

### Using uv (Recommended)

First, install `uv`:
```bash
# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then, install Hacxgent:
```bash
uv tool install hacxgent
```

### Using pip

```bash
pip install hacxgent
```

---

## Quick Start

1. Navigate to your project's root directory:
   ```bash
   cd /path/to/your/project
   ```

2. Launch Hacxgent:
   ```bash
   hacxgent
   ```

3. **First Run Setup**: Hacxgent will create a default configuration at `~/.hacxgent/settings.json`. It will prompt you to enter your preferred API provider and keys (saved securely to `~/.hacxgent/.env`).

4. **Start Coding**:
   ```
   > Find all instances of the word "TODO" and summarize what needs to be done.
   ```

---

## Smart Memory Architecture

Hacxgent solves the "Context Exhaustion" problem that plagues standard coding agents. 

### The Problem
Agents perform actions like reading a 2,000-line file. That 8k+ token output sits in the chat history permanently. After 4-5 file reads, the LLM starts forgetting the original prompt, hallucinating, or hitting its token limit.

### The Hacxgent Solution
Hacxgent utilizes a **Rolling Compaction Middleware**:
- **Execution**: The agent reads the file and gets the full content to perform its immediate reasoning.
- **Compaction**: As the conversation moves forward, Hacxgent identifies these stale, heavy tool outputs in the history.
- **Redaction**: It strips out the massive text block and replaces it with a highly optimized marker: 
  `[REDACTED: Output of read_file (5,400 chars). Key context: src/core/loop.py.]`
- **Result**: The model retains the *knowledge* that it read the file and understands the project state, but thousands of tokens are recovered. This allows for essentially **infinite context horizons**.

---

## Usage & CLI Features

### Interactive Mode

Simply run `hacxgent` to enter the interactive chat loop. The CLI is heavily optimized for developers:

- **File Path Autocomplete**: Type `@` to get smart autocompletion for files in your project (e.g., `> Read @src/agent.py`).
- **Slash Commands**: Type `/` to access meta-actions (`/help`, `/clear`, `/compact`, `/status`).
- **Shell Passthrough**: Prefix with `!` to run standard terminal commands (e.g., `> !npm run build`).
- **External Editor**: Press `Ctrl+G` to write your prompt in Vim/VSCode.
- **Toggle Views**: 
  - `Ctrl+O`: Collapse/Expand raw tool outputs.
  - `Ctrl+T`: Toggle the internal Todo list view.
  - `Shift+Tab`: Toggle Auto-Approve mode on/off.

### Programmatic Mode

Run Hacxgent non-interactively for scripting or CI/CD pipelines:

```bash
hacxgent --prompt "Refactor the main function in cli/main.py to be more modular." --max-turns 5 --output json
```

### Trust Folder System

Safety first. When Hacxgent runs in a new directory containing a `.hacxgent` subfolder, it will ask for confirmation. Trusted folders are saved in `~/.hacxgent/trusted_folders.json`.

---

## Built-in Agents & Subagents

Hacxgent ships with specialized profiles tailored for different risk levels:

- **`default`**: Standard agent. Requires manual approval for risky tool executions (writes, deletes, shell commands).
- **`plan`**: Read-only exploration and architecture mapping.
- **`accept-edits`**: Automatically approves code modifications (`write_file`, `replace_lines`), but asks for shell commands.
- **`auto-approve`**: Full autonomy. Use only in trusted, version-controlled environments.

Select an agent via CLI:
```bash
hacxgent --agent plan
```

### Subagent Delegation
Hacxgent can parallelize work by delegating tasks to subagents without cluttering your main context window:
```text
> Can you explore the codebase structure while I work on something else?
🤖 I'll delegate this to the explore subagent.
> task(task="Analyze the project architecture", agent="explore")
```

---

## The Hacxgent Toolset

We expanded standard toolsets to focus on **surgical precision**:

- **File Operations**: `read_lines`, `write_file`, `replace_lines` (1-indexed, surgical swapping instead of fragile search/replace), `file_meta` (Knowledge Map generation).
- **System**: `bash` (stateful terminal), `grep` (recursive fast search).
- **Agentic**: 
  - `todo`: Allows the agent to self-manage complex, multi-step tasks.
  - `ask_user_question`: Pauses execution to render an interactive multi-choice question to the user for clarification.
  - `impact_analyzer`: Maps symbol dependencies project-wide before refactoring.

---

## Configuration (JSON)

Hacxgent uses strictly standard `.json` files for all configurations. The main configuration is located at `~/.hacxgent/settings.json`.

For a comprehensive, in-depth guide to all available settings, including provider setup, model parameters, tool management, and advanced features, please refer to the dedicated documentation:

👉 [**Configuration Reference (DOCS/SETTINGS.md)**](DOCS/SETTINGS.md)

### Provider Agnosticism (Bring Your Own LLM)

Configure any OpenAI-compatible endpoint easily. Below is a brief example; full details are in the Configuration Reference.

**`~/.hacxgent/settings.json`**
```json
{
  "system_prompt_id": "cli",
  "active_model": "llama3",
  "providers": [
    {
      "name": "LocalOpenAI",
      "api_base": "http://localhost:11434/v1",
      "api_key_env_var": "OLLAMA_API_KEY"
    },
    {
      "name": "Groq",
      "api_base": "https://api.groq.com/openai/v1",
      "api_key_env_var": "GROQ_API_KEY"
    }
  ],
  "enabled_tools": ["*"],
  "disabled_tools": ["dangerous_tool_*"],
  "enable_auto_update": true
}
```

### API Keys
Store keys in your environment, or in `~/.hacxgent/.env`:
```env
OLLAMA_API_KEY=your_key_here
OPENAI_API_KEY=sk-....
```

---

## Skills System

Extend Hacxgent with reusable capabilities. Skills conform to the [Agent Skills specification](https://agentskills.io/specification).

1. Create a skill directory: `~/.hacxgent/skills/code-review/`
2. Create a `SKILL.md` file with YAML frontmatter:

```markdown
---
name: code-review
description: Perform automated code reviews
user-invocable: true
allowed-tools:
  - read_file
  - grep
---
# Code Review Skill
Instructions for the agent on how to review code...
```
Enable it in `settings.json`:
```json
{
  "enabled_skills": ["code-review"]
}
```

---

## MCP Server Integration

Hacxgent natively supports the **Model Context Protocol (MCP)** to connect to external tools and databases.

Configure MCP servers in your `settings.json`:

```json
{
  "mcp_servers": [
    {
      "name": "postgres_db",
      "transport": "stdio",
      "command": "uvx",
      "args": ["mcp-server-postgres", "postgresql://localhost/mydb"],
      "startup_timeout_sec": 15
    },
    {
      "name": "weather_api",
      "transport": "http",
      "url": "http://localhost:8000",
      "headers": {
        "Authorization": "Bearer my_token"
      }
    }
  ],
  "tools": {
    "postgres_db_query": {
      "permission": "ask"
    }
  }
}
```

---

## Custom Hacxgent Home Directory

Override the default `~/.hacxgent/` directory by setting an environment variable:
```bash
export HACXGENT_HOME="/path/to/custom/dir"
```

## Documentation

For comprehensive information and detailed guides, please refer to the following:

*   [**Configuration Reference**](DOCS/SETTINGS.md): An exhaustive guide to all settings, providers, and customizations.
*   [**Memory Management**](MEMORY_MANAGEMENT.md): Dive deep into Hacxgent's unique context compaction architecture.
*   [**Contribution Guidelines**](CONTRIBUTING.md): How to get involved and extend Hacxgent.

## Contributing & Telemetry

Hacxgent is built for privacy. All Telemetry Removed, No Telemetry, Nothing.

We welcome contributions! Please see `CONTRIBUTING.md` for guidelines on adding tools, improving memory management, or fixing bugs.

## License

Hacxgent is released under the **Apache-2.0 License**. See [LICENSE](LICENSE) for the full text.

*Core architecture inspired by Mistral Vibe. Re-engineered by BlackTechX for universal provider support and advanced memory management.*
