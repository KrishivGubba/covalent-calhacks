"""
Test to verify MCPToolModule enforces register() method implementation.

Run:
  python3 -m covalent_mcp.tests.test_base_enforcement
"""

from covalent_mcp.toolclasses.base import MCPToolModule

# For CI/sandbox environments where fastmcp isn't installed, we provide a tiny stub.
try:
    from fastmcp import FastMCP  # type: ignore
except ModuleNotFoundError:
    class FastMCP:  # type: ignore
        def __init__(self, name: str):
            self.name = name

        def tool(self):
            def decorator(fn):
                return fn

            return decorator


def test_missing_register_raises_error():
    """Test that a class without register() raises TypeError at instantiation."""
    try:
        class BadToolModule(MCPToolModule):
            # Missing register() method!
            pass

        # Should raise TypeError when trying to instantiate
        _ = BadToolModule()
        print("❌ ERROR: Should have raised TypeError!")
        return False
    except TypeError as e:
        print(f"✅ Correctly raised TypeError: {e}")
        return True
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_implemented_register_works():
    """Test that a class with register() works correctly."""
    try:
        class GoodToolModule(MCPToolModule):
            def register(self, mcp: "FastMCP") -> None:
                @mcp.tool()
                def test_tool(x: int) -> int:
                    return x * 2

        module = GoodToolModule()
        print("✅ GoodToolModule instantiated successfully")

        # Test that register can be called (FastMCP is either real or stubbed above)
        mcp = FastMCP("Test Server")
        module.register(mcp)
        print("✅ register() method called successfully")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Testing MCPToolModule enforcement...\n")

    print("Test 1: Missing register() method")
    test1 = test_missing_register_raises_error()

    print("\nTest 2: Implemented register() method")
    test2 = test_implemented_register_works()

    print("\n" + "=" * 50)
    if test1 and test2:
        print("✅ All tests passed! MCPToolModule enforcement works.")
    else:
        print("❌ Some tests failed.")

