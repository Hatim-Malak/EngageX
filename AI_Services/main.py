import os
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEndpointEmbeddings

# 1. Load environment variables
load_dotenv()

hf_token = os.environ.get("HUGGINGFACEHUB_API_TOKEN")

if not hf_token:
    raise ValueError("Missing critical environment variables!")

# 2. Initialize the embedding model
embeddings = HuggingFaceEndpointEmbeddings(model="BAAI/bge-m3")

# 3. TEST: Generate an embedding for a sample sentence
try:
    test_text = "Testing my video RAG chatbot embedding generation."
    vector = embeddings.embed_query(test_text)
    
    print("\n--- EMBEDDING TEST SUCCESSFUL ---")
    print(f"Vector Type: {type(vector)}")
    print(f"Vector Dimensions: {len(vector)} (Expected: 1024)")
    print(f"First 5 values: {vector[:5]}")
    
except Exception as e:
    print("\n--- EMBEDDING TEST FAILED ---")
    print(f"Error details: {e}")