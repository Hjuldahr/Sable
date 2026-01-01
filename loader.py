import csv
import requests
import pathlib

url = 'https://storage.googleapis.com/kagglesdsdata/datasets/2488965/4222789/NRC-VAD-Lexicon/BipolarScale/NRC-VAD-Lexicon.txt?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=gcp-kaggle-com%40kaggle-161607.iam.gserviceaccount.com%2F20260101%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20260101T230103Z&X-Goog-Expires=259200&X-Goog-SignedHeaders=host&X-Goog-Signature=8e296a610f332a02ef4941bc2c6e02a8f2bd8be2108d669ead66e7f59b8aa0936f1c9f35479e9a28853d24528e68ed572aa19dcb6d42b10da4e1a54aae0b5ff3783d8ca8a46cc90a5c576076a46a1904ad9626dc558f2e414f00f885dd824e249cac5a255a9ee65dbcb534e8b06311a5fb1c9c1705c2e25c8b054e7a3ae28618b88af84047b346a9b800473f9f890a9701b685d290e15c5751ad9cc2075bddec751e11e0920f7f4ff2659e1a2da26a4a555583725e95ed8942ec2d807fa0425680ee715e38d7bbdf854117703ceae64e0887aa27a915955c3862fb64d3b5ac6699a1ee196491e6985460417c5135b93dd76339c56647f54bc55336396680e2dd'

path = pathlib.Path(__file__).resolve().parents[1] / "data" / "nrc-vad" / "NRC-Bipolar-VAD-Lexicon.csv"
path.parent.mkdir(parents=True, exist_ok=True)

try:
    response = requests.get(url)
    response.raise_for_status()
    
    with open(path, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["word", "valence", "arousal", "dominance"])
        writer.writerows(row.split('\t') for row in response.text.splitlines() if row.strip())
        
except Exception as e:
    print(f"An error occurred: {e}")