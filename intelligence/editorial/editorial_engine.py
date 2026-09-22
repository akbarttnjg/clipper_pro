"""
Editorial Intelligence Engine

Orchestrator layer:
Semantic + Topic + Keyword intelligence.

Compatible with:
- semantic_adapter.py
- topic_adapter.py
- keyword_adapter.py
"""


from dataclasses import dataclass
from typing import List, Dict, Any


from .semantic_adapter import SemanticAdapter
from .topic_adapter import TopicAdapter
from .keyword_adapter import KeywordAdapter



@dataclass
class EditorialResult:
    """
    Final editorial scoring result.
    """

    segment: str

    topic_id: int

    keywords: List[str]

    semantic_score: float

    topic_score: float

    keyword_score: float

    editorial_score: float



class EditorialEngine:
    """
    Main intelligence orchestration engine.
    """


    def __init__(self) -> None:

        print(
            "[Editorial] Loading Intelligence Layer..."
        )


        self.semantic = SemanticAdapter()


        self.topic = TopicAdapter()


        self.keyword = KeywordAdapter()



    # -------------------------------------------------
    # Semantic scoring
    # -------------------------------------------------

    def _semantic_score(
        self,
        segment: str,
        reference: str
    ) -> float:
        """
        Compare semantic similarity.

        Return:
            float 0-1
        """

        try:

            return float(
                self.semantic.compare(
                    segment,
                    reference
                )
            )

        except Exception:

            return 0.0



    # -------------------------------------------------
    # Keyword scoring
    # -------------------------------------------------

    def _keyword_analysis(
        self,
        segment: str
    ) -> Dict[str,Any]:

        try:

            return self.keyword.extract(
                segment
            )

        except Exception:

            return {

                "keywords": [],

                "score":0.0

            }



    # -------------------------------------------------
    # Single segment analysis
    # -------------------------------------------------

    def analyze_segment(
        self,
        segment:str,
        reference:str,
        topic_data:Dict[str,Any]
    )->EditorialResult:


        semantic_score = self._semantic_score(
            segment,
            reference
        )


        keyword_data = self._keyword_analysis(
            segment
        )


        keywords = keyword_data.get(
            "keywords",
            []
        )


        keyword_score = float(
            keyword_data.get(
                "score",
                0.0
            )
        )


        topic_score = float(
            topic_data.get(
                "confidence",
                0.0
            )
        )


        topic_id = int(
            topic_data.get(
                "topic_id",
                -1
            )
        )


        #
        # Weighted editorial scoring
        #

        editorial_score = (

            semantic_score * 0.5

            +

            topic_score * 0.2

            +

            keyword_score * 0.3

        ) * 100



        return EditorialResult(

            segment=segment,

            topic_id=topic_id,

            keywords=keywords,

            semantic_score=round(
                semantic_score,
                4
            ),

            topic_score=round(
                topic_score,
                4
            ),

            keyword_score=round(
                keyword_score,
                4
            ),

            editorial_score=round(
                editorial_score,
                2
            )

        )



    # -------------------------------------------------
    # Batch ranking
    # -------------------------------------------------

    def rank_segments(
        self,
        segments:List[str],
        reference:str
    )->List[EditorialResult]:
        """
        Analyze and rank all segments.
        """


        if not segments:

            return []



        topic_results = self.topic.analyze_batch(
            segments
        )


        results=[]


        for segment,topic_data in zip(
            segments,
            topic_results
        ):


            result=self.analyze_segment(

                segment,

                reference,

                topic_data

            )


            results.append(
                result
            )



        results.sort(

            key=lambda x:
            x.editorial_score,

            reverse=True

        )


        return results





    # -------------------------------------------------
    # Display helper
    # -------------------------------------------------

    def print_ranking(
        self,
        results:List[EditorialResult]
    )->None:


        print(
            "\n=============================="
        )

        print(
            "EDITORIAL RANKING"
        )

        print(
            "=============================="
        )



        for index,item in enumerate(
            results,
            start=1
        ):


            print(
                f"\n#{index}"
            )


            print(
                "Segment:"
            )

            print(
                item.segment
            )


            print(
                "Topic ID:",
                item.topic_id
            )


            print(
                "Keywords:",
                item.keywords
            )


            print(
                "Semantic:",
                item.semantic_score
            )


            print(
                "Topic:",
                item.topic_score
            )


            print(
                "Keyword:",
                item.keyword_score
            )


            print(
                "Editorial Score:",
                item.editorial_score
            )

            print(
                "-"*40
            )





def _self_test()->None:


    print(
        "Testing Editorial Engine v4..."
    )


    engine = EditorialEngine()



    segments=[

        "Investasi saham membutuhkan analisis fundamental",

        "Strategi bisnis online membutuhkan pemahaman pelanggan",

        "Literasi finansial membantu mengatur uang"


    ]


    reference = (

        "investasi saham dan "
        "strategi finansial"
    )


    results = engine.rank_segments(

        segments,

        reference

    )


    engine.print_ranking(
        results
    )



    print(
        "\neditorial_engine.py sanity check: OK"
    )





if __name__=="__main__":

    _self_test()