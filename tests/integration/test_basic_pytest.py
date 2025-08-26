"""
Basic test to verify pytest is working
"""

import pytest

def test_basic_assertion():
    """Simple test to verify pytest works"""
    assert 1 + 1 == 2

def test_list_operations():
    """Test basic list operations"""
    test_list = [1, 2, 3]
    test_list.append(4)
    assert len(test_list) == 4
    assert test_list[-1] == 4

@pytest.mark.asyncio
async def test_async_function():
    """Test async functionality works"""
    async def get_value():
        return 42
    
    result = await get_value()
    assert result == 42

class TestBasicClass:
    """Test class-based tests work"""
    
    def test_string_methods(self):
        """Test string methods"""
        text = "hello world"
        assert text.upper() == "HELLO WORLD"
        assert text.split() == ["hello", "world"]
    
    def test_dictionary_operations(self):
        """Test dictionary operations"""
        data = {"key": "value"}
        data["new_key"] = "new_value"
        assert len(data) == 2
        assert "new_key" in data