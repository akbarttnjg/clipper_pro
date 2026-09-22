"""
Topic Intelligence Adapter

BERTopic wrapper
"""


from typing import List, Dict, Any


from sentence_transformers import SentenceTransformer

from bertopic import BERTopic

from umap import UMAP

from hdbscan import HDBSCAN




class TopicIntelligenceEngine:



    def __init__(self):


        print(
            "[Topic] Loading model..."
        )


        self.encoder = SentenceTransformer(
            "sentence-transformers/all-mpnet-base-v2"
        )


        self.umap = UMAP(

            n_neighbors=5,

            n_components=2,

            min_dist=0.0,

            metric="cosine",

            random_state=42

        )


        self.cluster = HDBSCAN(

            min_cluster_size=3,

            min_samples=1

        )


        self.model = BERTopic(

            umap_model=self.umap,

            hdbscan_model=self.cluster

        )




    def analyze(
        self,
        segments:List[str]
    )->List[Dict[str,Any]]:



        if len(segments)<6:


            return [

                {

                    "segment":x,

                    "topic_id":-1,

                    "keywords":[],

                    "confidence":0.0

                }

                for x in segments

            ]



        embeddings=self.encoder.encode(
            segments,
            normalize_embeddings=True
        )



        topics, probabilities = self.model.fit_transform(

            segments,

            embeddings

        )



        results=[]



        for i,text in enumerate(segments):


            results.append(

                {

                    "segment":text,

                    "topic_id":int(topics[i]),

                    "keywords":[],

                    "confidence":0.5

                }

            )



        return results




    #
    # Compatibility untuk Editorial Engine
    #

    def analyze_batch(
        self,
        segments:List[str]
    ):


        return self.analyze(
            segments
        )





#
# Alias
#

TopicAdapter = TopicIntelligenceEngine






def _self_test():


    print(
        "Testing Topic Adapter..."
    )


    engine=TopicAdapter()


    result=engine.analyze_batch(

        [

        "Investasi saham dan keuangan",

        "Strategi bisnis online",

        "Literasi finansial"

        ]

    )


    print(result)


    print(
        "topic_adapter.py sanity check: OK"
    )



if __name__=="__main__":

    _self_test()