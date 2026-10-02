import os
from datetime import datetime, timezone

from dotenv import load_dotenv

from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.embedder.openai import (
    OpenAIEmbedder,
    OpenAIEmbedderConfig,
)
from graphiti_core.cross_encoder.openai_reranker_client import (
    OpenAIRerankerClient,
)


load_dotenv()


class GraphitiService:
    def __init__(self, neo4j_password: str):

        api_key = os.getenv("OPENROUTER_API_KEY")

        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set")

        base_url = "https://openrouter.ai/api/v1"

        # LLM configuration
        llm_config = LLMConfig(
            api_key=api_key,
            model="google/gemini-2.5-flash",
            base_url=base_url,
            temperature=0,
        )

        # Graphiti LLM
        llm_client = OpenAIGenericClient(
            config=llm_config
        )

        # Graphiti embeddings
        embedder_config = OpenAIEmbedderConfig(
            api_key=api_key,
            embedding_model="openai/text-embedding-3-small",
            base_url=base_url,
            embedding_dim=1536,
        )

        embedder = OpenAIEmbedder(
            config=embedder_config
        )

        # Graphiti reranker
        cross_encoder = OpenAIRerankerClient(
            config=llm_config
        )

        # Graphiti + Neo4j
        self.graphiti = Graphiti(
            uri="bolt://localhost:7687",
            user="neo4j",
            password=neo4j_password,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=cross_encoder,
        )

    async def initialize(self):
        await self.graphiti.build_indices_and_constraints()

    async def add_context(
        self,
        group_id: str,
        content: str,
        source_description: str = "Queryable Chatbot",
    ):

        await self.graphiti.add_episode(
            name=f"context_{group_id}",
            episode_body=content,
            source_description=source_description,
            reference_time=datetime.now(timezone.utc),
            group_id=group_id,
        )

    async def search_context(
        self,
        group_id: str,
        query: str,
        num_results: int = 5,
    ):

        results = await self.graphiti.search(
            query=query,
            group_ids=[group_id],
            num_results=num_results,
        )

        return results

    async def close(self):
        await self.graphiti.close()