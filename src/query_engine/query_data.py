import os
import time
import asyncio

# from typing import  List, Dict

from dotenv import load_dotenv, find_dotenv
from langchain.prompts import ChatPromptTemplate
# from trulens_eval import TruCustomApp
from langchain.vectorstores.chroma import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from src.logging import Logger
from src.evaluation import TestEngine
# from trulens_eval.instruments import instrument

load_dotenv(find_dotenv())

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
APP_FOLDER = os.getenv("APP_FOLDER", "")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
EMB_MODEL = os.getenv("EMB_MODEL", "text-embedding-ada-002")
CHROMA_PATH = os.path.join(APP_FOLDER, './data/chroma')


PROMPT_TEMPLATE = """
Answer the question based only on the following context:

{context}

---

Answer the question based on the above context: {question}
"""


class QueryData:
    def __init__(self):
        # self.tests = TestEngine()
        self.db = None  # Will be initialized in prepare_db
        self.tru_rag = None

    async def prepare_db(self):
        embedding_function = OpenAIEmbeddings(
            model=EMB_MODEL, openai_api_key=OPENAI_API_KEY
        )
        db = Chroma(persist_directory=CHROMA_PATH,
                    embedding_function=embedding_function)
        return db


    async def retrieve_context(self, query: str) -> (list, list):

        if not self.db:
            self.db = await self.prepare_db()

        results = self.db.similarity_search_with_relevance_scores(query, k=3)
        if not results or results[0][1] < 0.7:
           raise Exception(status_code=404, detail="Matching results not found")
        contextes, scores = zip(*[(doc.page_content, _score) for doc, _score in results])
        return contextes, scores


    def prepare_promt(self, query: str, contextes: list) -> str:
        context_text = "\n\n---\n\n".join(contextes)
        prompt_template = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)
        prompt = prompt_template.format(context=context_text, question=query)
        return prompt


    async def llm_query(self, prompt: str) -> str:
        model = ChatOpenAI(openai_api_key=OPENAI_API_KEY, model=MODEL_NAME)
        response_text = model.invoke(prompt)
        response_text = response_text.content
        return response_text



    async def take_answer(self, query_text: str) -> dict:
        prompt_start_time = time.perf_counter()
        contexts, scores = await self.retrieve_context(query_text)
        prompt = self.prepare_promt(query_text, contexts)
        prompt_end_time = time.perf_counter()

        llm_response = await self.llm_query(prompt)
        response_end_time = time.perf_counter()

        prompt_duration = round(prompt_end_time - prompt_start_time, 2)
        response_duration = round(response_end_time - prompt_end_time, 2)
        total_duration = round(response_end_time - prompt_start_time, 2)

        token_spents, formatted_spents = Logger.calculate_tokens(prompt, llm_response)
        hints = Logger.format_hints(contexts, scores)

        response_data = {
            "query_text": query_text,
            "response_text": llm_response,
            "total_time": total_duration,
            "token_spents": formatted_spents,
            "hints": hints,
            "prompt_time": prompt_duration,
            "llm_time": response_duration,
        }

        asyncio.create_task(self.log_query_info(prompt, response_data, str(scores), token_spents))
        return response_data



    async def log_query_info(self, prompt: str, response_data: dict, scores: str, token_spents: int) -> None:
        Logger.log_query_info(response_data['query_text'], prompt, response_data["prompt_time"], response_data["llm_time"],
                            response_data["total_time"], response_data["response_text"],token_spents, response_data["token_spents"], scores)



