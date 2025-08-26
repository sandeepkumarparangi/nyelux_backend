"""
Unit tests for search service.

Tests cover all search strategies, caching, filtering, and analytics tracking.
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from elasticsearch import AsyncElasticsearch

from src.db.models.gudid_device import GUDIDDevice
from src.db.models.search_history import SearchHistory, SavedSearch
from src.services.search_service import SearchService


class TestSearchService:
    """Test suite for SearchService class."""
    
    @pytest.fixture
    def mock_cache(self):
        """Create mock cache service."""
        cache = AsyncMock()
        cache.get.return_value = None  # Default to no cache hit
        cache.set.return_value = True
        return cache
    
    @pytest.fixture
    def mock_es_client(self):
        """Create mock Elasticsearch client."""
        es = AsyncMock(spec=AsyncElasticsearch)
        return es
    
    @pytest.fixture
    def search_service(self, mock_cache, mock_es_client):
        """Create SearchService instance with mocked dependencies."""
        service = SearchService()
        service.cache = mock_cache
        service.es_client = mock_es_client
        return service
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_gudid_device(self):
        """Create mock GUDID device."""
        device = MagicMock(spec=GUDIDDevice)
        device.primary_di = "12345678901234"
        device.device_name = "Test Pacemaker"
        device.manufacturer_name = "Medtronic"
        device.brand_name = "Medtronic"
        device.model_number = "PM123"
        device.device_class = "III"
        device.device_class_name = "Class III"
        device.gmdn_terms = "Pacemaker, cardiac, implantable"
        device.gmdn_codes = "12345"
        device.device_description = "Implantable cardiac pacemaker"
        device.mri_safety = "MR Conditional"
        device.sterile = True
        device.single_use = False
        device.implantable = True
        device.life_supporting = True
        return device
    
    @pytest.mark.asyncio
    async def test_search_devices_empty_query(self, search_service, mock_db):
        """Test search with empty query returns empty results."""
        result = await search_service.search_devices(
            db=mock_db,
            query="",
            user_id=1
        )
        
        assert result["results"] == []
        assert result["total_count"] == 0
        assert result["execution_time_ms"] == 0
    
    @pytest.mark.asyncio
    async def test_search_devices_with_cache_hit(self, search_service, mock_db, mock_cache):
        """Test search returns cached results when available."""
        # Setup cache hit
        cached_data = {
            "results": [{"primary_di": "123", "device_name": "Cached Device"}],
            "total_count": 1,
            "page": 1,
            "limit": 50,
            "total_pages": 1,
            "suggestions": [],
            "facets": {},
            "execution_time_ms": 10
        }
        mock_cache.get.return_value = cached_data
        
        # Mock settings to not be in development
        with patch('src.services.search_service.settings.ENVIRONMENT', 'production'):
            result = await search_service.search_devices(
                db=mock_db,
                query="pacemaker",
                user_id=1
            )
        
        assert result["results"] == cached_data["results"]
        assert result["from_cache"] is True
        assert result["execution_time_ms"] == 0
        
        # Verify cache was checked
        mock_cache.get.assert_called_once()
        # Verify no database queries were made
        mock_db.execute.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_exact_match_search(self, search_service, mock_db, mock_gudid_device):
        """Test exact DI match search strategy."""
        # Setup mock database response
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_gudid_device]
        mock_db.execute.return_value = mock_result
        
        results = await search_service._exact_match_search(
            db=mock_db,
            query="12345678901234"
        )
        
        assert len(results) == 1
        assert results[0]["primary_di"] == "12345678901234"
        assert results[0]["score"] == 1.0  # Exact match gets highest score
        
        # Verify query was executed
        mock_db.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_full_text_search(self, search_service, mock_db, mock_gudid_device):
        """Test PostgreSQL full-text search strategy."""
        # Setup mock database response with rank
        mock_row = (mock_gudid_device, 0.8)
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([mock_row]))
        mock_db.execute.return_value = mock_result
        
        results = await search_service._full_text_search(
            db=mock_db,
            query="cardiac pacemaker"
        )
        
        assert len(results) == 1
        assert results[0]["device_name"] == "Test Pacemaker"
        assert results[0]["score"] == 0.8
    
    @pytest.mark.asyncio
    async def test_manufacturer_model_search(self, search_service, mock_db, mock_gudid_device):
        """Test manufacturer + model combination search."""
        # Setup mock database response
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_gudid_device]
        mock_db.execute.return_value = mock_result
        
        results = await search_service._manufacturer_model_search(
            db=mock_db,
            query="Medtronic pacemaker"
        )
        
        assert len(results) > 0
        assert results[0]["manufacturer_name"] == "Medtronic"
        assert results[0]["score"] == 0.8
    
    @pytest.mark.asyncio
    async def test_gmdn_search(self, search_service, mock_db, mock_gudid_device):
        """Test GMDN category search."""
        # Setup mock database response
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_gudid_device]
        mock_db.execute.return_value = mock_result
        
        results = await search_service._gmdn_search(
            db=mock_db,
            query="pacemaker"
        )
        
        assert len(results) == 1
        assert "pacemaker" in results[0]["gmdn_terms"].lower()
        assert results[0]["score"] == 0.7
    
    @pytest.mark.asyncio
    async def test_elasticsearch_search_success(self, search_service, mock_es_client):
        """Test Elasticsearch fuzzy search."""
        # Setup mock ES response
        mock_es_client.search.return_value = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "primary_di": "123",
                            "device_name": "Test Device",
                            "manufacturer_name": "Test Corp"
                        },
                        "_score": 5.5
                    }
                ]
            },
            "suggest": {}
        }
        
        results = await search_service._elasticsearch_search(
            query="test devce"  # Typo intentional
        )
        
        assert len(results) == 1
        assert results[0]["device_name"] == "Test Device"
        assert results[0]["score"] == 0.55  # Normalized from 5.5
        
        # Verify ES query structure
        mock_es_client.search.assert_called_once()
        call_args = mock_es_client.search.call_args
        assert "fuzziness" in str(call_args)
    
    @pytest.mark.asyncio
    async def test_elasticsearch_search_error_handling(self, search_service, mock_es_client):
        """Test Elasticsearch error handling."""
        # Setup ES to raise an error
        mock_es_client.search.side_effect = Exception("ES connection failed")
        
        results = await search_service._elasticsearch_search(query="test")
        
        # Should return empty results on error
        assert results == []
    
    def test_apply_filters_device_class(self, search_service):
        """Test applying device class filter."""
        # Create mock query
        mock_stmt = MagicMock()
        mock_model = MagicMock()
        mock_model.device_class = MagicMock()
        
        filters = {"device_class": ["I", "II"]}
        result = search_service._apply_filters(mock_stmt, filters, mock_model)
        
        # Verify filter was applied
        mock_stmt.where.assert_called_once()
    
    def test_device_to_dict_conversion(self, search_service, mock_gudid_device):
        """Test converting device model to dictionary."""
        result = search_service._device_to_dict(mock_gudid_device, score=0.9)
        
        assert result["primary_di"] == "12345678901234"
        assert result["device_name"] == "Test Pacemaker"
        assert result["score"] == 0.9
        assert "manufacturer_name" in result
        assert "device_class" in result
    
    def test_sort_results_by_relevance(self, search_service):
        """Test sorting results by relevance score."""
        results = [
            {"device_name": "Device A", "score": 0.5},
            {"device_name": "Device B", "score": 0.9},
            {"device_name": "Device C", "score": 0.7}
        ]
        
        sorted_results = search_service._sort_results(results, "relevance")
        
        assert sorted_results[0]["score"] == 0.9
        assert sorted_results[1]["score"] == 0.7
        assert sorted_results[2]["score"] == 0.5
    
    def test_sort_results_by_name(self, search_service):
        """Test sorting results by device name."""
        results = [
            {"device_name": "Zebra Device", "score": 0.5},
            {"device_name": "Alpha Device", "score": 0.9},
            {"device_name": "Beta Device", "score": 0.7}
        ]
        
        sorted_results = search_service._sort_results(results, "name")
        
        assert sorted_results[0]["device_name"] == "Alpha Device"
        assert sorted_results[1]["device_name"] == "Beta Device"
        assert sorted_results[2]["device_name"] == "Zebra Device"
    
    @pytest.mark.asyncio
    async def test_generate_facets(self, search_service, mock_db):
        """Test facet generation for search refinement."""
        # Mock facet query results
        class_result = [
            MagicMock(device_class="I", device_class_name="Class I", count=50),
            MagicMock(device_class="II", device_class_name="Class II", count=30),
            MagicMock(device_class="III", device_class_name="Class III", count=20)
        ]
        
        mfr_result = [
            MagicMock(manufacturer_name="Medtronic", count=40),
            MagicMock(manufacturer_name="Abbott", count=35)
        ]
        
        # Setup mock responses
        mock_db.execute.side_effect = [
            MagicMock(return_value=class_result),
            MagicMock(return_value=mfr_result)
        ]
        
        facets = await search_service._generate_facets(
            db=mock_db,
            query="pacemaker"
        )
        
        assert "device_class" in facets
        assert len(facets["device_class"]) == 3
        assert facets["device_class"][0]["value"] == "I"
        assert facets["device_class"][0]["count"] == 50
        
        assert "manufacturer" in facets
        assert len(facets["manufacturer"]) == 2
    
    @pytest.mark.asyncio
    async def test_generate_suggestions_no_results(self, search_service, mock_db):
        """Test suggestion generation when no results found."""
        # Mock similar searches
        similar_searches = [
            MagicMock(search_query="pacemaker"),
            MagicMock(search_query="pace maker"),
            MagicMock(search_query="cardiac pacemaker")
        ]
        
        mock_db.execute.return_value = MagicMock(return_value=similar_searches)
        
        suggestions = await search_service._generate_suggestions(
            db=mock_db,
            query="pacemker",  # Typo
            results=[[], [], [], [], []]  # No results from any strategy
        )
        
        assert len(suggestions) == 3
        assert "pacemaker" in suggestions
    
    @pytest.mark.asyncio
    async def test_track_search_analytics(self, search_service, mock_db):
        """Test search analytics tracking."""
        start_time = datetime.utcnow()
        
        await search_service._track_search(
            db=mock_db,
            user_id=1,
            organization_id=10,
            query="test search",
            filters={"device_class": ["III"]},
            results_count=25,
            start_time=start_time
        )
        
        # Verify SearchHistory was created
        mock_db.add.assert_called_once()
        search_history = mock_db.add.call_args[0][0]
        
        assert isinstance(search_history, SearchHistory)
        assert search_history.user_id == 1
        assert search_history.search_query == "test search"
        assert search_history.results_count == 25
        assert search_history.filters_applied == {"device_class": ["III"]}
    
    @pytest.mark.asyncio
    async def test_save_search(self, search_service, mock_db):
        """Test saving a search for future use."""
        saved_search = await search_service.save_search(
            db=mock_db,
            user_id=1,
            name="My Pacemaker Search",
            query="medtronic pacemaker",
            filters={"device_class": ["III"]},
            alert_enabled=True,
            alert_frequency="daily"
        )
        
        # Verify SavedSearch was created
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        
        # Verify the saved search object
        saved_obj = mock_db.add.call_args[0][0]
        assert isinstance(saved_obj, SavedSearch)
        assert saved_obj.name == "My Pacemaker Search"
        assert saved_obj.alert_enabled is True
    
    @pytest.mark.asyncio
    async def test_get_popular_searches(self, search_service, mock_db):
        """Test retrieving popular searches."""
        # Mock popular search results
        popular = [
            MagicMock(search_query="pacemaker", search_count=150, avg_results=45.5),
            MagicMock(search_query="hip implant", search_count=120, avg_results=38.2),
            MagicMock(search_query="stent", search_count=100, avg_results=52.7)
        ]
        
        mock_db.execute.return_value = MagicMock(return_value=popular)
        
        results = await search_service.get_popular_searches(
            db=mock_db,
            organization_id=10,
            limit=3
        )
        
        assert len(results) == 3
        assert results[0]["query"] == "pacemaker"
        assert results[0]["count"] == 150
        assert results[0]["avg_results"] == 45
    
    @pytest.mark.asyncio
    async def test_search_devices_integration(self, search_service, mock_db, mock_cache):
        """Test complete search flow with all strategies."""
        # Mock all strategy results
        exact_results = [{"primary_di": "123", "device_name": "Exact Match", "score": 1.0}]
        fulltext_results = [{"primary_di": "456", "device_name": "Text Match", "score": 0.8}]
        mfr_results = [{"primary_di": "789", "device_name": "Mfr Match", "score": 0.7}]
        gmdn_results = []
        es_results = []
        
        # Mock the strategy methods
        with patch.multiple(
            search_service,
            _exact_match_search=AsyncMock(return_value=exact_results),
            _full_text_search=AsyncMock(return_value=fulltext_results),
            _manufacturer_model_search=AsyncMock(return_value=mfr_results),
            _gmdn_search=AsyncMock(return_value=gmdn_results),
            _elasticsearch_search=AsyncMock(return_value=es_results),
            _generate_facets=AsyncMock(return_value={"device_class": []}),
            _generate_suggestions=AsyncMock(return_value=[]),
            _track_search=AsyncMock()
        ):
            result = await search_service.search_devices(
                db=mock_db,
                query="test device",
                user_id=1,
                page=1,
                limit=50
            )
        
        # Verify results are combined and deduplicated
        assert result["total_count"] == 3
        assert len(result["results"]) == 3
        
        # Verify results are sorted by score
        assert result["results"][0]["score"] == 1.0
        assert result["results"][1]["score"] == 0.8
        assert result["results"][2]["score"] == 0.7
        
        # Verify cache was set
        mock_cache.set.assert_called_once()
        
        # Verify execution time is calculated
        assert result["execution_time_ms"] > 0
