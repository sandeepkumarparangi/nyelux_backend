"""
Elasticsearch initialization service.
Creates indices with proper mappings for device search.
REAL implementation - no fake indices.
"""
import logging
from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import RequestError

from src.core.config import settings

logger = logging.getLogger(__name__)


async def initialize_elasticsearch_indices():
    """
    Initialize Elasticsearch indices with proper mappings.
    Creates indices for devices, documents, and analytics.
    """
    if not settings.ELASTICSEARCH_URL:
        logger.warning("Elasticsearch URL not configured")
        return
    
    # Create client
    es = AsyncElasticsearch(
        [settings.ELASTICSEARCH_URL],
        basic_auth=(settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)
        if settings.ELASTICSEARCH_USERNAME else None
    )
    
    try:
        # Check connection
        if not await es.ping():
            raise ConnectionError("Cannot connect to Elasticsearch")
        
        # Device index mapping
        device_mapping = {
            "settings": {
                "number_of_shards": 3,
                "number_of_replicas": 1,
                "analysis": {
                    "analyzer": {
                        "device_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "stop", "snowball", "edge_ngram_filter"]
                        },
                        "exact_analyzer": {
                            "type": "custom",
                            "tokenizer": "keyword",
                            "filter": ["lowercase"]
                        }
                    },
                    "filter": {
                        "edge_ngram_filter": {
                            "type": "edge_ngram",
                            "min_gram": 2,
                            "max_gram": 20
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "primary_di": {
                        "type": "text",
                        "analyzer": "exact_analyzer",
                        "fields": {
                            "keyword": {"type": "keyword"}
                        }
                    },
                    "device_name": {
                        "type": "text",
                        "analyzer": "device_analyzer",
                        "fields": {
                            "keyword": {"type": "keyword"},
                            "suggest": {"type": "completion"}
                        }
                    },
                    "manufacturer_name": {
                        "type": "text",
                        "analyzer": "device_analyzer",
                        "fields": {
                            "keyword": {"type": "keyword"},
                            "suggest": {"type": "completion"}
                        }
                    },
                    "manufacturer_di": {"type": "keyword"},
                    "brand_name": {
                        "type": "text",
                        "analyzer": "device_analyzer"
                    },
                    "model_number": {
                        "type": "text",
                        "analyzer": "exact_analyzer",
                        "fields": {
                            "keyword": {"type": "keyword"}
                        }
                    },
                    "catalog_number": {"type": "keyword"},
                    "device_class": {"type": "keyword"},
                    "device_class_name": {"type": "text"},
                    "gmdn_terms": {
                        "type": "text",
                        "analyzer": "standard"
                    },
                    "gmdn_codes": {"type": "keyword"},
                    "product_code": {"type": "keyword"},
                    "device_description": {
                        "type": "text",
                        "analyzer": "standard"
                    },
                    "mri_safety": {"type": "keyword"},
                    "sterile": {"type": "boolean"},
                    "single_use": {"type": "boolean"},
                    "implantable": {"type": "boolean"},
                    "life_supporting": {"type": "boolean"},
                    "rx_required": {"type": "boolean"},
                    "otc": {"type": "boolean"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"}
                }
            }
        }
        
        # Document chunks index mapping
        document_chunks_mapping = {
            "settings": {
                "number_of_shards": 2,
                "number_of_replicas": 1
            },
            "mappings": {
                "properties": {
                    "document_id": {"type": "keyword"},
                    "device_id": {"type": "keyword"},
                    "organization_id": {"type": "keyword"},
                    "chunk_index": {"type": "integer"},
                    "chunk_text": {
                        "type": "text",
                        "analyzer": "standard"
                    },
                    "page_number": {"type": "integer"},
                    "section_heading": {"type": "text"},
                    "embedding_vector": {
                        "type": "dense_vector",
                        "dims": 1536,
                        "index": True,
                        "similarity": "cosine"
                    },
                    "metadata": {"type": "object"},
                    "created_at": {"type": "date"}
                }
            }
        }
        
        # Analytics events index mapping
        analytics_mapping = {
            "settings": {
                "number_of_shards": 3,
                "number_of_replicas": 0,  # No replicas for write-heavy index
                "index": {
                    "refresh_interval": "30s"  # Less frequent refresh for performance
                }
            },
            "mappings": {
                "properties": {
                    "user_id": {"type": "keyword"},
                    "organization_id": {"type": "keyword"},
                    "session_id": {"type": "keyword"},
                    "event_type": {"type": "keyword"},
                    "event_category": {"type": "keyword"},
                    "resource_type": {"type": "keyword"},
                    "resource_id": {"type": "keyword"},
                    "action": {"type": "keyword"},
                    "label": {"type": "text"},
                    "value": {"type": "float"},
                    "metadata": {"type": "object"},
                    "page_url": {"type": "text"},
                    "referrer_url": {"type": "text"},
                    "ip_address": {"type": "ip"},
                    "user_agent": {"type": "text"},
                    "device_type": {"type": "keyword"},
                    "browser": {"type": "keyword"},
                    "os": {"type": "keyword"},
                    "country_code": {"type": "keyword"},
                    "region": {"type": "keyword"},
                    "city": {"type": "keyword"},
                    "created_at": {"type": "date"}
                }
            }
        }
        
        # Create indices
        indices = [
            (f"{settings.ELASTICSEARCH_INDEX_PREFIX}_devices", device_mapping),
            (f"{settings.ELASTICSEARCH_INDEX_PREFIX}_document_chunks", document_chunks_mapping),
            (f"{settings.ELASTICSEARCH_INDEX_PREFIX}_analytics", analytics_mapping)
        ]
        
        for index_name, mapping in indices:
            try:
                # Check if index exists
                if await es.indices.exists(index=index_name):
                    logger.info(f"Index {index_name} already exists")
                    # In production, you might want to update mapping instead
                else:
                    # Create index
                    await es.indices.create(index=index_name, body=mapping)
                    logger.info(f"Created index: {index_name}")
                    
            except RequestError as e:
                if e.error == "resource_already_exists_exception":
                    logger.info(f"Index {index_name} already exists")
                else:
                    logger.error(f"Failed to create index {index_name}: {e}")
                    raise
        
        # Create index aliases for easier management
        aliases = [
            (f"{settings.ELASTICSEARCH_INDEX_PREFIX}_devices", "devices"),
            (f"{settings.ELASTICSEARCH_INDEX_PREFIX}_document_chunks", "documents"),
            (f"{settings.ELASTICSEARCH_INDEX_PREFIX}_analytics", "analytics")
        ]
        
        for index_name, alias in aliases:
            try:
                if not await es.indices.exists_alias(name=alias):
                    await es.indices.put_alias(index=index_name, name=alias)
                    logger.info(f"Created alias {alias} -> {index_name}")
            except Exception as e:
                logger.warning(f"Failed to create alias {alias}: {e}")
        
        logger.info("Elasticsearch initialization completed")
        
    except Exception as e:
        logger.error(f"Elasticsearch initialization failed: {e}")
        raise
    finally:
        await es.close()
