# from abc import ABC, abstractmethod
# from typing import Any, Dict, List, Optional
#
# from pydantic import BaseModel
#
# from src.schemas.document import Document
#
#
# class VectorDBQuery(BaseModel):
#     r"""Represents a query to a vector database.
#
#     Attributes:
#         query_vector (List[float]): The numerical representation of the query
#             vector.
#         top_k (int, optional): The number of top similar vectors to retrieve
#             from the database. (default: :obj:`1`)
#     """
#
#     query_vector: List[float]
#     """The numerical representation of the query vector."""
#     top_k: int = 3
#     """The number of top similar vectors to retrieve from the database."""
#
#     def __init__(self, query_vector: List[float], top_k: int, **kwargs: Any) -> None:
#         """Pass in query_vector and tok_k as positional arg.
#         Args:
#             query_vector (List[float]): The numerical representation of the
#                 query vector.
#             top_k (int, optional): The number of top similar vectors to
#                 retrieve from the database. (default: :obj:`1`)
#         """
#         super().__init__(query_vector=query_vector, top_k=top_k, **kwargs)
#
#
# class VectorDBQueryResult(BaseModel):
#     r"""Encapsulates the result of a query against a vector database.
#
#     Attributes:
#         record (Document): The target vector record.
#         similarity (float): The similarity score between the query vector and
#             the record.
#     """
#
#     record: Document
#     similarity: float
#
#     @classmethod
#     def create(
#         cls,
#         similarity: float,
#         id: str,
#         vector: List[float] = None,
#         payload: Optional[Dict[str, Any]] = None,
#     ) -> "VectorDBQueryResult":
#         r"""A class method to construct a `VectorDBQueryResult` instance."""
#         content = payload.pop("content")
#         return cls(
#             record=Document(id=id, metadata=payload, content=content),
#             similarity=similarity,
#         )
#
#
# class VectorDBStatus(BaseModel):
#     r"""Vector database status.
#
#     Attributes:
#         vector_dim (int): The dimension of stored vectors.
#         vector_count (int): The number of stored vectors.
#
#     """
#
#     vector_dim: int
#     vector_count: int
#
#
# class BaseVectorStorage(ABC):
#     r"""An abstract base class for vector storage systems."""
#
#     @abstractmethod
#     def add(
#         self,
#         records: List[Document],
#         **kwargs: Any,
#     ) -> None:
#         r"""Saves a list of vector records to the storage.
#
#         Args:
#             records (List[Document]): List of vector records to be saved.
#             **kwargs (Any): Additional keyword arguments.
#
#         Raises:
#             RuntimeError: If there is an error during the saving process.
#         """
#         pass
#
#     @abstractmethod
#     def delete(
#         self,
#         ids: List[str],
#         **kwargs: Any,
#     ) -> None:
#         r"""Deletes a list of vectors identified by their IDs from the storage.
#
#         Args:
#             ids (List[str]): List of unique identifiers for the vectors to be
#                 deleted.
#             **kwargs (Any): Additional keyword arguments.
#
#         Raises:
#             RuntimeError: If there is an error during the deletion process.
#         """
#         pass
#
#     @abstractmethod
#     def status(self) -> VectorDBStatus:
#         r"""Returns status of the vector database.
#
#         Returns:
#             VectorDBStatus: The vector database status.
#         """
#         pass
#
#     @abstractmethod
#     def query(
#         self,
#         query: VectorDBQuery,
#         **kwargs: Any,
#     ) -> List[VectorDBQueryResult]:
#         r"""Searches for similar vectors in the storage based on the provided
#         query.
#
#         Args:
#             query (VectorDBQuery): The query object containing the search
#                 vector and the number of top similar vectors to retrieve.
#             **kwargs (Any): Additional keyword arguments.
#
#         Returns:
#             List[VectorDBQueryResult]: A list of vectors retrieved from the
#                 storage based on similarity to the query vector.
#         """
#         pass
#
#     @abstractmethod
#     def clear(self) -> None:
#         r"""Remove all vectors from the storage."""
#         pass
#
#     @abstractmethod
#     def load(self) -> None:
#         r"""Load the collection hosted on cloud service."""
#         pass
#
#     @property
#     @abstractmethod
#     def client(self) -> Any:
#         r"""Provides access to the underlying vector database client."""
#         pass
#
#     def get_payloads_by_vector(
#         self,
#         vector: List[float],
#         top_k: int,
#     ) -> List[Dict[str, Any]]:
#         r"""Returns payloads of top k vector records that closest to the given
#         vector.
#
#         This function is a wrapper of `BaseVectorStorage.query`.
#
#         Args:
#             vector (List[float]): The search vector.
#             top_k (int): The number of top similar vectors.
#
#         Returns:
#             List[List[Dict[str, Any]]]: A list of vector payloads retrieved
#                 from the storage based on similarity to the query vector.
#         """
#         results = self.query(VectorDBQuery(query_vector=vector, top_k=top_k))
#         return [
#             result.record.payload
#             for result in results
#             if result.record.payload is not None
#         ]


from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class VectorDBStatus(BaseModel):
    """Represents the status of the vector database."""
    vector_dim: int
    vector_count: int

class VectorDBQuery(BaseModel):
    """Represents a query to the vector database."""
    query_vector: List[float]
    top_k: int = Field(default=10, description="The number of top results to return.")

class VectorDBQueryResult(BaseModel):
    """
    Represents a single result item from a vector database query.
    This model now correctly includes the 'payload' attribute.
    """
    id: str
    similarity: float
    payload: Optional[Dict[str, Any]] = Field(default=None, description="The metadata and content payload of the vector.")
    vector: Optional[List[float]] = Field(default=None, description="The vector embedding of the result.")

    @classmethod
    def create(
        cls,
        id: str,
        similarity: float,
        payload: Optional[Dict[str, Any]] = None,
        vector: Optional[List[float]] = None,
    ) -> "VectorDBQueryResult":
        """
        A factory method to create an instance of VectorDBQueryResult,
        ensuring all provided arguments are passed to the model's constructor.
        """
        return cls(id=id, similarity=similarity, payload=payload, vector=vector)