"""
Semantic Intelligence Adapter

Sentence Transformer wrapper
"""

from typing import List, Dict, Any

from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim



class SemanticIntelligence:
    """
    Production wrapper for Sentence Transformer.
    """

    MODEL_NAME = (
        "sentence-transformers/"
        "paraphrase-multilingual-mpnet-base-v2"
    )


    def __init__(
        self,
        device: str = "cpu"
    ) -> None:


        self.model = SentenceTransformer(
            self.MODEL_NAME,
            device=device
        )



    def encode(
        self,
        texts: List[str]
    ):

        if not texts:

            return []


        return self.model.encode(
            texts,
            batch_size=16,
            normalize_embeddings=True
        )



    def similarity(
        self,
        text_a: str,
        text_b: str
    ) -> float:


        embeddings = self.encode(
            [
                text_a,
                text_b
            ]
        )


        score = cos_sim(
            embeddings[0],
            embeddings[1]
        )


        return float(
            score[0][0]
        )



    #
    # Compatibility function
    # dipakai editorial_engine
    #

    def compare(
        self,
        text: str,
        reference: str
    ) -> float:


        return self.similarity(
            text,
            reference
        )



    def rank_segments(
        self,
        segments: List[str],
        reference: str
    ) -> List[Dict[str,Any]]:


        reference_embedding = self.model.encode(
            reference,
            normalize_embeddings=True
        )


        segment_embeddings = self.model.encode(
            segments,
            normalize_embeddings=True
        )


        scores = cos_sim(
            reference_embedding,
            segment_embeddings
        )[0]


        results = []


        for index,segment in enumerate(segments):

            results.append(
                {
                    "segment":segment,
                    "score":float(scores[index])
                }
            )


        results.sort(
            key=lambda x:x["score"],
            reverse=True
        )


        return results





#
# Alias untuk Editorial Engine
#

SemanticAdapter = SemanticIntelligence





def _self_test():


    print(
        "Testing Sentence Transformer..."
    )


    engine = SemanticAdapter()


    score = engine.compare(
        "Cara investasi saham",
        "Belajar investasi saham"
    )


    print(
        "Similarity:",
        score
    )


    print(
        "semantic_adapter.py sanity check: OK"
    )



if __name__ == "__main__":

    _self_test()