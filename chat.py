import os
from dotenv import load_dotenv
from cerebras.cloud.sdk import Cerebras

load_dotenv()

client = Cerebras(api_key=os.getenv("CEREBRAS_API_KEY"))

models = client.models.list()

print(models)