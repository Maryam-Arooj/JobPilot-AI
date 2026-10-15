class CareerMemoryAgent:
    def store_memory(self, user_id: int, memory_type: str, content: str, tags: list):
        return {"user_id": user_id, "type": memory_type, "content": content, "tags": tags}

    def retrieve_memories(self, user_id: int, query: str):
        return []
