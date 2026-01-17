"""
Test to verify MCPToolModule enforces register() method implementation.

Run this to verify the abstract base class works correctly.
"""
from covalent_mcp.toolclasses.base import MCPToolModule


def test_missing_register_raises_error():
    """Test that a class without register() raises TypeError at instantiation."""
    try:
        class BadToolModule(MCPToolModule):
            # Missing register() method!
            pass
        
        # Should raise TypeError when trying to instantiate
        module = BadToolModule()
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
        
        # Test that register can be called
        from fastmcp import FastMCP
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
    
    print("\n" + "="*50)
    if test1 and test2:
        print("✅ All tests passed! MCPToolModule enforcement works.")
    else:
        print("❌ Some tests failed.")
