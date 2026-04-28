"""
Claude CLI runner service.
Invokes Claude Code skills via `claude -p` for workflow analysis and editing.
Supports both direct prompt mode and skill-file-based invocation.
"""

import subprocess
import json
import os
import re
import logging
import time

logger = logging.getLogger(__name__)

SKILLS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '.claude', 'commands')


def get_skill_prompt(skill_name: str) -> str:
    """
    Load a skill prompt template from the .claude/commands/ directory.
    """
    skill_path = os.path.join(SKILLS_DIR, f"{skill_name}.md")
    skill_path = os.path.abspath(skill_path)
    logger.info(f"[SKILL] Loading skill template from: {skill_path}")

    if not os.path.exists(skill_path):
        logger.error(f"[SKILL] Skill file NOT FOUND: {skill_path}")
        raise FileNotFoundError(f"Skill file not found: {skill_path}")

    with open(skill_path, "r") as f:
        content = f.read()
    logger.info(f"[SKILL] Loaded skill template: {len(content)} chars")
    return content


def build_skill_prompt(skill_name: str, arguments: str) -> str:
    """
    Build a full prompt by loading the skill template and injecting arguments.
    """
    template = get_skill_prompt(skill_name)
    prompt = template.replace("$ARGUMENTS", arguments)
    logger.info(f"[SKILL] Built prompt for skill '{skill_name}': {len(prompt)} chars total")
    return prompt


def run_claude_prompt(prompt: str, cwd: str = None, timeout: int = 120) -> str:
    """
    Run a prompt through `claude -p` and return the raw text output.
    """
    prompt_preview = prompt[:200].replace('\n', ' ')
    logger.info(f"[CLAUDE] Invoking claude -p (timeout={timeout}s, cwd={cwd})")
    logger.info(f"[CLAUDE] Prompt preview: {prompt_preview}...")
    logger.info(f"[CLAUDE] Full prompt length: {len(prompt)} chars")

    cmd = ["claude", "-p", prompt]

    try:
        start_time = time.time()
        logger.info(f"[CLAUDE] Starting subprocess: claude -p <prompt>")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
        )

        elapsed = time.time() - start_time
        logger.info(f"[CLAUDE] Subprocess completed in {elapsed:.1f}s, exit code: {result.returncode}")

        if result.stderr:
            logger.warning(f"[CLAUDE] stderr: {result.stderr[:500]}")

        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            logger.error(f"[CLAUDE] CLI failed (exit {result.returncode}): {error_msg}")
            raise RuntimeError(f"Claude CLI failed (exit {result.returncode}): {error_msg}")

        output = result.stdout.strip()
        logger.info(f"[CLAUDE] Response received: {len(output)} chars")
        logger.debug(f"[CLAUDE] Response preview: {output[:300]}")
        return output

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        logger.error(f"[CLAUDE] TIMEOUT after {elapsed:.1f}s (limit was {timeout}s)")
        raise RuntimeError(f"Claude CLI timed out after {timeout}s")
    except FileNotFoundError:
        logger.error("[CLAUDE] 'claude' command not found in PATH")
        raise RuntimeError("Claude CLI not found. Ensure 'claude' is installed and in PATH.")
    except Exception as e:
        logger.error(f"[CLAUDE] Unexpected error: {type(e).__name__}: {e}")
        raise


def run_skill(skill_name: str, arguments: str, cwd: str = None, timeout: int = 180) -> str:
    """
    Run a Claude skill by name with the given arguments.
    """
    logger.info(f"[SKILL] === Running skill: {skill_name} ===")
    logger.info(f"[SKILL] Arguments length: {len(arguments)} chars")
    prompt = build_skill_prompt(skill_name, arguments)
    return run_claude_prompt(prompt, cwd=cwd, timeout=timeout)


def extract_json_from_response(response: str) -> dict:
    """
    Extract JSON from a Claude response that may contain markdown code blocks
    or surrounding text.
    """
    logger.info(f"[JSON] Extracting JSON from response ({len(response)} chars)")

    # Try direct parse first
    try:
        result = json.loads(response)
        logger.info("[JSON] Direct JSON parse succeeded")
        return result
    except json.JSONDecodeError as e:
        logger.info(f"[JSON] Direct parse failed: {e}")

    # Try to extract from markdown code blocks
    json_patterns = [
        r"```json\s*\n(.*?)\n\s*```",
        r"```\s*\n(.*?)\n\s*```",
    ]

    for i, pattern in enumerate(json_patterns):
        match = re.search(pattern, response, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1))
                logger.info(f"[JSON] Extracted from code block (pattern {i+1})")
                return result
            except json.JSONDecodeError as e:
                logger.info(f"[JSON] Code block pattern {i+1} matched but JSON invalid: {e}")
                continue

    # Try to find the largest valid JSON object by scanning for balanced braces
    brace_start = response.find("{")
    if brace_start != -1:
        logger.info(f"[JSON] Trying brace-matching from position {brace_start}")
        depth = 0
        in_string = False
        escape_next = False
        for i in range(brace_start, len(response)):
            ch = response[i]
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if not in_string:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            result = json.loads(response[brace_start:i + 1])
                            logger.info(f"[JSON] Brace-matching succeeded (chars {brace_start} to {i+1})")
                            return result
                        except json.JSONDecodeError as e:
                            logger.warning(f"[JSON] Brace-matched block invalid: {e}")
                            break

    logger.error(f"[JSON] FAILED to extract JSON. Response preview:\n{response[:800]}")
    raise ValueError(
        f"Could not extract valid JSON from Claude response. "
        f"Response preview: {response[:500]}"
    )
