from dotenv import load_dotenv
load_dotenv('.env')
from rag.config.settings import RAGSettings
s = RAGSettings()

if not s.pinecone_api_key or s.pinecone_api_key == 'your_pinecone_api_key_here':
    print('PINECONE_API_KEY is not set yet in .env')
    print('Open backend/.env and paste your real API key')
else:
    print('API key found in .env')
    print('Connecting to Pinecone...')
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=s.pinecone_api_key)
        indexes = pc.list_indexes()
        names = [idx.name for idx in indexes]
        print(f'Connected! Indexes found: {names}')
        if s.pinecone_index_name in names:
            print(f'Index "{s.pinecone_index_name}" exists and is ready!')
        else:
            print(f'Index "{s.pinecone_index_name}" not found.')
            print(f'Create it in the Pinecone dashboard with dimension=384, metric=cosine')
    except Exception as e:
        print(f'Connection failed: {e}')
