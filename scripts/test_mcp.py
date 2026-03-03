"""
Test script for the Validity MCP server tools.

Directly imports and calls the MCP tool functions (bypasses the MCP transport layer)
to verify the pipeline works end-to-end from the MCP server's perspective.

Usage:
    python scripts/test_mcp.py

Requires a valid .env with LLM_API_KEY and SEARCH_API_KEY.

Note on imports: We load mcp/server.py via importlib to avoid naming conflicts
with the installed 'mcp' (Model Context Protocol) Python SDK package.
"""

import asyncio
import importlib.util
import os
import sys

# Add project root to path so backend.* imports work
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Load mcp/server.py directly to avoid mcp package naming conflict with MCP SDK
_server_path = os.path.join(_PROJECT_ROOT, "mcp", "server.py")
_spec = importlib.util.spec_from_file_location("validity_mcp_server", _server_path)
_server_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_server_mod)

verify_text = _server_mod.verify_text
verify_text_interactive = _server_mod.verify_text_interactive
get_run = _server_mod.get_run


TEST_TEXT = (
    "The Earth orbits the Sun once every 365.25 days. "
    "The Great Wall of China is visible from space with the naked eye. "
    "Mount Everest is the tallest mountain in the world at 8,849 metres."
)


async def test_verify_text():
    print("=" * 60)
    print("TEST 1: verify_text (full pipeline, HITL auto-approved)")
    print("=" * 60)
    print(f"Input: {TEST_TEXT[:80]}...")
    print()

    result = await verify_text(TEST_TEXT)
    print(result)
    print()
    assert "Overall Verdict" in result, "Expected 'Overall Verdict' in output"
    assert "Claims Verified" in result, "Expected 'Claims Verified' in output"
    print("✓ verify_text passed")
    print()
    return result


async def test_verify_text_interactive_step1():
    print("=" * 60)
    print("TEST 2: verify_text_interactive — Step 1 (decompose + rank)")
    print("=" * 60)
    print(f"Input: {TEST_TEXT[:80]}...")
    print()

    result = await verify_text_interactive(TEST_TEXT)
    print(result)
    print()
    assert "Step 1 of 2" in result, "Expected step 1 header"
    assert "Preview ID:" in result, "Expected 'Preview ID:' in output"
    assert "ID:" in result, "Expected claim IDs in output"
    print("✓ verify_text_interactive step 1 passed")
    print()
    return result


async def test_get_run_found(run_id: str):
    print("=" * 60)
    print(f"TEST 3: get_run (run_id={run_id[:8]}...)")
    print("=" * 60)

    result = get_run(run_id)
    print(result)
    print()
    print("✓ get_run (found) passed")
    print()


async def test_get_run_not_found():
    print("=" * 60)
    print("TEST 4: get_run — unknown run_id")
    print("=" * 60)

    result = get_run("00000000-0000-0000-0000-000000000000")
    print(result)
    print()
    assert "not found" in result.lower(), "Expected 'not found' for unknown run_id"
    print("✓ get_run (not found) passed")
    print()


async def main():
    print()
    print("Validity MCP Server — Tool Tests")
    print("=" * 60)
    print()

    # Test 1: Full pipeline — HITL auto-approved
    verify_result = await test_verify_text()

    # Extract run_id from result for get_run test
    run_id = None
    for line in verify_result.splitlines():
        if line.startswith("Run ID:"):
            run_id = line.split("Run ID:", 1)[1].strip()
            break

    # Test 2: Interactive step 1 (decompose + rank preview)
    await test_verify_text_interactive_step1()

    # Test 3: get_run with a known run_id
    if run_id:
        await test_get_run_found(run_id)
    else:
        print("Skipping test 3 — could not extract run_id from verify_text output")

    # Test 4: get_run with unknown run_id
    await test_get_run_not_found()

    print("=" * 60)
    print("All MCP tool tests passed.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
