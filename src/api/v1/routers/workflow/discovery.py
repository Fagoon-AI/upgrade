from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from src.core.database import get_db
from src.api.v1.routers.workflow.deps import get_current_user
from src.models.sql.workflow.user import User
from src.services.workflow.discovery_service import DiscoveryService
from src.schemas.workflow.response import APIResponse, ErrorResponse


# ============================================================
# ROUTER
# ============================================================

router = APIRouter()


# ============================================================
# SEARCH ENDPOINTS
# ============================================================

@router.get(
    "/search",
    response_model=APIResponse,
    summary="Semantic search",
    description="Search across RAG-ingested documents using semantic similarity"
)
async def semantic_search(
        q: str = Query(
            ...,
            min_length=3,
            max_length=1000,
            description="The search query"
        ),
        connection_id: UUID = Query(
            ...,
            description="AI connection ID for embeddings"
        ),
        limit: int = Query(
            5,
            ge=1,
            le=50,
            description="Maximum results to return"
        ),
        min_similarity: Optional[float] = Query(
            None,
            ge=0.0,
            le=1.0,
            description="Minimum similarity threshold (0-1)"
        ),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Performs semantic search across user's documents.

    Uses vector embeddings to find semantically similar content.
    Falls back to keyword search if embedding generation fails.
    """
    try:
        service = DiscoveryService()

        results = await service._do_semantic_search(
            db=db,
            user_id=current_user.id,
            query=q,
            connection_id=connection_id,
            limit=limit,
            min_similarity=min_similarity
        )

        return APIResponse(
            success=True,
            message=f"Found {len(results)} relevant documents",
            data={
                "query": q,
                "count": len(results),
                "results": results
            }
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Search error: {e}", extra={"user_id": str(current_user.id)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed. Please try again."
        )


@router.get(
    "/search/hybrid",
    response_model=APIResponse,
    summary="Hybrid search",
    description="Combined vector and keyword search for better results"
)
async def hybrid_search(
        q: str = Query(
            ...,
            min_length=3,
            max_length=1000,
            description="The search query"
        ),
        connection_id: UUID = Query(
            ...,
            description="AI connection ID for embeddings"
        ),
        limit: int = Query(5, ge=1, le=50),
        keyword_weight: float = Query(
            0.3,
            ge=0.0,
            le=1.0,
            description="Weight for keyword matching (0-1)"
        ),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Performs hybrid search combining vector similarity and keyword matching.

    Useful when exact keyword matches are important alongside semantic relevance.
    """
    try:
        service = DiscoveryService()

        results = await service.hybrid_search(
            db=db,
            user_id=current_user.id,
            query=q,
            connection_id=connection_id,
            limit=limit,
            keyword_weight=keyword_weight
        )

        return APIResponse(
            success=True,
            message=f"Found {len(results)} documents",
            data={
                "query": q,
                "mode": "hybrid",
                "keyword_weight": keyword_weight,
                "count": len(results),
                "results": results
            }
        )

    except Exception as e:
        logger.error(f"Hybrid search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed"
        )


# ============================================================
# DOCUMENT MANAGEMENT ENDPOINTS
# ============================================================

@router.get(
    "/documents",
    response_model=APIResponse,
    summary="List documents",
    description="List all ingested documents"
)
async def list_documents(
        limit: int = Query(100, ge=1, le=500),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Lists all documents in the user's knowledge base.

    Documents are grouped by filename with chunk counts.
    """
    try:
        service = DiscoveryService()

        documents = await service.list_documents(
            db=db,
            user_id=current_user.id,
            limit=limit
        )

        return APIResponse(
            success=True,
            message=f"Found {len(documents)} documents",
            data={
                "count": len(documents),
                "documents": documents
            }
        )

    except Exception as e:
        logger.error(f"List documents error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list documents"
        )


@router.get(
    "/documents/stats",
    response_model=APIResponse,
    summary="Document statistics",
    description="Get statistics about ingested documents"
)
async def get_document_stats(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Returns statistics about the user's knowledge base.

    Includes total chunks, file count, and date range.
    """
    try:
        service = DiscoveryService()

        stats = await service.get_document_stats(
            db=db,
            user_id=current_user.id
        )

        return APIResponse(
            success=True,
            message="Statistics retrieved",
            data=stats
        )

    except Exception as e:
        logger.error(f"Document stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get statistics"
        )


@router.delete(
    "/documents/{filename}",
    response_model=APIResponse,
    summary="Delete document",
    description="Delete all chunks for a document"
)
async def delete_document(
        filename: str,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Deletes all chunks associated with a filename.

    This permanently removes the document from the knowledge base.
    """
    try:
        service = DiscoveryService()

        deleted_count = await service.delete_document(
            db=db,
            user_id=current_user.id,
            filename=filename
        )

        if deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{filename}' not found"
            )

        return APIResponse(
            success=True,
            message=f"Deleted {deleted_count} chunks",
            data={
                "filename": filename,
                "deleted_chunks": deleted_count
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete document error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document"
        )


# ============================================================
# BULK OPERATIONS
# ============================================================

@router.post(
    "/documents/bulk-delete",
    response_model=APIResponse,
    summary="Bulk delete documents",
    description="Delete multiple documents at once"
)
async def bulk_delete_documents(
        filenames: List[str],
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Deletes multiple documents in a single operation.
    """
    if len(filenames) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete more than 100 documents at once"
        )

    try:
        service = DiscoveryService()
        results = {}
        total_deleted = 0

        for filename in filenames:
            deleted = await service.delete_document(
                db=db,
                user_id=current_user.id,
                filename=filename
            )
            results[filename] = deleted
            total_deleted += deleted

        return APIResponse(
            success=True,
            message=f"Deleted {total_deleted} total chunks",
            data={
                "total_deleted": total_deleted,
                "results": results
            }
        )

    except Exception as e:
        logger.error(f"Bulk delete error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bulk delete failed"
        )