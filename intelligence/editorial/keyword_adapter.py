"""
Keyword Intelligence Adapter

KeyBERT + Sentence Transformer
"""


from typing import List, Dict, Any


from keybert import KeyBERT

from sentence_transformers import SentenceTransformer




class KeywordAdapter:


    def __init__(
        self,
        model_name:
        str =
        "sentence-transformers/all-mpnet-base-v2"

    ):


        print(
            "[Keyword] Loading Sentence Transformer..."
        )


        self.encoder = SentenceTransformer(
            model_name
        )


        self.keyword_model = KeyBERT(
            model=self.encoder
        )


        print(
            "[Keyword] Model ready"
        )




    def extract_keywords(
        self,
        text:str,
        top_n:int=5
    )->List[Dict[str,Any]]:


        if not text:

            return []



        results = self.keyword_model.extract_keywords(

            text,

            keyphrase_ngram_range=(1,3),

            use_mmr=True,

            diversity=0.7,

            top_n=top_n

        )



        output=[]


        for keyword,score in results:


            output.append(

                {
                    "keyword":keyword,
                    "score":float(score)
                }

            )


        return output





    #
    # Compatibility untuk engine
    #

    def extract(
        self,
        text:str
    )->Dict[str,Any]:


        keywords = self.extract_keywords(
            text
        )


        if not keywords:


            return {

                "keywords":[],
                "score":0.0

            }



        return {


            "keywords":

            [
                item["keyword"]
                for item in keywords
            ],


            "score":

            sum(
                item["score"]
                for item in keywords
            )
            /
            len(keywords)

        }






    def analyze_segment(
        self,
        segment:str
    ):


        return {

            "segment":segment,

            "keywords":
            self.extract_keywords(segment)

        }





def _self_test():


    print(
        "Testing Keyword Adapter..."
    )


    engine=KeywordAdapter()


    result=engine.extract(
        "Investasi saham membutuhkan analisis fundamental"
    )


    print(result)


    print(
        "keyword_adapter.py sanity check: OK"
    )



if __name__=="__main__":

    _self_test()