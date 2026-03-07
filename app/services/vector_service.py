"""Vector service - manages Milvus vector database for semantic retrieval."""
import logging
import uuid

from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility,
)

from app.core.config import settings
from app.services.embedding_service import embed_texts, get_embedding_dim

logger = logging.getLogger(__name__)

COLLECTION_NAME = "material_chunks"
_connected = False


def connect_milvus():
    """Connect to Milvus server."""
    global _connected
    if not _connected:
        connections.connect(
            alias="default",
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
        )
        _connected = True
        logger.info(f"Connected to Milvus at {settings.MILVUS_HOST}:{settings.MILVUS_PORT}")


def ensure_collection() -> Collection:
    """Create or get the material_chunks collection."""
    connect_milvus()
    dim = get_embedding_dim()

    if utility.has_collection(COLLECTION_NAME):
        collection = Collection(COLLECTION_NAME)
        collection.load()
        return collection

    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=64),
        FieldSchema(name="material_id", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="chunk_index", dtype=DataType.INT64),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=8192),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
    ]

    schema = CollectionSchema(fields=fields, description="Material chunks for semantic search")
    collection = Collection(name=COLLECTION_NAME, schema=schema)

    # Create IVF_FLAT index for vector field
    index_params = {
        "metric_type": "COSINE",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128},
    }
    collection.create_index(field_name="embedding", index_params=index_params)
    collection.load()

    logger.info(f"Created Milvus collection '{COLLECTION_NAME}' with dim={dim}")
    return collection


def insert_vectors(
    knowledge_unit_ids: list[str],
    material_id: str,
    chunk_indices: list[int],
    contents: list[str],
) -> int:
    """Insert text chunks as vectors into Milvus."""
    if not contents:
        return 0

    collection = ensure_collection()
    embeddings = embed_texts(contents)

    # Truncate content to fit VARCHAR limit
    truncated = [c[:8000] if len(c) > 8000 else c for c in contents]

    data = [
        knowledge_unit_ids,                                    # id
        [material_id] * len(contents),                         # material_id
        chunk_indices,                                         # chunk_index
        truncated,                                             # content
        embeddings,                                            # embedding
    ]

    collection.insert(data)
    collection.flush()

    logger.info(f"Inserted {len(contents)} vectors for material {material_id}")
    return len(contents)


def search_similar(query: str, top_k: int = 5, material_id: str = None) -> list[dict]:
    """Search for similar chunks using vector similarity."""
    collection = ensure_collection()
    query_embedding = embed_texts([query])[0]

    search_params = {
        "metric_type": "COSINE",
        "params": {"nprobe": 16},
    }

    expr = None
    if material_id:
        expr = f'material_id == "{material_id}"'

    results = collection.search(
        data=[query_embedding],
        anns_field="embedding",
        param=search_params,
        limit=top_k,
        expr=expr,
        output_fields=["material_id", "chunk_index", "content"],
    )

    hits = []
    for hit in results[0]:
        hits.append({
            "id": hit.id,
            "score": hit.score,
            "material_id": hit.entity.get("material_id"),
            "chunk_index": hit.entity.get("chunk_index"),
            "content": hit.entity.get("content"),
        })

    return hits


def delete_material_vectors(material_id: str) -> int:
    """Delete all vectors for a given material."""
    collection = ensure_collection()
    expr = f'material_id == "{material_id}"'
    result = collection.delete(expr)
    collection.flush()
    return result.delete_count if hasattr(result, 'delete_count') else 0


def get_collection_stats() -> dict:
    """Get collection statistics."""
    connect_milvus()
    if not utility.has_collection(COLLECTION_NAME):
        return {"exists": False, "count": 0}

    collection = Collection(COLLECTION_NAME)
    collection.flush()
    return {
        "exists": True,
        "count": collection.num_entities,
        "name": COLLECTION_NAME,
    }
