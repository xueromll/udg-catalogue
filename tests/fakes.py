import re
import zlib

from sci_etl_core.embeddings import AsyncEmbedder

DIMENSIONS = 64


def hashed_vector(text):
    vector = [0.0] * DIMENSIONS
    for word in re.findall(r"\w+", text.casefold()):
        vector[zlib.crc32(word.encode("utf-8")) % DIMENSIONS] += 1.0
    if not any(vector):
        vector[0] = 1.0
    return vector


class HashingEmbedder(AsyncEmbedder):
    def __init__(self):
        self.batches = []
        self.closed = False

    async def embed(self, texts):
        self.batches.append(list(texts))
        return [hashed_vector(text) for text in texts]

    async def aclose(self):
        self.closed = True
