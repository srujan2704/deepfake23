# Test code
from serpapi import GoogleSearch

params = {
    "engine": "google_lens",
    "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Cat03.jpg/481px-Cat03.jpg",
    "api_key": "af7f0bdbc46813db68b68b8b2eea99a3df1e591581e80b7ce544e8d88e0e12ac"
}

search = GoogleSearch(params)
results = search.get_dict()
print(results)
